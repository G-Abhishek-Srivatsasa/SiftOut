"""
siftout.hardware
~~~~~~~~~~~~~~~~

Core Janitor engine: workspace cleanup, secret detection, and environment hardening.
"""

from __future__ import annotations

import os
import re
import glob
import shutil
import logging
import hashlib
import fnmatch
import platform
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Union

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Default patterns
# ─────────────────────────────────────────────────────────────────────────────
DEFAULT_TRASH_PATTERNS: List[str] = [
    "__pycache__",
    "*.pyc",
    "*.pyo",
    "*.log",
    "*.tmp",
    "*.temp",
    ".DS_Store",
    "Thumbs.db",
    "*.egg-info",
    "dist",
    "build",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "*.coverage",
    ".coverage",
    "htmlcov",
]

# Regex for detecting hardcoded secrets in Python source files
_SECRET_PATTERN = re.compile(
    r'^(?P<indent>\s*)(?P<var>[A-Z0-9_]{3,})\s*=\s*["\'](?P<val>[A-Za-z0-9+/=_\-\.]{20,})["\']',
    re.MULTILINE,
)

# Directories that should never be scanned or mutated
_SKIP_DIRS: frozenset[str] = frozenset(
    {
        "siftout",
        "venv",
        ".venv",
        "env",
        ".env",
        "node_modules",
        ".git",
        "__pycache__",
        "dist",
        "build",
        "site-packages",
    }
)


# ─────────────────────────────────────────────────────────────────────────────
# Result dataclasses (plain dicts with typed helpers for zero extra deps)
# ─────────────────────────────────────────────────────────────────────────────
class CleanReport(dict):
    """Returned by :meth:`Janitor.self_destruct`."""

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"CleanReport(files={self['files']}, folders={self['folders']}, "
            f"errors={self['errors']}, bytes_freed={self['bytes_freed']})"
        )


class SecureReport(dict):
    """Returned by :meth:`Janitor.secure_env`."""

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"SecureReport(secrets_found={self['secrets_found']}, "
            f"files_patched={self['files_patched']}, "
            f"env_entries_written={self['env_entries_written']})"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Janitor
# ─────────────────────────────────────────────────────────────────────────────
class Janitor:
    """
    Siftout's all-in-one workspace hygiene engine.

    Parameters
    ----------
    extra_patterns:
        Additional glob patterns (files *or* directories) to treat as trash.
    root:
        Root directory to operate on. Defaults to the current working directory.
    dry_run:
        When ``True``, **no** files are deleted or modified.  All methods still
        return accurate reports so you can preview changes before committing.
    backup:
        When ``True``, files mutated by :meth:`secure_env` are backed up with a
        ``.siftout.bak`` suffix before being overwritten.
    """

    # ------------------------------------------------------------------
    def __init__(
        self,
        extra_patterns: Optional[Union[str, List[str]]] = None,
        root: Union[str, Path, None] = None,
        dry_run: bool = False,
        backup: bool = True,
    ) -> None:
        self.root = Path(root).resolve() if root else Path.cwd()
        self.dry_run = dry_run
        self.backup = backup

        self.trash_patterns: List[str] = list(DEFAULT_TRASH_PATTERNS)
        if extra_patterns:
            if isinstance(extra_patterns, str):
                extra_patterns = [extra_patterns]
            self.trash_patterns.extend(extra_patterns)

        self._setup_logging()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _setup_logging() -> None:
        if not logging.root.handlers:
            logging.basicConfig(
                level=logging.INFO,
                format="%(asctime)s  %(levelname)-8s  %(message)s",
                datefmt="%H:%M:%S",
            )

    def _glob(self, pattern: str) -> List[Path]:
        """Return all matches for *pattern* under self.root."""
        return [
            Path(p)
            for p in glob.glob(
                str(self.root / "**" / pattern), recursive=True
            )
        ]

    def _path_in_skip_dir(self, path: Path) -> bool:
        parts = set(path.parts)
        return bool(parts & _SKIP_DIRS)

    @staticmethod
    def _dir_size(path: Path) -> int:
        total = 0
        for entry in path.rglob("*"):
            if entry.is_file():
                try:
                    total += entry.stat().st_size
                except OSError:
                    pass
        return total

    @staticmethod
    def _file_hash(path: Path) -> str:
        h = hashlib.sha256()
        with path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def list_trash(self) -> List[Path]:
        """
        Discover all trash items matching :attr:`trash_patterns`.

        Returns
        -------
        list[Path]
            Deduplicated list of matching paths.
        """
        found: set[Path] = set()
        for pattern in self.trash_patterns:
            for match in self._glob(pattern):
                found.add(match)

        results = sorted(found)

        if not results:
            logger.info("[siftout] ✅  Workspace is spotless — nothing to clean.")
        else:
            logger.info("[siftout] 🗑️   Found %d item(s) to clean:", len(results))
            for item in results:
                tag = "DIR " if item.is_dir() else "FILE"
                logger.info("   [%s] %s", tag, item)

        return results

    # ------------------------------------------------------------------
    def self_destruct(self) -> CleanReport:
        """
        Delete everything returned by :meth:`list_trash`.

        Returns
        -------
        CleanReport
            ``{"files": int, "folders": int, "errors": int, "bytes_freed": int}``
        """
        items = self.list_trash()
        files_cleaned = folders_cleaned = errors = bytes_freed = 0

        for item in items:
            try:
                if item.is_dir():
                    size = self._dir_size(item)
                    if not self.dry_run:
                        shutil.rmtree(item)
                    bytes_freed += size
                    folders_cleaned += 1
                    logger.info("[siftout] %s 📁  %s", "DRY" if self.dry_run else "DEL", item)

                elif item.is_file():
                    size = item.stat().st_size
                    if not self.dry_run:
                        item.unlink()
                    bytes_freed += size
                    files_cleaned += 1
                    logger.info("[siftout] %s 📄  %s", "DRY" if self.dry_run else "DEL", item)

            except OSError as exc:
                errors += 1
                logger.error("[siftout] ❌  Could not remove %s: %s", item, exc)

        report = CleanReport(
            files=files_cleaned,
            folders=folders_cleaned,
            errors=errors,
            bytes_freed=bytes_freed,
        )
        logger.info(
            "[siftout] 🧹  Done — %d file(s), %d folder(s) removed  |  %.2f KB freed%s",
            files_cleaned,
            folders_cleaned,
            bytes_freed / 1024,
            "  [DRY RUN]" if self.dry_run else "",
        )
        return report

    # ------------------------------------------------------------------
    def secure_env(self) -> SecureReport:
        """
        Scan Python source files for hardcoded secrets, replace them with
        ``os.getenv(...)`` calls, persist the real values in ``.env``, and
        ensure ``.env`` is listed in ``.gitignore``.

        Returns
        -------
        SecureReport
            ``{"secrets_found": int, "files_patched": int, "env_entries_written": int}``
        """
        py_files = [
            p
            for p in self.root.rglob("*.py")
            if not self._path_in_skip_dir(p) and "setup.py" not in p.name
        ]

        env_entries: Dict[str, str] = {}
        files_patched = 0
        secrets_found = 0

        for file_path in py_files:
            try:
                original = file_path.read_text(encoding="utf-8", errors="ignore")
            except OSError as exc:
                logger.warning("[siftout] Cannot read %s: %s", file_path, exc)
                continue

            new_source, found = self._patch_secrets(original, str(file_path))

            if found:
                secrets_found += len(found)
                env_entries.update(found)
                files_patched += 1

                if not self.dry_run:
                    if self.backup:
                        bak = file_path.with_suffix(file_path.suffix + ".siftout.bak")
                        bak.write_text(original, encoding="utf-8")
                    file_path.write_text(new_source, encoding="utf-8")
                    logger.info("[siftout] 🔐  Patched %s (%d secret(s))", file_path, len(found))
                else:
                    logger.info("[siftout] DRY  Would patch %s (%d secret(s))", file_path, len(found))

        env_entries_written = 0
        if env_entries and not self.dry_run:
            env_entries_written = self._update_env_file(env_entries)
            self._ensure_ignored(".env")

        report = SecureReport(
            secrets_found=secrets_found,
            files_patched=files_patched,
            env_entries_written=env_entries_written,
        )
        logger.info(
            "[siftout] 🛡️   Secure scan done — %d secret(s) across %d file(s)%s",
            secrets_found,
            files_patched,
            "  [DRY RUN]" if self.dry_run else "",
        )
        return report

    # ------------------------------------------------------------------
    def scan_duplicates(self) -> Dict[str, List[Path]]:
        """
        Identify duplicate files (by SHA-256 content hash) under :attr:`root`.

        Returns
        -------
        dict[str, list[Path]]
            Mapping of hash → list of duplicate paths (only groups with ≥ 2 entries).
        """
        hash_map: Dict[str, List[Path]] = {}
        for path in self.root.rglob("*"):
            if path.is_file() and not self._path_in_skip_dir(path):
                try:
                    h = self._file_hash(path)
                    hash_map.setdefault(h, []).append(path)
                except OSError:
                    pass

        duplicates = {h: paths for h, paths in hash_map.items() if len(paths) > 1}
        if duplicates:
            total = sum(len(v) - 1 for v in duplicates.values())
            logger.info("[siftout] 🔍  Found %d duplicate file(s) in %d group(s)", total, len(duplicates))
        else:
            logger.info("[siftout] ✅  No duplicate files found.")
        return duplicates

    # ------------------------------------------------------------------
    def summary(self) -> Dict:
        """
        Return a non-destructive workspace summary (disk usage, trash count,
        potential secrets, duplicates).
        """
        trash = self.list_trash()
        trash_size = sum(
            (self._dir_size(t) if t.is_dir() else t.stat().st_size)
            for t in trash
            if t.exists()
        )

        py_files = [
            p for p in self.root.rglob("*.py")
            if not self._path_in_skip_dir(p)
        ]
        secret_hits: List[str] = []
        for fp in py_files:
            try:
                src = fp.read_text(encoding="utf-8", errors="ignore")
                for m in _SECRET_PATTERN.finditer(src):
                    secret_hits.append(f"{fp}:{m.group('var')}")
            except OSError:
                pass

        duplicates = self.scan_duplicates()

        return {
            "root": str(self.root),
            "platform": platform.system(),
            "trash_items": len(trash),
            "trash_size_bytes": trash_size,
            "potential_secrets": len(secret_hits),
            "secret_locations": secret_hits,
            "duplicate_groups": len(duplicates),
            "generated_at": datetime.utcnow().isoformat() + "Z",
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------
    def _patch_secrets(
        self, source: str, file_label: str
    ) -> tuple[str, Dict[str, str]]:
        """Replace hardcoded secrets in *source* and return (new_source, found)."""
        found: Dict[str, str] = {}
        lines = source.splitlines(keepends=True)
        new_lines: List[str] = []

        for lineno, line in enumerate(lines, 1):
            match = _SECRET_PATTERN.search(line)
            if match and len(match.group("val")) >= 20:
                var = match.group("var")
                val = match.group("val")
                indent = match.group("indent")
                logger.warning(
                    "[siftout] 🚨  Secret detected  %s  →  %s  (line %d)",
                    var,
                    file_label,
                    lineno,
                )
                new_lines.append(f"{indent}{var} = os.getenv('{var}')\n")
                found[var] = val
            else:
                new_lines.append(line)

        if found:
            new_source = "".join(new_lines)
            if "import os" not in new_source:
                new_source = "import os\n" + new_source
            return new_source, found

        return source, found

    def _update_env_file(self, env_entries: Dict[str, str]) -> int:
        env_path = self.root / ".env"
        existing: Dict[str, str] = {}

        if env_path.exists():
            with env_path.open("r", encoding="utf-8") as fh:
                for raw in fh:
                    raw = raw.strip()
                    if "=" in raw and not raw.startswith("#"):
                        k, _, v = raw.partition("=")
                        existing[k.strip()] = v.strip()

        written = 0
        with env_path.open("a", encoding="utf-8") as fh:
            for k, v in env_entries.items():
                if k not in existing:
                    fh.write(f"{k}={v}\n")
                    logger.info("[siftout] 📝  Added %s to .env", k)
                    written += 1

        return written

    def _ensure_ignored(self, filename: str) -> None:
        gitignore = self.root / ".gitignore"
        mode = "a" if gitignore.exists() else "w"

        if mode == "a":
            content = gitignore.read_text(encoding="utf-8")
            # Check for exact line match
            if any(
                line.strip() == filename
                for line in content.splitlines()
            ):
                return

        with gitignore.open(mode, encoding="utf-8") as fh:
            fh.write(f"\n{filename}\n")
        logger.info("[siftout] 📋  Added %s to .gitignore", filename)