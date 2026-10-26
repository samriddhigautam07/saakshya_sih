"""Private local document storage helpers."""

import os
from pathlib import Path
import re
import stat
import tempfile
from uuid import uuid4

_STORAGE_KEY = re.compile(r"^[a-f0-9]{32}\.pdf$")
_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def resolve_private_storage_root(configured_path: Path) -> Path:
    """Create a private storage directory outside the repository/frontend tree."""
    root = configured_path.expanduser()
    if not root.is_absolute():
        root = Path.cwd() / root
    root = root.resolve()
    if (
        root == _REPOSITORY_ROOT
        or _REPOSITORY_ROOT in root.parents
        or root in _REPOSITORY_ROOT.parents
    ):
        raise RuntimeError("DOCUMENT_STORAGE_DIR must be outside the project repository.")
    existed = root.exists()
    if existed and not root.is_dir():
        raise RuntimeError("DOCUMENT_STORAGE_DIR must be a dedicated directory.")
    if existed and root.stat().st_mode & 0o077:
        raise RuntimeError("Existing DOCUMENT_STORAGE_DIR must already have owner-only permissions.")
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    return root


def create_temporary_file(storage_root: Path) -> tuple[int, Path]:
    """Create an exclusive, owner-only temporary file inside private storage."""
    descriptor, filename = tempfile.mkstemp(prefix=".upload-", suffix=".tmp", dir=storage_root)
    os.chmod(filename, stat.S_IRUSR | stat.S_IWUSR)
    return descriptor, Path(filename)


def new_storage_key() -> str:
    return f"{uuid4().hex}.pdf"


def resolve_storage_key(storage_root: Path, storage_key: str) -> Path:
    """Resolve only generated flat keys; reject traversal and unexpected names."""
    if not _STORAGE_KEY.fullmatch(storage_key):
        raise ValueError("Invalid storage key.")
    path = (storage_root / storage_key).resolve()
    if path.parent != storage_root:
        raise ValueError("Invalid storage key.")
    return path
