from __future__ import annotations

from pathlib import Path
from typing import Literal, TypedDict


class FSItem(TypedDict):
    name: str
    kind: Literal["dir", "file"]
    size: int | None


class FSError(Exception):
    pass


def _resolve_safe(base: Path, subpath: str | None) -> Path:
    target = base if not subpath else (base / subpath)
    target = target.resolve()
    base = base.resolve()
    if base not in target.parents and target != base:
        raise FSError("Path escapes workspace sandbox")
    return target


def list_dir(workspace_dir: Path, subdir: str | None = None) -> list[FSItem]:
    base = Path(workspace_dir)
    root = _resolve_safe(base, subdir)
    if not root.exists():
        raise FileNotFoundError("Directory not found")
    if not root.is_dir():
        raise NotADirectoryError("Not a directory")
    items: list[FSItem] = []
    for p in sorted(root.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
        try:
            size = p.stat().st_size if p.is_file() else None
        except Exception:
            size = None
        items.append(FSItem(name=p.name, kind="dir" if p.is_dir() else "file", size=size))
    return items


def read_file(workspace_dir: Path, rel_path: str) -> str:
    base = Path(workspace_dir)
    path = _resolve_safe(base, rel_path)
    if not path.exists():
        raise FileNotFoundError("File not found")
    if not path.is_file():
        raise IsADirectoryError("Path is not a file")
    # Only UTF-8 text files
    try:
        data = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as e:
        raise FSError("Unsupported media type; only UTF-8 text allowed") from e
    return data
