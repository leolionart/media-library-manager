from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Callable

from .models import MediaFile, RootConfig, ScanReport
from .scanner_storage import LocalPathScannerStorage, ScannedFileEntry, ScannerStorageBackend

VIDEO_EXTENSIONS = {
    ".mkv",
    ".mp4",
    ".avi",
    ".m4v",
    ".mov",
    ".wmv",
    ".mpg",
    ".mpeg",
    ".ts",
    ".m2ts",
    ".iso",
}

SIDECAR_EXTENSIONS = {
    ".srt",
    ".ass",
    ".ssa",
    ".sub",
    ".idx",
    ".nfo",
    ".jpg",
    ".jpeg",
    ".png",
}

NOISE_WORDS = {
    "2160p",
    "1080p",
    "720p",
    "480p",
    "bluray",
    "blu",
    "ray",
    "bdrip",
    "brrip",
    "remux",
    "web",
    "webdl",
    "web-dl",
    "webrip",
    "hdtv",
    "dvdrip",
    "hdrip",
    "x264",
    "x265",
    "h264",
    "h265",
    "hevc",
    "av1",
    "hdr",
    "dv",
    "dolbyvision",
    "atmos",
    "proper",
    "repack",
    "extended",
    "criterion",
    "multi",
    "subs",
    "dubbed",
    "internal",
    "readnfo",
    "10bit",
    "8bit",
}

SOURCE_RANKS = {
    "remux": 120,
    "bluray": 100,
    "bdrip": 80,
    "web-dl": 70,
    "webdl": 70,
    "webrip": 60,
    "hdtv": 40,
    "dvdrip": 30,
}

CODEC_RANKS = {
    "av1": 40,
    "x265": 35,
    "hevc": 35,
    "h265": 35,
    "x264": 20,
    "h264": 20,
}

DYNAMIC_RANGE_RANKS = {
    "dv": 20,
    "dolbyvision": 20,
    "hdr": 15,
}

EPISODE_RE = re.compile(r"(?i)\bS(?P<season>\d{1,2})E(?P<episode>\d{1,3})\b|\b(?P<season2>\d{1,2})x(?P<episode2>\d{1,3})\b")
YEAR_RE = re.compile(r"\b(19\d{2}|20\d{2})\b")
RESOLUTION_RE = re.compile(r"\b(2160|1080|720|576|480)p\b", re.IGNORECASE)
SOURCE_RE = re.compile(r"\b(remux|bluray|bdrip|web-dl|webdl|webrip|hdtv|dvdrip)\b", re.IGNORECASE)
CODEC_RE = re.compile(r"\b(av1|x265|hevc|h265|x264|h264)\b", re.IGNORECASE)
DYNAMIC_RANGE_RE = re.compile(r"\b(dolbyvision|dv|hdr)\b", re.IGNORECASE)
SEPARATORS_RE = re.compile(r"[._]+")
BRACKETS_RE = re.compile(r"[\[\](){}]")
MULTISPACE_RE = re.compile(r"\s+")


ScanProgressCallback = Callable[[dict[str, object]], None]


def scan_roots(
    roots: list[RootConfig],
    *,
    progress_callback: ScanProgressCallback | None = None,
    storage_backend: ScannerStorageBackend | None = None,
) -> ScanReport:
    files: list[MediaFile] = []
    size_groups: dict[int, list[MediaFile]] = defaultdict(list)
    hash_entries: dict[int, ScannedFileEntry] = {}
    total_roots = len(roots)
    total_files = 0
    backend = storage_backend or LocalPathScannerStorage()

    for index, root in enumerate(roots, start=1):
        root_file_count = 0
        if progress_callback:
            progress_callback(
                {
                    "event": "root_started",
                    "index": index,
                    "total_roots": total_roots,
                    "root_label": root.label,
                    "root_path": str(root.path),
                    "total_indexed_files": total_files,
                }
            )
        for entry in backend.iter_video_files(root, allowed_suffixes=VIDEO_EXTENSIONS):
            media = inspect_media_file(entry, root)
            files.append(media)
            size_groups[media.size].append(media)
            hash_entries[id(media)] = entry
            root_file_count += 1
            total_files += 1
        if progress_callback:
            progress_callback(
                {
                    "event": "root_completed",
                    "index": index,
                    "total_roots": total_roots,
                    "root_label": root.label,
                    "root_path": str(root.path),
                    "indexed_files": root_file_count,
                    "total_indexed_files": total_files,
                }
            )

    exact_groups = build_exact_duplicate_groups(
        size_groups,
        sha256_for=lambda item: backend.compute_sha256(hash_entries[id(item)]) if id(item) in hash_entries else compute_sha256(item.path),
    )
    media_groups = build_media_collision_groups(files)
    if progress_callback:
        progress_callback(
            {
                "event": "scan_completed",
                "total_roots": total_roots,
                "total_indexed_files": total_files,
                "exact_duplicate_groups": len(exact_groups),
                "media_collision_groups": len(media_groups),
            }
        )
    return ScanReport(roots=roots, files=files, exact_duplicates=exact_groups, media_collisions=media_groups)


def inspect_media_file(entry: ScannedFileEntry, root: RootConfig) -> MediaFile:
    details = parse_media_details_from_names(entry.stem, entry.parent_name)
    storage_uri = entry.path if entry.path.startswith(("local://", "smb://")) else ""
    media = MediaFile(
        path=Path(entry.path),
        root_path=root.path,
        root_label=root.label,
        root_priority=root.priority,
        kind=details["kind"],
        media_key=details["media_key"],
        canonical_name=details["canonical_name"],
        title=details["title"],
        year=details["year"],
        season=details["season"],
        episode=details["episode"],
        size=entry.size,
        relative_path=entry.relative_path,
        resolution=details["resolution"],
        source=details["source"],
        codec=details["codec"],
        dynamic_range=details["dynamic_range"],
        quality_rank=details["quality_rank"],
        storage_uri=storage_uri,
        root_storage_uri=root.storage_uri,
    )
    return media


def build_exact_duplicate_groups(
    size_groups: dict[int, list[MediaFile]],
    *,
    sha256_for: Callable[[MediaFile], str] | None = None,
) -> list[dict[str, object]]:
    groups: list[dict[str, object]] = []
    for size, items in size_groups.items():
        if len(items) < 2:
            continue
        hash_groups: dict[str, list[MediaFile]] = defaultdict(list)
        for item in items:
            item.sha256 = item.sha256 or (sha256_for(item) if sha256_for else compute_sha256(item.path))
            hash_groups[item.sha256].append(item)
        for sha256, hashed_items in hash_groups.items():
            if len(hashed_items) < 2:
                continue
            groups.append(
                {
                    "sha256": sha256,
                    "size": size,
                    "media_keys": sorted({item.media_key for item in hashed_items}),
                    "items": [item.to_dict() for item in sorted(hashed_items, key=lambda file: str(file.path))],
                }
            )
    groups.sort(key=lambda group: (group["size"], json.dumps(group["media_keys"])))
    return groups


def build_media_collision_groups(files: list[MediaFile]) -> list[dict[str, object]]:
    grouped: dict[str, list[MediaFile]] = defaultdict(list)
    for item in files:
        grouped[item.media_key].append(item)

    groups: list[dict[str, object]] = []
    for media_key, items in grouped.items():
        if len(items) < 2:
            continue
        groups.append(
            {
                "media_key": media_key,
                "kind": items[0].kind,
                "canonical_name": items[0].canonical_name,
                "items": [item.to_dict() for item in sorted(items, key=lambda file: file.score_tuple(), reverse=True)],
            }
        )
    groups.sort(key=lambda group: group["media_key"])
    return groups


def parse_media_details(path: Path | str) -> dict[str, object]:
    path_obj = Path(path)
    stem = path_obj.stem
    parent = path_obj.parent.name
    return parse_media_details_from_names(stem, parent)


def parse_media_details_from_names(stem: str, parent: str) -> dict[str, object]:
    stem_clean = clean_text(stem)
    parent_clean = clean_text(parent)

    episode_match = EPISODE_RE.search(stem_clean) or EPISODE_RE.search(parent_clean)
    if episode_match:
        season = int(episode_match.group("season") or episode_match.group("season2"))
        episode = int(episode_match.group("episode") or episode_match.group("episode2"))
        title_source = stem_clean[: episode_match.start()].strip() or parent_clean
        title = normalize_title(title_source)
        canonical_name = f"{title} - S{season:02d}E{episode:02d}"
        media_key = f"episode:{slugify(title)}:s{season:02d}e{episode:02d}"
        return finalize_details(
            kind="series",
            media_key=media_key,
            canonical_name=canonical_name,
            title=title,
            year=None,
            season=season,
            episode=episode,
            stem_clean=stem_clean,
            parent_clean=parent_clean,
        )

    title_source = stem_clean
    year = extract_year(stem_clean)
    if year is None:
        year = extract_year(parent_clean)
        if year is not None:
            title_source = parent_clean

    title = normalize_title(text_before_year_or_noise(title_source))
    canonical_name = f"{title} ({year})" if year else title
    media_key = f"movie:{slugify(title)}:{year if year else 'unknown'}"
    return finalize_details(
        kind="movie",
        media_key=media_key,
        canonical_name=canonical_name,
        title=title,
        year=year,
        season=None,
        episode=None,
        stem_clean=stem_clean,
        parent_clean=parent_clean,
    )


def finalize_details(
    *,
    kind: str,
    media_key: str,
    canonical_name: str,
    title: str,
    year: int | None,
    season: int | None,
    episode: int | None,
    stem_clean: str,
    parent_clean: str,
) -> dict[str, object]:
    haystack = f"{stem_clean} {parent_clean}".strip()
    resolution_match = RESOLUTION_RE.search(haystack)
    source_match = SOURCE_RE.search(haystack)
    codec_match = CODEC_RE.search(haystack)
    dynamic_range_match = DYNAMIC_RANGE_RE.search(haystack)

    resolution = int(resolution_match.group(1)) if resolution_match else None
    source = source_match.group(1).lower() if source_match else None
    codec = codec_match.group(1).lower() if codec_match else None
    dynamic_range = dynamic_range_match.group(1).lower() if dynamic_range_match else None

    quality_rank = 0
    quality_rank += resolution_rank(resolution)
    quality_rank += SOURCE_RANKS.get(source or "", 0)
    quality_rank += CODEC_RANKS.get(codec or "", 0)
    quality_rank += DYNAMIC_RANGE_RANKS.get(dynamic_range or "", 0)

    return {
        "kind": kind,
        "media_key": media_key,
        "canonical_name": canonical_name,
        "title": title,
        "year": year,
        "season": season,
        "episode": episode,
        "resolution": resolution,
        "source": source,
        "codec": codec,
        "dynamic_range": dynamic_range,
        "quality_rank": quality_rank,
    }


def resolution_rank(resolution: int | None) -> int:
    if not resolution:
        return 0
    mapping = {480: 10, 576: 12, 720: 20, 1080: 30, 2160: 40}
    return mapping.get(resolution, 0)


def extract_year(text: str) -> int | None:
    match = YEAR_RE.search(text)
    if not match:
        return None
    return int(match.group(1))


def text_before_year_or_noise(text: str) -> str:
    year_match = YEAR_RE.search(text)
    if year_match:
        return text[: year_match.start()].strip()
    parts = text.split()
    collected: list[str] = []
    for part in parts:
        normalized = re.sub(r"[^a-z0-9]", "", part.lower())
        if normalized in NOISE_WORDS:
            break
        collected.append(part)
    return " ".join(collected).strip()


def normalize_title(text: str) -> str:
    text = clean_text(text)
    if not text:
        return "Unknown"
    return " ".join(part.capitalize() for part in text.split())


def clean_text(text: str) -> str:
    text = SEPARATORS_RE.sub(" ", text)
    text = BRACKETS_RE.sub(" ", text)
    text = MULTISPACE_RE.sub(" ", text)
    return text.strip()


def slugify(text: str) -> str:
    cleaned = clean_text(text).lower()
    return re.sub(r"[^a-z0-9]+", "-", cleaned).strip("-") or "unknown"


def compute_sha256(path: Path | str) -> str:
    digest = hashlib.sha256()
    path_obj = Path(path)
    with path_obj.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def companion_files(path: Path) -> list[Path]:
    companions: list[Path] = []
    for sibling in path.parent.iterdir():
        if sibling == path or not sibling.is_file():
            continue
        if sibling.stem != path.stem:
            continue
        if sibling.suffix.lower() in SIDECAR_EXTENSIONS:
            companions.append(sibling)
    return sorted(companions, key=lambda item: item.name)
