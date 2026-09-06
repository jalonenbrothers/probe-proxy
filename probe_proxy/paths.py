"""Data-dir resolution for both layouts.

In a repo checkout (dev), artifacts (probe_results.db, replay/, ...)
live beside the package — keep that behavior. When installed as a tool
(uv tool install / pipx), the package sits in site-packages and MUST
NOT write there: fall back to the current working directory.
"""
from __future__ import annotations

from pathlib import Path

_PKG_DIR = Path(__file__).resolve().parent
_REPO_DIR = _PKG_DIR.parent


def data_dir() -> Path:
    """Repo layout if we're clearly in a checkout, else CWD."""
    if (_REPO_DIR / "probe_results.db").exists() \
            or (_REPO_DIR / ".git").exists() \
            or (_REPO_DIR / "matrix.json").exists():
        return _REPO_DIR
    return Path.cwd()


def repo_file(name: str) -> Path:
    return data_dir() / name