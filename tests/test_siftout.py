"""
Siftout — comprehensive test suite
===================================

Run with:
    pytest tests/ -v --tb=short
    pytest tests/ -v --cov=siftout --cov-report=term-missing
"""

from __future__ import annotations

import os
import json
import logging
import textwrap
from pathlib import Path

import pytest

from siftout import Janitor, CleanReport, SecureReport
from siftout.hardware import DEFAULT_TRASH_PATTERNS


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────
@pytest.fixture()
def workspace(tmp_path: Path) -> Path:
    """A clean temporary workspace for each test."""
    return tmp_path


@pytest.fixture()
def dirty_workspace(workspace: Path) -> Path:
    """Workspace pre-populated with trash and real files."""
    # Trash
    (workspace / "__pycache__").mkdir()
    (workspace / "__pycache__" / "mod.cpython-311.pyc").write_bytes(b"\x00" * 128)
    (workspace / "old.log").write_text("log data")
    (workspace / "temp.tmp").write_text("tmp data")
    (workspace / "backup.bak").write_text("bak data")

    # Real source files (should survive)
    src = workspace / "myapp"
    src.mkdir()
    (src / "main.py").write_text("print('hello')\n")
    (src / "utils.py").write_text("def add(a, b): return a + b\n")

    return workspace


@pytest.fixture()
def secret_workspace(workspace: Path) -> Path:
    """Workspace containing Python files with hardcoded secrets."""
    app = workspace / "app"
    app.mkdir()

    (app / "config.py").write_text(
        textwrap.dedent(
            """\
            DEBUG = True
            DATABASE_URL = 'postgresql://localhost/mydb'
            SECRET_KEY = 'supersecretkey1234567890abc'
            SHORT = 'tiny'
            """
        )
    )

    (app / "integrations.py").write_text(
        textwrap.dedent(
            """\
            import requests
            STRIPE_API_KEY = 'sk_live_abcdefghij1234567890xyz'
            SENDGRID_KEY = 'SG.abcdefghijklmnopqrstuvwxyz1234'
            """
        )
    )

    # File that should be skipped (inside siftout package dir)
    skip_dir = workspace / "siftout"
    skip_dir.mkdir()
    (skip_dir / "hardware.py").write_text("INTERNAL = 'should_not_be_touched_at_all'\n")

    return workspace


# ─────────────────────────────────────────────────────────────────────────────
# Janitor initialisation
# ─────────────────────────────────────────────────────────────────────────────
class TestJanitorInit:
    def test_default_patterns_loaded(self, workspace):
        j = Janitor(root=workspace)
        for p in DEFAULT_TRASH_PATTERNS:
            assert p in j.trash_patterns

    def test_extra_pattern_string(self, workspace):
        j = Janitor(extra_patterns="*.bak", root=workspace)
        assert "*.bak" in j.trash_patterns

    def test_extra_patterns_list(self, workspace):
        j = Janitor(extra_patterns=["*.bak", "*.swp"], root=workspace)
        assert "*.bak" in j.trash_patterns
        assert "*.swp" in j.trash_patterns

    def test_dry_run_default_false(self, workspace):
        j = Janitor(root=workspace)
        assert j.dry_run is False

    def test_dry_run_true(self, workspace):
        j = Janitor(root=workspace, dry_run=True)
        assert j.dry_run is True

    def test_root_resolved(self, workspace):
        j = Janitor(root=str(workspace))
        assert j.root == workspace.resolve()

    def test_root_defaults_to_cwd(self):
        j = Janitor()
        assert j.root == Path.cwd()


# ─────────────────────────────────────────────────────────────────────────────
# list_trash
# ─────────────────────────────────────────────────────────────────────────────
class TestListTrash:
    def test_empty_workspace_returns_empty(self, workspace):
        j = Janitor(root=workspace)
        assert j.list_trash() == []

    def test_finds_pycache(self, dirty_workspace):
        j = Janitor(root=dirty_workspace)
        items = j.list_trash()
        names = [p.name for p in items]
        assert "__pycache__" in names

    def test_finds_log_files(self, dirty_workspace):
        j = Janitor(root=dirty_workspace)
        items = j.list_trash()
        names = [p.name for p in items]
        assert "old.log" in names

    def test_finds_tmp_files(self, dirty_workspace):
        j = Janitor(root=dirty_workspace)
        items = j.list_trash()
        names = [p.name for p in items]
        assert "temp.tmp" in names

    def test_finds_extra_pattern(self, dirty_workspace):
        j = Janitor(extra_patterns=["*.bak"], root=dirty_workspace)
        items = j.list_trash()
        names = [p.name for p in items]
        assert "backup.bak" in names

    def test_does_not_find_real_py_files(self, dirty_workspace):
        j = Janitor(root=dirty_workspace)
        items = j.list_trash()
        names = [p.name for p in items]
        assert "main.py" not in names
        assert "utils.py" not in names

    def test_returns_list_of_paths(self, dirty_workspace):
        j = Janitor(root=dirty_workspace)
        items = j.list_trash()
        assert all(isinstance(p, Path) for p in items)

    def test_no_duplicates(self, dirty_workspace):
        j = Janitor(extra_patterns=["*.log"], root=dirty_workspace)
        items = j.list_trash()
        assert len(items) == len(set(items))


# ─────────────────────────────────────────────────────────────────────────────
# self_destruct
# ─────────────────────────────────────────────────────────────────────────────
class TestSelfDestruct:
    def test_returns_clean_report(self, dirty_workspace):
        j = Janitor(root=dirty_workspace)
        report = j.self_destruct()
        assert isinstance(report, CleanReport)

    def test_report_keys(self, dirty_workspace):
        j = Janitor(root=dirty_workspace)
        report = j.self_destruct()
        assert set(report.keys()) == {"files", "folders", "errors", "bytes_freed"}

    def test_deletes_log_file(self, dirty_workspace):
        j = Janitor(root=dirty_workspace)
        j.self_destruct()
        assert not (dirty_workspace / "old.log").exists()

    def test_deletes_tmp_file(self, dirty_workspace):
        j = Janitor(root=dirty_workspace)
        j.self_destruct()
        assert not (dirty_workspace / "temp.tmp").exists()

    def test_deletes_pycache_dir(self, dirty_workspace):
        j = Janitor(root=dirty_workspace)
        j.self_destruct()
        assert not (dirty_workspace / "__pycache__").exists()

    def test_preserves_real_files(self, dirty_workspace):
        j = Janitor(root=dirty_workspace)
        j.self_destruct()
        assert (dirty_workspace / "myapp" / "main.py").exists()

    def test_dry_run_does_not_delete(self, dirty_workspace):
        j = Janitor(root=dirty_workspace, dry_run=True)
        j.self_destruct()
        assert (dirty_workspace / "old.log").exists()
        assert (dirty_workspace / "__pycache__").exists()

    def test_dry_run_still_counts(self, dirty_workspace):
        j = Janitor(root=dirty_workspace, dry_run=True)
        report = j.self_destruct()
        assert report["files"] > 0 or report["folders"] > 0

    def test_bytes_freed_positive_when_files_removed(self, dirty_workspace):
        j = Janitor(root=dirty_workspace)
        report = j.self_destruct()
        assert report["bytes_freed"] > 0

    def test_zero_errors_on_normal_workspace(self, dirty_workspace):
        j = Janitor(root=dirty_workspace)
        report = j.self_destruct()
        assert report["errors"] == 0

    def test_empty_workspace_zeros(self, workspace):
        j = Janitor(root=workspace)
        report = j.self_destruct()
        assert report == {"files": 0, "folders": 0, "errors": 0, "bytes_freed": 0}


# ─────────────────────────────────────────────────────────────────────────────
# secure_env
# ─────────────────────────────────────────────────────────────────────────────
class TestSecureEnv:
    def test_returns_secure_report(self, secret_workspace):
        j = Janitor(root=secret_workspace)
        report = j.secure_env()
        assert isinstance(report, SecureReport)

    def test_report_keys(self, secret_workspace):
        j = Janitor(root=secret_workspace)
        report = j.secure_env()
        assert set(report.keys()) == {"secrets_found", "files_patched", "env_entries_written"}

    def test_secrets_found_count(self, secret_workspace):
        j = Janitor(root=secret_workspace)
        report = j.secure_env()
        # SECRET_KEY, STRIPE_API_KEY, SENDGRID_KEY = 3 secrets
        assert report["secrets_found"] == 3

    def test_files_patched_count(self, secret_workspace):
        j = Janitor(root=secret_workspace)
        report = j.secure_env()
        assert report["files_patched"] == 2

    def test_secret_replaced_with_os_getenv(self, secret_workspace):
        j = Janitor(root=secret_workspace)
        j.secure_env()
        config = (secret_workspace / "app" / "config.py").read_text()
        assert "os.getenv('SECRET_KEY')" in config
        assert "supersecretkey1234567890abc" not in config

    def test_import_os_added(self, secret_workspace):
        j = Janitor(root=secret_workspace)
        j.secure_env()
        config = (secret_workspace / "app" / "config.py").read_text()
        assert "import os" in config

    def test_env_file_created(self, secret_workspace):
        j = Janitor(root=secret_workspace)
        j.secure_env()
        assert (secret_workspace / ".env").exists()

    def test_env_file_contains_secrets(self, secret_workspace):
        j = Janitor(root=secret_workspace)
        j.secure_env()
        env_content = (secret_workspace / ".env").read_text()
        assert "SECRET_KEY=" in env_content
        assert "STRIPE_API_KEY=" in env_content

    def test_gitignore_updated(self, secret_workspace):
        j = Janitor(root=secret_workspace)
        j.secure_env()
        gitignore = (secret_workspace / ".gitignore").read_text()
        assert ".env" in gitignore

    def test_existing_gitignore_not_duplicated(self, secret_workspace):
        gi = secret_workspace / ".gitignore"
        gi.write_text(".env\n")
        j = Janitor(root=secret_workspace)
        j.secure_env()
        content = gi.read_text()
        assert content.count(".env") == 1

    def test_existing_env_not_overwritten(self, secret_workspace):
        env_file = secret_workspace / ".env"
        env_file.write_text("SECRET_KEY=already_there\n")
        j = Janitor(root=secret_workspace)
        report = j.secure_env()
        env_content = env_file.read_text()
        # SECRET_KEY already exists, should not be duplicated
        assert env_content.count("SECRET_KEY=") == 1

    def test_skips_siftout_directory(self, secret_workspace):
        j = Janitor(root=secret_workspace)
        j.secure_env()
        # internal file should be untouched
        internal = (secret_workspace / "siftout" / "hardware.py").read_text()
        assert "INTERNAL" in internal
        assert "os.getenv" not in internal

    def test_short_values_not_replaced(self, secret_workspace):
        src = secret_workspace / "app" / "config.py"
        src.write_text("SHORT = 'tiny'\n")
        j = Janitor(root=secret_workspace)
        j.secure_env()
        assert "SHORT = 'tiny'" in src.read_text()

    def test_dry_run_does_not_modify(self, secret_workspace):
        original = (secret_workspace / "app" / "config.py").read_text()
        j = Janitor(root=secret_workspace, dry_run=True)
        j.secure_env()
        assert (secret_workspace / "app" / "config.py").read_text() == original

    def test_dry_run_no_env_file(self, secret_workspace):
        j = Janitor(root=secret_workspace, dry_run=True)
        j.secure_env()
        assert not (secret_workspace / ".env").exists()

    def test_backup_created(self, secret_workspace):
        j = Janitor(root=secret_workspace, backup=True)
        j.secure_env()
        assert (secret_workspace / "app" / "config.py.siftout.bak").exists()

    def test_no_backup_when_disabled(self, secret_workspace):
        j = Janitor(root=secret_workspace, backup=False)
        j.secure_env()
        assert not (secret_workspace / "app" / "config.py.siftout.bak").exists()

    def test_import_os_not_doubled(self, secret_workspace):
        src = secret_workspace / "app" / "already_imported.py"
        src.write_text("import os\nANOTHER_KEY = 'verylongsecretvalue12345678'\n")
        j = Janitor(root=secret_workspace)
        j.secure_env()
        content = src.read_text()
        assert content.count("import os") == 1


# ─────────────────────────────────────────────────────────────────────────────
# scan_duplicates
# ─────────────────────────────────────────────────────────────────────────────
class TestScanDuplicates:
    def test_no_duplicates(self, workspace):
        (workspace / "a.txt").write_text("unique content a")
        (workspace / "b.txt").write_text("unique content b")
        j = Janitor(root=workspace)
        assert j.scan_duplicates() == {}

    def test_detects_duplicates(self, workspace):
        content = b"identical file content for duplicate detection"
        (workspace / "file1.txt").write_bytes(content)
        (workspace / "file2.txt").write_bytes(content)
        j = Janitor(root=workspace)
        dupes = j.scan_duplicates()
        assert len(dupes) == 1
        paths = list(dupes.values())[0]
        assert len(paths) == 2

    def test_triplicate(self, workspace):
        content = b"three identical files"
        for name in ("x.dat", "y.dat", "z.dat"):
            (workspace / name).write_bytes(content)
        j = Janitor(root=workspace)
        dupes = j.scan_duplicates()
        assert len(list(dupes.values())[0]) == 3

    def test_empty_workspace(self, workspace):
        j = Janitor(root=workspace)
        assert j.scan_duplicates() == {}


# ─────────────────────────────────────────────────────────────────────────────
# summary
# ─────────────────────────────────────────────────────────────────────────────
class TestSummary:
    def test_returns_dict(self, workspace):
        j = Janitor(root=workspace)
        assert isinstance(j.summary(), dict)

    def test_required_keys(self, workspace):
        expected = {
            "root",
            "platform",
            "trash_items",
            "trash_size_bytes",
            "potential_secrets",
            "secret_locations",
            "duplicate_groups",
            "generated_at",
        }
        j = Janitor(root=workspace)
        assert expected.issubset(j.summary().keys())

    def test_root_is_string(self, workspace):
        j = Janitor(root=workspace)
        assert isinstance(j.summary()["root"], str)

    def test_generated_at_is_utc_iso(self, workspace):
        j = Janitor(root=workspace)
        ts = j.summary()["generated_at"]
        assert ts.endswith("Z")

    def test_trash_items_count(self, dirty_workspace):
        j = Janitor(root=dirty_workspace)
        data = j.summary()
        assert data["trash_items"] >= 1

    def test_potential_secrets_detected(self, secret_workspace):
        j = Janitor(root=secret_workspace)
        data = j.summary()
        assert data["potential_secrets"] > 0


# ─────────────────────────────────────────────────────────────────────────────
# CleanReport / SecureReport repr & dict behaviour
# ─────────────────────────────────────────────────────────────────────────────
class TestReportObjects:
    def test_clean_report_is_dict(self, workspace):
        j = Janitor(root=workspace)
        r = j.self_destruct()
        assert isinstance(r, dict)

    def test_secure_report_is_dict(self, workspace):
        j = Janitor(root=workspace)
        r = j.secure_env()
        assert isinstance(r, dict)

    def test_clean_report_json_serialisable(self, workspace):
        j = Janitor(root=workspace)
        r = j.self_destruct()
        json.dumps(dict(r))  # should not raise

    def test_secure_report_json_serialisable(self, workspace):
        j = Janitor(root=workspace)
        r = j.secure_env()
        json.dumps(dict(r))  # should not raise


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────
class TestCLI:
    def test_clean_command(self, dirty_workspace, capsys):
        from siftout.cli import main

        ret = main(["clean", "--root", str(dirty_workspace)])
        assert ret == 0

    def test_clean_dry_run(self, dirty_workspace, capsys):
        from siftout.cli import main

        main(["clean", "--dry-run", "--root", str(dirty_workspace)])
        assert (dirty_workspace / "old.log").exists()

    def test_clean_list_only(self, dirty_workspace, capsys):
        from siftout.cli import main

        ret = main(["clean", "--list", "--root", str(dirty_workspace)])
        assert ret == 0
        assert (dirty_workspace / "old.log").exists()  # not deleted

    def test_clean_json_output(self, dirty_workspace, capsys):
        from siftout.cli import main

        main(["clean", "--json", "--root", str(dirty_workspace)])
        out = capsys.readouterr().out
        parsed = json.loads(out)
        assert "files" in parsed

    def test_secure_command(self, secret_workspace):
        from siftout.cli import main

        ret = main(["secure", "--root", str(secret_workspace)])
        assert ret == 0

    def test_secure_dry_run(self, secret_workspace):
        from siftout.cli import main

        original = (secret_workspace / "app" / "config.py").read_text()
        main(["secure", "--dry-run", "--root", str(secret_workspace)])
        assert (secret_workspace / "app" / "config.py").read_text() == original

    def test_scan_command(self, workspace):
        from siftout.cli import main

        ret = main(["scan", "--root", str(workspace)])
        assert ret == 0

    def test_summary_command(self, workspace):
        from siftout.cli import main

        ret = main(["summary", "--root", str(workspace)])
        assert ret == 0

    def test_summary_json(self, workspace, capsys):
        from siftout.cli import main

        main(["summary", "--json", "--root", str(workspace)])
        out = capsys.readouterr().out
        data = json.loads(out)
        assert "root" in data


# ─────────────────────────────────────────────────────────────────────────────
# Edge cases
# ─────────────────────────────────────────────────────────────────────────────
class TestEdgeCases:
    def test_pattern_with_no_matches(self, workspace):
        j = Janitor(extra_patterns=["*.unicorn"], root=workspace)
        assert j.list_trash() == []

    def test_nested_trash(self, workspace):
        nested = workspace / "deep" / "nested"
        nested.mkdir(parents=True)
        (nested / "file.tmp").write_text("x")
        j = Janitor(root=workspace)
        items = j.list_trash()
        names = [p.name for p in items]
        assert "file.tmp" in names

    def test_unicode_in_paths(self, workspace):
        uni = workspace / "données"
        uni.mkdir()
        (uni / "test.tmp").write_text("données", encoding="utf-8")
        j = Janitor(root=workspace)
        items = j.list_trash()
        assert any("test.tmp" in str(p) for p in items)

    def test_empty_env_entries_no_env_file(self, workspace):
        """secure_env on a workspace with no secrets should not create .env"""
        (workspace / "clean.py").write_text("x = 1\n")
        j = Janitor(root=workspace)
        j.secure_env()
        assert not (workspace / ".env").exists()