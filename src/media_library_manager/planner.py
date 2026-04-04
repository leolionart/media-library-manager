from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import Action, LibraryTargets, MediaFile, RootConfig, ScanReport


def plan_actions(
    report: ScanReport,
    targets: LibraryTargets,
    *,
    delete_lower_quality: bool = False,
) -> dict[str, Any]:
    actions: list[Action] = []
    handled_sources: set[str] = set()

    exact_entries = [
        [media_from_dict(item) for item in group["items"]]
        for group in report.exact_duplicates
    ]
    for items in exact_entries:
        keeper = choose_keeper(items)
        keeper_source = keeper.path
        desired_destination = build_destination_path(keeper, targets)
        if desired_destination and desired_destination != keeper.path:
            actions.append(
                Action(
                    type="move",
                    source=keeper.path,
                    destination=desired_destination,
                    reason="canonicalize_best_exact_duplicate",
                    media_key=keeper.media_key,
                    root_path=keeper.root_path,
                    keep_path=desired_destination,
                    details=build_action_details(keeper, targets),
                )
            )
            keeper = clone_with_path(keeper, desired_destination)
        handled_sources.add(str(keeper_source))

        for item in items:
            if item.path == keeper_source:
                continue
            actions.append(
                Action(
                    type="delete",
                    source=item.path,
                    destination=None,
                    reason="exact_duplicate",
                    media_key=item.media_key,
                    root_path=item.root_path,
                    keep_path=keeper.path,
                    details=build_action_details(item, targets),
                )
            )
            handled_sources.add(str(item.path))

    for collision in report.media_collisions:
        items = [media_from_dict(item) for item in collision["items"]]
        keeper = choose_keeper(items)
        keeper_source = keeper.path
        desired_destination = build_destination_path(keeper, targets)
        if desired_destination and desired_destination != keeper.path and str(keeper_source) not in handled_sources:
            actions.append(
                Action(
                    type="move",
                    source=keeper.path,
                    destination=desired_destination,
                    reason="canonicalize_best_media",
                    media_key=keeper.media_key,
                    root_path=keeper.root_path,
                    keep_path=desired_destination,
                    details=build_action_details(keeper, targets),
                )
            )
            keeper = clone_with_path(keeper, desired_destination)
            handled_sources.add(str(keeper_source))

        for item in items:
            if item.path == keeper_source or str(item.path) in handled_sources:
                continue
            action_type = "delete" if delete_lower_quality else "review"
            reason = "lower_quality_duplicate" if delete_lower_quality else "manual_review_same_media"
            destination = None
            if action_type == "review" and targets.review_root:
                destination = build_review_path(item, targets.review_root)
            actions.append(
                Action(
                    type=action_type,
                    source=item.path,
                    destination=destination,
                    reason=reason,
                    media_key=item.media_key,
                    root_path=item.root_path,
                    keep_path=keeper.path,
                    details={
                        **build_action_details(item, targets),
                        "keeper_quality_rank": keeper.quality_rank,
                        "candidate_quality_rank": item.quality_rank,
                    },
                )
            )
            handled_sources.add(str(item.path))

    serialized = [action.to_dict() for action in actions]
    return {
        "version": 1,
        "summary": summarize_actions(actions),
        "actions": serialized,
    }


def choose_keeper(items: list[MediaFile]) -> MediaFile:
    return max(items, key=lambda item: item.score_tuple())


def build_destination_path(item: MediaFile, targets: LibraryTargets) -> Path | None:
    root = targets.series_root if item.kind == "series" else targets.movie_root
    if root is None:
        return None
    if item.kind == "series":
        season_dir = f"Season {item.season:02d}" if item.season is not None else "Season 01"
        show_dir = item.title
        file_name = f"{item.canonical_name}{item.path.suffix.lower()}"
        return root / show_dir / season_dir / file_name
    file_name = f"{item.canonical_name}{item.path.suffix.lower()}"
    return root / item.canonical_name / file_name


def build_review_path(item: MediaFile, review_root: Path) -> Path:
    return review_root / item.kind / item.canonical_name / item.path.name


def build_action_details(item: MediaFile, targets: LibraryTargets) -> dict[str, Any]:
    details: dict[str, Any] = {
        "canonical_name": item.canonical_name,
        "kind": item.kind,
        "title": item.title,
        "year": item.year,
        "season": item.season,
        "episode": item.episode,
    }
    if item.kind == "movie" and targets.movie_root:
        details["target_root"] = str(targets.movie_root)
    if item.kind == "series" and targets.series_root:
        details["target_root"] = str(targets.series_root)
    return details


def media_from_dict(data: dict[str, Any]) -> MediaFile:
    root = RootConfig(
        path=Path(data["root_path"]),
        label=data["root_label"],
        priority=int(data["root_priority"]),
        kind=data["kind"],
    )
    report_item = MediaFile(
        path=Path(data["path"]),
        root_path=root.path,
        root_label=root.label,
        root_priority=root.priority,
        kind=data["kind"],
        media_key=data["media_key"],
        canonical_name=data["canonical_name"],
        title=data["title"],
        year=data.get("year"),
        season=data.get("season"),
        episode=data.get("episode"),
        size=int(data["size"]),
        relative_path=data["relative_path"],
        resolution=data.get("resolution"),
        source=data.get("source"),
        codec=data.get("codec"),
        dynamic_range=data.get("dynamic_range"),
        quality_rank=int(data.get("quality_rank", 0)),
        sha256=data.get("sha256"),
    )
    return report_item


def clone_with_path(item: MediaFile, new_path: Path) -> MediaFile:
    payload = item.to_dict()
    payload["path"] = str(new_path)
    try:
        payload["relative_path"] = str(new_path.relative_to(item.root_path))
    except ValueError:
        payload["relative_path"] = new_path.name
    return media_from_dict(payload)


def summarize_actions(actions: list[Action]) -> dict[str, int]:
    summary = {"move": 0, "delete": 0, "review": 0}
    for action in actions:
        summary[action.type] = summary.get(action.type, 0) + 1
    return summary


def save_plan(plan: dict[str, Any], output_path: str | Path) -> None:
    path = Path(output_path)
    path.write_text(json.dumps(plan, indent=2, sort_keys=True), encoding="utf-8")


def load_report(report_path: str | Path) -> ScanReport:
    data = json.loads(Path(report_path).read_text(encoding="utf-8"))
    roots = [
        RootConfig(
            path=Path(root["path"]),
            label=root["label"],
            priority=int(root["priority"]),
            kind=root.get("kind", "mixed"),
        )
        for root in data["roots"]
    ]
    files = [media_from_dict(item) for item in data["files"]]
    return ScanReport(
        roots=roots,
        files=files,
        exact_duplicates=data["exact_duplicates"],
        media_collisions=data["media_collisions"],
    )
