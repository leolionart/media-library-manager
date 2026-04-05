from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from typing import Any


class RcloneError(RuntimeError):
    pass


@dataclass(slots=True)
class RcloneCommandResult:
    stdout: str
    stderr: str


def build_rclone_target(*, remote: str, path: str) -> str:
    clean_remote = str(remote or "").strip().strip("/")
    if not clean_remote:
        raise RcloneError("rclone remote is required")
    normalized = _normalize_rclone_path(path)
    rel = normalized.strip("/")
    return f"{clean_remote}:{rel}" if rel else f"{clean_remote}:"


def run_rclone(args: list[str], *, timeout: int = 30) -> RcloneCommandResult:
    command = ["rclone", *args]
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        raise RcloneError("rclone command not found in PATH") from exc
    except subprocess.TimeoutExpired as exc:
        raise RcloneError(f"rclone command timed out after {timeout}s: {' '.join(command)}") from exc

    if completed.returncode != 0:
        message = (completed.stderr or completed.stdout or "").strip() or f"rclone command failed: {' '.join(command)}"
        raise RcloneError(message)
    return RcloneCommandResult(stdout=completed.stdout or "", stderr=completed.stderr or "")


def run_rclone_json(args: list[str], *, timeout: int = 30) -> Any:
    result = run_rclone(args, timeout=timeout)
    text = (result.stdout or "").strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise RcloneError("rclone returned invalid JSON output") from exc


def is_rclone_not_found_error(error: Exception) -> bool:
    text = str(error).lower()
    return "not found" in text or "directory not found" in text or "object not found" in text


def _normalize_rclone_path(value: str) -> str:
    text = str(value or "").strip()
    if not text or text == ".":
        return "/"
    return "/" + text.strip("/")
