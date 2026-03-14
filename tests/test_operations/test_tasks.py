"""Unit tests for the operations Celery periodic task."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.operations.tasks import poll_service_health

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_settings():
    """Return a mock Settings object with test defaults."""
    settings = MagicMock()
    settings.redis_url = "redis://localhost:6379/0"
    settings.qdrant_url = "http://localhost:6333"
    settings.neo4j_uri = "bolt://localhost:7687"
    settings.neo4j_user = "neo4j"
    settings.neo4j_password = "test"
    settings.minio_endpoint = "localhost:9000"
    settings.minio_use_ssl = False
    return settings


def _mock_engine():
    """Return a mock sync SQLAlchemy engine with a connect() context manager."""
    engine = MagicMock()
    mock_conn = MagicMock()
    engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
    engine.connect.return_value.__exit__ = MagicMock(return_value=False)
    return engine, mock_conn


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestPollServiceHealth:
    @patch("app.config.Settings")
    @patch("app.operations.tasks._get_sync_engine")
    def test_poll_service_health_inserts_records(self, mock_get_engine, mock_settings_cls):
        """Successful polls insert one record per service plus cleanup."""
        engine, mock_conn = _mock_engine()
        mock_get_engine.return_value = engine
        mock_settings_cls.return_value = _mock_settings()

        # Mock successful service checks
        with (
            patch("redis.from_url") as mock_redis_from_url,
            patch("qdrant_client.QdrantClient") as mock_qdrant_cls,
            patch("neo4j.GraphDatabase.driver") as mock_neo4j_driver,
            patch("urllib.request.urlopen") as mock_urlopen,
        ):
            # Redis: ping succeeds
            mock_redis = MagicMock()
            mock_redis_from_url.return_value = mock_redis

            # Qdrant: get_collections succeeds
            mock_qc = MagicMock()
            mock_qdrant_cls.return_value = mock_qc

            # Neo4j: session.run succeeds
            mock_driver = MagicMock()
            mock_session = MagicMock()
            mock_driver.session.return_value.__enter__ = MagicMock(return_value=mock_session)
            mock_driver.session.return_value.__exit__ = MagicMock(return_value=False)
            mock_neo4j_driver.return_value = mock_driver

            # MinIO: urlopen succeeds
            mock_urlopen.return_value = MagicMock()

            result = poll_service_health()

        # All 5 services should report ok
        assert result == {
            "postgres": "ok",
            "redis": "ok",
            "qdrant": "ok",
            "neo4j": "ok",
            "minio": "ok",
        }

        # Verify execute calls: 1 SELECT (postgres check) + 5 INSERTs + 1 DELETE = 7
        execute_calls = mock_conn.execute.call_args_list
        assert len(execute_calls) == 7

        # Verify commit was called
        mock_conn.commit.assert_called_once()

    @patch("app.config.Settings")
    @patch("app.operations.tasks._get_sync_engine")
    def test_poll_service_health_handles_failures(self, mock_get_engine, mock_settings_cls):
        """When services fail, error records are inserted without crashing the task."""
        engine, mock_conn = _mock_engine()
        mock_get_engine.return_value = engine
        mock_settings_cls.return_value = _mock_settings()

        with (
            patch("redis.from_url") as mock_redis_from_url,
            patch("qdrant_client.QdrantClient") as mock_qdrant_cls,
            patch("neo4j.GraphDatabase.driver") as mock_neo4j_driver,
            patch("urllib.request.urlopen") as mock_urlopen,
        ):
            # Redis: raise on ping
            mock_redis = MagicMock()
            mock_redis.ping.side_effect = ConnectionError("Connection refused")
            mock_redis_from_url.return_value = mock_redis

            # Qdrant: raise
            mock_qdrant_cls.side_effect = ConnectionError("Qdrant down")

            # Neo4j: raise
            mock_neo4j_driver.side_effect = Exception("Neo4j connection failed")

            # MinIO: raise
            mock_urlopen.side_effect = Exception("MinIO unreachable")

            result = poll_service_health()

        # Postgres should still be ok (mocked engine works), the rest should be errors
        assert result["postgres"] == "ok"
        assert result["redis"] == "error"
        assert result["qdrant"] == "error"
        assert result["neo4j"] == "error"
        assert result["minio"] == "error"

        # 1 SELECT (postgres check) + 5 INSERTs + 1 DELETE = 7
        execute_calls = mock_conn.execute.call_args_list
        assert len(execute_calls) == 7
        mock_conn.commit.assert_called_once()

    @patch("app.config.Settings")
    @patch("app.operations.tasks._get_sync_engine")
    def test_poll_service_health_cleans_old_records(self, mock_get_engine, mock_settings_cls):
        """Verify the DELETE for records >31 days is executed."""
        engine, mock_conn = _mock_engine()
        mock_get_engine.return_value = engine
        mock_settings_cls.return_value = _mock_settings()

        with (
            patch("redis.from_url") as mock_redis_from_url,
            patch("qdrant_client.QdrantClient") as mock_qdrant_cls,
            patch("neo4j.GraphDatabase.driver") as mock_neo4j_driver,
            patch("urllib.request.urlopen") as mock_urlopen,
        ):
            mock_redis_from_url.return_value = MagicMock()
            mock_qc = MagicMock()
            mock_qdrant_cls.return_value = mock_qc

            mock_driver = MagicMock()
            mock_session = MagicMock()
            mock_driver.session.return_value.__enter__ = MagicMock(return_value=mock_session)
            mock_driver.session.return_value.__exit__ = MagicMock(return_value=False)
            mock_neo4j_driver.return_value = mock_driver

            mock_urlopen.return_value = MagicMock()

            poll_service_health()

        # The last execute call before commit should be the DELETE
        execute_calls = mock_conn.execute.call_args_list
        last_execute = execute_calls[-1]
        sql_text = str(last_execute[0][0])
        assert "DELETE" in sql_text
        assert "31 days" in sql_text
