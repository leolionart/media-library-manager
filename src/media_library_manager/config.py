from __future__ import annotations

import tomllib
from pathlib import Path

from .models import LibraryTargets, RootConfig


def load_config(config_path: str | Path) -> tuple[list[RootConfig], LibraryTargets]:
    path = Path(config_path).expanduser().resolve()
    data = tomllib.loads(path.read_text(encoding="utf-8"))

    roots_data = data.get("roots", [])
    roots = [
        RootConfig(
            path=Path(item["path"]).expanduser().resolve(),
            label=item.get("label", Path(item["path"]).name),
            priority=int(item.get("priority", 50)),
            kind=item.get("kind", "mixed"),
        )
        for item in roots_data
    ]

    targets_data = data.get("targets", {})
    targets = LibraryTargets(
        movie_root=_path_or_none(targets_data.get("movie_root")),
        series_root=_path_or_none(targets_data.get("series_root")),
        review_root=_path_or_none(targets_data.get("review_root")),
    )
    return roots, targets


def _path_or_none(raw: str | None) -> Path | None:
    if not raw:
        return None
    return Path(raw).expanduser().resolve()
