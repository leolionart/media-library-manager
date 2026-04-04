from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class RootConfig:
    path: Path
    label: str
    priority: int = 50
    kind: str = "mixed"
    connection_id: str = ""
    connection_label: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": str(self.path),
            "label": self.label,
            "priority": self.priority,
            "kind": self.kind,
            "connection_id": self.connection_id,
            "connection_label": self.connection_label,
        }


@dataclass(slots=True)
class MediaFile:
    path: Path
    root_path: Path
    root_label: str
    root_priority: int
    kind: str
    media_key: str
    canonical_name: str
    title: str
    year: int | None
    season: int | None
    episode: int | None
    size: int
    relative_path: str
    resolution: int | None = None
    source: str | None = None
    codec: str | None = None
    dynamic_range: str | None = None
    quality_rank: int = 0
    sha256: str | None = None

    def score_tuple(self) -> tuple[int, int, int, int]:
        return (self.quality_rank, self.size, self.root_priority, -len(self.relative_path))

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["path"] = str(self.path)
        data["root_path"] = str(self.root_path)
        return data


@dataclass(slots=True)
class ScanReport:
    roots: list[RootConfig]
    files: list[MediaFile]
    exact_duplicates: list[dict[str, Any]] = field(default_factory=list)
    media_collisions: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": 1,
            "roots": [root.to_dict() for root in self.roots],
            "summary": {
                "files": len(self.files),
                "exact_duplicate_groups": len(self.exact_duplicates),
                "media_collision_groups": len(self.media_collisions),
            },
            "files": [item.to_dict() for item in self.files],
            "exact_duplicates": self.exact_duplicates,
            "media_collisions": self.media_collisions,
        }


@dataclass(slots=True)
class LibraryTargets:
    movie_root: Path | None = None
    series_root: Path | None = None
    review_root: Path | None = None


@dataclass(slots=True)
class Action:
    type: str
    source: Path
    destination: Path | None
    reason: str
    media_key: str
    root_path: Path
    keep_path: Path | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "source": str(self.source),
            "destination": str(self.destination) if self.destination else None,
            "reason": self.reason,
            "media_key": self.media_key,
            "root_path": str(self.root_path),
            "keep_path": str(self.keep_path) if self.keep_path else None,
            "details": self.details,
        }
