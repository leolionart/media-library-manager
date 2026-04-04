from __future__ import annotations

import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

NETWORK_FILESYSTEMS = {"smbfs", "nfs", "afpfs", "webdav", "cifs", "fusefs_smb"}
MAX_BROWSER_ENTRIES = 300


@dataclass(slots=True)
class MountInfo:
    source: str
    mount_point: Path
    filesystem: str
    is_network: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "mount_point": str(self.mount_point),
            "filesystem": self.filesystem,
            "is_network": self.is_network,
            "label": self.mount_point.name or str(self.mount_point),
        }


def list_mounts() -> list[MountInfo]:
    try:
        result = subprocess.run(["mount"], capture_output=True, text=True, check=False, timeout=3)
    except subprocess.TimeoutExpired:
        return fallback_mounts()
    mounts: list[MountInfo] = []
    for line in result.stdout.splitlines():
        mount = parse_mount_line(line)
        if mount is not None:
            mounts.append(mount)

    if not mounts:
        return fallback_mounts()

    mounts.sort(key=lambda item: (not item.is_network, str(item.mount_point)))
    return mounts


def parse_mount_line(line: str) -> MountInfo | None:
    if " on " not in line or " (" not in line:
        return None
    source, remainder = line.split(" on ", 1)
    mount_text, fs_part = remainder.split(" (", 1)
    filesystem = fs_part.split(",", 1)[0].rstrip(")")
    mount_point = Path(mount_text)
    return MountInfo(
        source=source.strip(),
        mount_point=mount_point,
        filesystem=filesystem,
        is_network=filesystem in NETWORK_FILESYSTEMS,
    )


def browse_path(raw_path: str | None) -> dict[str, Any]:
    path = normalize_browse_path(raw_path)
    if not path.exists():
        raise FileNotFoundError(f"path does not exist: {path}")
    if not path.is_dir():
        raise NotADirectoryError(f"path is not a directory: {path}")

    mounts = list_mounts()
    mount = find_mount_for_path(path, mounts)
    entries = []
    overflow = False

    children = []
    for child in path.iterdir():
        children.append(child)
    children.sort(key=lambda item: (not item.is_dir(), item.name.lower()))

    for index, child in enumerate(children):
        if index >= MAX_BROWSER_ENTRIES:
            overflow = True
            break
        stat = child.stat()
        entries.append(
            {
                "name": child.name,
                "path": str(child.resolve()),
                "type": "directory" if child.is_dir() else "file",
                "size": stat.st_size,
                "modified_at": datetime.fromtimestamp(stat.st_mtime, UTC).isoformat(),
                "suffix": child.suffix.lower(),
            }
        )

    parent = path.parent if path.parent != path else None
    return {
        "path": str(path),
        "parent": str(parent) if parent else None,
        "mount": mount.to_dict() if mount else None,
        "breadcrumbs": build_breadcrumbs(path),
        "entries": entries,
        "overflow": overflow,
        "favorites": build_favorites(mounts),
    }


def normalize_browse_path(raw_path: str | None) -> Path:
    if not raw_path:
        volumes = Path("/Volumes")
        if volumes.exists():
            return volumes.resolve()
        return Path("/").resolve()
    return Path(raw_path).expanduser().resolve()


def build_breadcrumbs(path: Path) -> list[dict[str, str]]:
    crumbs = []
    current = path
    parts = current.parts
    running = Path(parts[0]) if parts else Path("/")
    crumbs.append({"name": running.as_posix() or "/", "path": str(running)})
    for part in parts[1:]:
        running = running / part
        crumbs.append({"name": part, "path": str(running)})
    return crumbs


def build_favorites(mounts: list[MountInfo]) -> list[dict[str, Any]]:
    favorites: list[dict[str, Any]] = []
    seen: set[str] = set()
    for mount in mounts:
        if not mount.is_network:
            continue
        payload = mount.to_dict()
        if payload["mount_point"] in seen:
            continue
        seen.add(payload["mount_point"])
        favorites.append(payload)
    for fallback in [Path("/Volumes"), Path("/")]:
        if fallback.exists() and str(fallback) not in seen:
            favorites.append(
                {
                    "source": "local",
                    "mount_point": str(fallback),
                    "filesystem": "directory",
                    "is_network": False,
                    "label": fallback.name or fallback.as_posix(),
                }
            )
    return favorites


def find_mount_for_path(path: Path, mounts: list[MountInfo]) -> MountInfo | None:
    resolved = path.resolve()
    matched: MountInfo | None = None
    for mount in mounts:
        try:
            resolved.relative_to(mount.mount_point.resolve())
        except ValueError:
            continue
        if matched is None or len(str(mount.mount_point)) > len(str(matched.mount_point)):
            matched = mount
    return matched


def fallback_mounts() -> list[MountInfo]:
    mounts: list[MountInfo] = []
    seen: set[str] = set()
    volumes_root = Path("/Volumes")
    if volumes_root.exists():
        for child in sorted(volumes_root.iterdir(), key=lambda item: item.name.lower()):
            if not child.is_dir():
                continue
            key = str(child)
            if key in seen:
                continue
            seen.add(key)
            mounts.append(
                MountInfo(
                    source="volumes",
                    mount_point=child,
                    filesystem="mountpoint",
                    is_network=False,
                )
            )
    if "/" not in seen:
        mounts.append(MountInfo(source="local", mount_point=Path("/"), filesystem="apfs", is_network=False))
    return mounts
