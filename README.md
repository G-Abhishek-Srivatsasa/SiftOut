# Siftout

> **Smart, automated workspace cleaner and security hardener for Python projects.**
<div align="center">

<!-- Logo -->
<p align="center">
  <img src="https://siftout-logo.vercel.app/" alt="SiftOut" width="180">
</p>

Once you image is online on a webpage, add this type of line on your readme.md's first line
[![PyPI version](https://img.shields.io/pypi/v/siftout?color=blue)](https://pypi.org/project/siftout/)
[![Python versions](https://img.shields.io/pypi/pyversions/siftout)](https://pypi.org/project/siftout/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-passing-brightgreen)]()
[![Coverage](https://img.shields.io/badge/coverage-≥85%25-brightgreen)]()

---

Siftout is a zero-dependency Python library and CLI that does two things really well:

1. **Cleans** your workspace — removes `__pycache__`, `.log`, `.tmp`, `.pyc`, `dist/`, `build/`, and anything else you tell it to.
2. **Secures** your codebase — scans Python source files for hardcoded secrets, replaces them with `os.getenv()` calls, writes the real values to `.env`, and ensures `.env` is in `.gitignore`.

Plus a duplicate-file scanner and workspace health summary — all with a beautiful CLI and a fully typed API.

---

## Table of Contents

- [Installation](#installation)
- [Quick Start](#quick-start)
- [Python API](#python-api)
  - [Janitor](#janitor)
  - [self_destruct](#self_destruct)
  - [secure_env](#secure_env)
  - [scan_duplicates](#scan_duplicates)
  - [summary](#summary)
- [CLI Reference](#cli-reference)
- [Configuration](#configuration)
- [Development](#development)
- [Authors](#authors)
- [License](#license)

---

## Installation

```bash
pip install siftout
```

Siftout has **zero runtime dependencies** — it uses only the Python standard library.

---

## Quick Start

### As a library

```python
from siftout import Janitor

j = Janitor(extra_patterns=["*.bak", "*.swp"])

# Preview what would be removed (no actual deletion)
trash = j.list_trash()

# Delete all trash
report = j.self_destruct()
print(report)
# CleanReport(files=12, folders=3, errors=0, bytes_freed=204800)

# Scan for and fix hardcoded secrets
secure_report = j.secure_env()
print(secure_report)
# SecureReport(secrets_found=2, files_patched=1, env_entries_written=2)
```

### As a CLI

```bash
# Clean the current workspace
siftout clean

# Preview what would be deleted (no changes made)
siftout clean --dry-run

# Detect & remove hardcoded secrets
siftout secure

# Find duplicate files
siftout scan

# Full workspace health report
siftout summary

# Get JSON output (great for CI pipelines)
siftout clean --json
```

---

## Python API

### `Janitor`

```python
Janitor(
    extra_patterns=None,   # str | list[str] | None  — extra glob patterns to treat as trash
    root=None,             # str | Path | None        — root directory (default: cwd)
    dry_run=False,         # bool                     — preview without changing anything
    backup=True,           # bool                     — back up patched files before modifying
)
```

| Parameter        | Type                       | Default | Description                                                         |
| ---------------- | -------------------------- | ------- | ------------------------------------------------------------------- |
| `extra_patterns` | `str \| list[str] \| None` | `None`  | Additional glob patterns (e.g. `"*.bak"`)                           |
| `root`           | `str \| Path \| None`      | `cwd`   | Root directory to operate on                                        |
| `dry_run`        | `bool`                     | `False` | If `True`, nothing is modified — reports still reflect real counts  |
| `backup`         | `bool`                     | `True`  | If `True`, `.siftout.bak` files are created before patching secrets |

---

### `self_destruct`

Deletes every file and folder matched by the configured patterns.

```python
report = j.self_destruct()
# {"files": 8, "folders": 2, "errors": 0, "bytes_freed": 131072}
```

**Default patterns removed:**

| Pattern                 | What it targets                   |
| ----------------------- | --------------------------------- |
| `__pycache__`           | Python bytecode cache directories |
| `*.pyc` / `*.pyo`       | Compiled Python files             |
| `*.log`                 | Log files                         |
| `*.tmp` / `*.temp`      | Temporary files                   |
| `.DS_Store`             | macOS metadata                    |
| `Thumbs.db`             | Windows thumbnail cache           |
| `*.egg-info`            | Package build artifacts           |
| `dist` / `build`        | Distribution directories          |
| `.pytest_cache`         | Pytest cache                      |
| `.mypy_cache`           | Mypy cache                        |
| `.ruff_cache`           | Ruff cache                        |
| `.coverage` / `htmlcov` | Coverage reports                  |

---

### `secure_env`

Scans all `*.py` files (excluding `siftout/`, `venv/`, `.git/`, etc.) for hardcoded secrets — variables whose value is ≥ 20 characters long. Replaces them in-place with `os.getenv(...)`, writes values to `.env`, and adds `.env` to `.gitignore`.

```python
report = j.secure_env()
# {"secrets_found": 3, "files_patched": 2, "env_entries_written": 3}
```

**Before:**

```python
STRIPE_API_KEY = 'sk_live_abcdef1234567890xyz'
```

**After:**

```python
import os
STRIPE_API_KEY = os.getenv('STRIPE_API_KEY')
```

**`.env` (auto-created):**

```dotenv
STRIPE_API_KEY=sk_live_abcdef1234567890xyz
```

---

### `scan_duplicates`

Identifies duplicate files by SHA-256 content hash.

```python
dupes = j.scan_duplicates()
# {
#   "a1b2c3...": [Path("copy1.txt"), Path("copy2.txt")],
# }
```

---

### `summary`

Returns a non-destructive workspace health report — no files are modified.

```python
data = j.summary()
# {
#   "root": "/home/user/myproject",
#   "platform": "Linux",
#   "trash_items": 14,
#   "trash_size_bytes": 204800,
#   "potential_secrets": 2,
#   "secret_locations": ["app/config.py:API_KEY"],
#   "duplicate_groups": 1,
#   "generated_at": "2025-01-15T12:00:00Z",
# }
```

---

## CLI Reference

```
siftout [COMMAND] [OPTIONS]

Commands:
  clean    Delete trash files and folders
  secure   Detect and remove hardcoded secrets
  scan     Find duplicate files
  summary  Workspace health overview

Global options:
  --root DIR          Root directory (default: cwd)
  --patterns GLOB...  Extra glob patterns to include
  --dry-run           Preview changes without modifying anything
  --json              Output report as JSON
  --verbose / -v      Enable verbose logging
  --version           Show version
  --help              Show help
```

### `siftout clean`

```bash
siftout clean                          # Clean current directory
siftout clean --root ./myproject       # Clean a specific directory
siftout clean --patterns "*.bak" "*.swp"   # Extra patterns
siftout clean --dry-run                # Preview only
siftout clean --list                   # List items without deleting
siftout clean --json                   # JSON output
```

### `siftout secure`

```bash
siftout secure                         # Scan and patch secrets
siftout secure --dry-run               # Preview only
siftout secure --no-backup             # Skip .siftout.bak backups
siftout secure --json                  # JSON output
```

### `siftout scan`

```bash
siftout scan                           # Find duplicate files
siftout scan --json                    # JSON output
```

### `siftout summary`

```bash
siftout summary                        # Health overview
siftout summary --json                 # JSON output (great for dashboards)
```

---

## Configuration

Siftout is configured via `pyproject.toml`:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]

[tool.coverage.report]
fail_under = 85
```

No Siftout-specific config file is needed — all options are passed directly to `Janitor()` or the CLI.

---

## Development

```bash
# Clone
git clone https://github.com/Abhishek-Srivatsasa/SiftOut.git
cd SiftOut

# Install in editable mode with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run tests with coverage
pytest --cov=siftout --cov-report=term-missing

# Lint
ruff check siftout tests

# Type check
mypy siftout
```

### Project layout

```
SIFTOUT/
├── siftout/
│   ├── __init__.py      # Public API exports
│   ├── hardware.py      # Core Janitor engine
│   └── cli.py           # Command-line interface
├── tests/
│   ├── conftest.py      # Pytest fixtures
│   └── test_siftout.py  # Full test suite
├── testings/
│   ├── try.py           # Manual smoke test script
│   └── test_secret.py   # Example file with env var usage
├── pyproject.toml       # Build, lint, test, type config
└── README.md
```

---

## Authors

**Abhishek Srivatsasa Guntur**

- GitHub: [@Abhishek-Srivatsasa](https://github.com/Abhishek-Srivatsasa)
- Email: gabhisheksrivatsasa@gmail.com

**Devansh Singh**

- LinkedIn: [linkedin.com/in/devansh050607](https://linkedin.com/in/devansh050607)
- Email: devansh.jay.singh@gmail.com

---

## License

[MIT](LICENSE) © 2026 Abhishek Srivatsasa Guntur & Devansh Singh

