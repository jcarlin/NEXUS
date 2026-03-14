"""Feature flag service — CRUD, Settings mutation, and DI cache clearing."""

from __future__ import annotations

from uuid import UUID

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.feature_flags.registry import FLAG_REGISTRY
from app.feature_flags.schemas import (
    FeatureFlagDetail,
    FeatureFlagUpdateResponse,
)

logger = structlog.get_logger(__name__)


class FeatureFlagService:
    """Static methods for feature flag management."""

    @staticmethod
    async def list_flags(db: AsyncSession) -> list[FeatureFlagDetail]:
        """List all flags with current resolved values."""
        from app.dependencies import get_settings

        settings = get_settings()

        # Fetch DB overrides
        result = await db.execute(
            text("""
                SELECT flag_name, enabled, updated_at, updated_by
                FROM feature_flag_overrides
            """)
        )
        overrides = {r["flag_name"]: dict(r) for r in result.mappings().all()}

        items: list[FeatureFlagDetail] = []
        for flag_name, meta in FLAG_REGISTRY.items():
            override = overrides.get(flag_name)
            env_default = settings_env_default(flag_name)
            current_value = getattr(settings, flag_name)

            items.append(
                FeatureFlagDetail(
                    flag_name=flag_name,
                    display_name=meta.display_name,
                    description=meta.description,
                    category=meta.category,
                    risk_level=meta.risk_level,
                    enabled=current_value,
                    is_override=override is not None,
                    env_default=env_default,
                    updated_at=override["updated_at"] if override else None,
                    updated_by=override["updated_by"] if override else None,
                )
            )

        return items

    @staticmethod
    async def update_flag(
        db: AsyncSession,
        flag_name: str,
        enabled: bool,
        user_id: UUID | None = None,
    ) -> FeatureFlagUpdateResponse:
        """Toggle a flag: UPSERT DB override, mutate Settings singleton, clear DI caches."""
        if flag_name not in FLAG_REGISTRY:
            raise ValueError(f"Unknown feature flag: {flag_name}")

        meta = FLAG_REGISTRY[flag_name]

        # UPSERT override
        result = await db.execute(
            text("""
                INSERT INTO feature_flag_overrides (flag_name, enabled, updated_by, updated_at)
                VALUES (:flag_name, :enabled, :updated_by, now())
                ON CONFLICT (flag_name) DO UPDATE SET
                    enabled = EXCLUDED.enabled,
                    updated_by = EXCLUDED.updated_by,
                    updated_at = now()
                RETURNING flag_name, enabled, updated_at, updated_by
            """),
            {
                "flag_name": flag_name,
                "enabled": enabled,
                "updated_by": user_id,
            },
        )
        row = result.mappings().one()

        # Mutate Settings singleton
        from app.dependencies import get_settings

        settings = get_settings()
        setattr(settings, flag_name, enabled)
        logger.info("feature_flag.updated", flag=flag_name, enabled=enabled)

        # Clear DI caches
        caches_cleared = _clear_di_caches(meta.di_caches)

        return FeatureFlagUpdateResponse(
            flag_name=flag_name,
            display_name=meta.display_name,
            description=meta.description,
            category=meta.category,
            risk_level=meta.risk_level,
            enabled=enabled,
            is_override=True,
            env_default=settings_env_default(flag_name),
            updated_at=row["updated_at"],
            updated_by=row["updated_by"],
            caches_cleared=caches_cleared,
            restart_required=meta.risk_level == "restart",
        )

    @staticmethod
    async def reset_flag(db: AsyncSession, flag_name: str) -> None:
        """Remove DB override, revert Settings to env default, clear DI caches."""
        if flag_name not in FLAG_REGISTRY:
            raise ValueError(f"Unknown feature flag: {flag_name}")

        meta = FLAG_REGISTRY[flag_name]

        await db.execute(
            text("DELETE FROM feature_flag_overrides WHERE flag_name = :flag_name"),
            {"flag_name": flag_name},
        )

        # Revert to env default
        from app.dependencies import get_settings

        settings = get_settings()
        env_default = settings_env_default(flag_name)
        setattr(settings, flag_name, env_default)
        logger.info("feature_flag.reset", flag=flag_name, env_default=env_default)

        _clear_di_caches(meta.di_caches)

    @staticmethod
    async def load_overrides_into_settings(db: AsyncSession) -> None:
        """Load all DB overrides into the Settings singleton. Called at startup."""
        from app.dependencies import get_settings

        settings = get_settings()

        result = await db.execute(text("SELECT flag_name, enabled FROM feature_flag_overrides"))
        rows = result.mappings().all()
        if not rows:
            return

        for row in rows:
            flag_name = row["flag_name"]
            if flag_name in FLAG_REGISTRY and hasattr(settings, flag_name):
                setattr(settings, flag_name, row["enabled"])
                logger.info("feature_flag.override_loaded", flag=flag_name, enabled=row["enabled"])

        logger.info("feature_flags.overrides_loaded", count=len(rows))


def load_overrides_sync(settings: object, engine: object) -> None:
    """Load DB feature flag overrides into a Settings instance (sync).

    Called by Celery tasks so each execution picks up the latest
    admin-toggled values without a worker restart.
    """
    with engine.connect() as conn:
        result = conn.execute(text("SELECT flag_name, enabled FROM feature_flag_overrides"))
        rows = result.mappings().all()
    if not rows:
        return
    for row in rows:
        flag_name = row["flag_name"]
        if flag_name in FLAG_REGISTRY and hasattr(settings, flag_name):
            setattr(settings, flag_name, row["enabled"])


def load_overrides_sync_safe(settings: object, engine: object) -> None:
    """Like load_overrides_sync but logs and continues on failure.

    Safe for Celery tasks where the overrides table may not exist yet.
    """
    try:
        load_overrides_sync(settings, engine)
    except Exception:
        logger.warning("feature_flags.sync_load_failed", exc_info=True)


def settings_env_default(flag_name: str) -> bool:
    """Get the env-file default for a flag by reading Settings model field defaults."""
    from app.config import Settings

    field_info = Settings.model_fields.get(flag_name)
    if field_info is None:
        return False
    default = field_info.default
    return bool(default) if default is not None else False


def _clear_di_caches(cache_names: list[str]) -> list[str]:
    """Clear specified DI factory caches. Returns names of caches actually cleared."""
    from app import dependencies

    cleared: list[str] = []
    for cache_name in cache_names:
        factory = getattr(dependencies, cache_name, None)
        if factory is not None and hasattr(factory, "cache_clear"):
            factory.cache_clear()
            cleared.append(cache_name)
            logger.info("feature_flag.cache_cleared", cache=cache_name)
    return cleared
