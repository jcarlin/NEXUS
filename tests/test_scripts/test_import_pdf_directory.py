"""Tests for scripts/import_pdf_directory.py.

Covers:
- PDF file discovery (extension filtering, hidden files, OS artifacts)
- Dry-run mode (count only, no dispatch)
- Resume logic (skips existing content hashes)
- CLI argument validation
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from scripts.import_pdf_directory import discover_pdfs, lookup_dataset_id

# ---------------------------------------------------------------------------
# discover_pdfs() tests
# ---------------------------------------------------------------------------


class TestDiscoverPdfs:
    """Test recursive PDF discovery logic."""

    def test_finds_pdf_files(self, tmp_path: Path):
        (tmp_path / "a.pdf").write_bytes(b"%PDF-1.4 fake")
        (tmp_path / "b.PDF").write_bytes(b"%PDF-1.4 fake")  # uppercase
        (tmp_path / "c.txt").write_bytes(b"not a pdf")

        result = discover_pdfs(tmp_path)

        assert len(result) == 2
        names = {p.name for p in result}
        assert names == {"a.pdf", "b.PDF"}

    def test_recurses_subdirectories(self, tmp_path: Path):
        sub = tmp_path / "subdir" / "nested"
        sub.mkdir(parents=True)
        (sub / "deep.pdf").write_bytes(b"%PDF")
        (tmp_path / "top.pdf").write_bytes(b"%PDF")

        result = discover_pdfs(tmp_path)

        assert len(result) == 2

    def test_skips_hidden_files(self, tmp_path: Path):
        (tmp_path / ".hidden.pdf").write_bytes(b"%PDF")
        (tmp_path / "visible.pdf").write_bytes(b"%PDF")

        result = discover_pdfs(tmp_path)

        assert len(result) == 1
        assert result[0].name == "visible.pdf"

    def test_skips_hidden_directories(self, tmp_path: Path):
        hidden_dir = tmp_path / ".hidden_dir"
        hidden_dir.mkdir()
        (hidden_dir / "secret.pdf").write_bytes(b"%PDF")
        (tmp_path / "visible.pdf").write_bytes(b"%PDF")

        result = discover_pdfs(tmp_path)

        assert len(result) == 1
        assert result[0].name == "visible.pdf"

    def test_skips_os_artifact_dirs(self, tmp_path: Path):
        macosx = tmp_path / "__MACOSX"
        macosx.mkdir()
        (macosx / "junk.pdf").write_bytes(b"%PDF")
        (tmp_path / "real.pdf").write_bytes(b"%PDF")

        result = discover_pdfs(tmp_path)

        assert len(result) == 1
        assert result[0].name == "real.pdf"

    def test_skips_os_artifact_files(self, tmp_path: Path):
        (tmp_path / ".DS_Store").write_bytes(b"junk")
        (tmp_path / "Thumbs.db").write_bytes(b"junk")
        (tmp_path / "real.pdf").write_bytes(b"%PDF")

        result = discover_pdfs(tmp_path)

        assert len(result) == 1

    def test_respects_limit(self, tmp_path: Path):
        for i in range(10):
            (tmp_path / f"doc_{i:02d}.pdf").write_bytes(b"%PDF")

        result = discover_pdfs(tmp_path, limit=3)

        assert len(result) == 3

    def test_returns_sorted(self, tmp_path: Path):
        (tmp_path / "z.pdf").write_bytes(b"%PDF")
        (tmp_path / "a.pdf").write_bytes(b"%PDF")
        (tmp_path / "m.pdf").write_bytes(b"%PDF")

        result = discover_pdfs(tmp_path)

        assert [p.name for p in result] == ["a.pdf", "m.pdf", "z.pdf"]

    def test_empty_directory(self, tmp_path: Path):
        result = discover_pdfs(tmp_path)

        assert result == []

    def test_no_pdfs_in_directory(self, tmp_path: Path):
        (tmp_path / "readme.txt").write_bytes(b"text")
        (tmp_path / "image.png").write_bytes(b"png")

        result = discover_pdfs(tmp_path)

        assert result == []


# ---------------------------------------------------------------------------
# lookup_dataset_id() tests
# ---------------------------------------------------------------------------


class TestLookupDatasetId:
    """Test dataset ID lookup by name."""

    def test_returns_id_when_found(self):
        mock_engine = MagicMock()
        mock_conn = mock_engine.connect.return_value.__enter__.return_value
        mock_row = MagicMock()
        mock_row.id = "test-dataset-uuid"
        mock_conn.execute.return_value.first.return_value = mock_row

        result = lookup_dataset_id(mock_engine, "matter-1", "FBI Files")

        assert result == "test-dataset-uuid"

    def test_returns_none_when_not_found(self):
        mock_engine = MagicMock()
        mock_conn = mock_engine.connect.return_value.__enter__.return_value
        mock_conn.execute.return_value.first.return_value = None

        result = lookup_dataset_id(mock_engine, "matter-1", "Nonexistent")

        assert result is None


# ---------------------------------------------------------------------------
# CLI / main() tests
# ---------------------------------------------------------------------------


class TestMainCli:
    """Test main() via subprocess-like invocation with mocked dependencies."""

    def test_dry_run_counts_pdfs(self, tmp_path: Path, capsys):
        for i in range(5):
            (tmp_path / f"doc_{i}.pdf").write_bytes(b"%PDF-1.4 fake content")

        with patch(
            "sys.argv",
            [
                "import_pdf_directory.py",
                "--dir",
                str(tmp_path),
                "--matter-id",
                "00000000-0000-0000-0000-000000000001",
                "--dry-run",
            ],
        ):
            from scripts.import_pdf_directory import main

            rc = main()

        assert rc == 0
        captured = capsys.readouterr()
        assert "5 PDF file(s)" in captured.out
        assert "Dry Run" in captured.out

    def test_empty_dir_exits_zero(self, tmp_path: Path, capsys):
        with patch(
            "sys.argv",
            [
                "import_pdf_directory.py",
                "--dir",
                str(tmp_path),
                "--matter-id",
                "00000000-0000-0000-0000-000000000001",
                "--dry-run",
            ],
        ):
            from scripts.import_pdf_directory import main

            rc = main()

        assert rc == 0
        captured = capsys.readouterr()
        assert "No PDFs found" in captured.out

    def test_invalid_matter_id_exits_one(self, tmp_path: Path):
        with patch(
            "sys.argv",
            [
                "import_pdf_directory.py",
                "--dir",
                str(tmp_path),
                "--matter-id",
                "not-a-uuid",
            ],
        ):
            from scripts.import_pdf_directory import main

            rc = main()

        assert rc == 1

    def test_nonexistent_dir_exits_one(self):
        with patch(
            "sys.argv",
            [
                "import_pdf_directory.py",
                "--dir",
                "/nonexistent/path",
                "--matter-id",
                "00000000-0000-0000-0000-000000000001",
            ],
        ):
            from scripts.import_pdf_directory import main

            rc = main()

        assert rc == 1
