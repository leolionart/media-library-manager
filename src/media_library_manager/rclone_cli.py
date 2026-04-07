from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_RCLONE_TIMEOUT = 120


class RcloneError(RuntimeError):
    pass


@dataclass(slots=True)
class RcloneCommandResult:
    status: str
    stdout: str
    stderr: str
    returncode: int
    message: str = ""


def build_rclone_target(remote: str, path: str) -> str:
    clean_remote = str(remote or "").strip()
    if not clean_remote:
        raise ValueError("rclone remote is required")
    clean_path = str(path or "").strip().strip("/")
    if not clean_path:
        return f"{clean_remote}:"

    # If path contains a colon, rclone might mistake it for a remote name
    # unless it's explicitly part of the path (e.g., remote:./path:with:colon)
    if ":" in clean_path:
        return f"{clean_remote}:./{clean_path}"
    return f"{clean_remote}:{clean_path}"


def build_target(remote: str, path: str) -> str:
    return build_rclone_target(remote, path)


def run_rclone_command(
    args: list[str],
    *,
    timeout: int = DEFAULT_RCLONE_TIMEOUT,
    expect_json: bool = False,
) -> Any:
    # Use shell execution to ensure rclone CLI receives correctly-escaped paths
    # especially when parentheses and spaces are involved.
    import shlex
    
    # Escape each argument and join into a single command string
    command_str = "rclone " + " ".join(shlex.quote(arg) for arg in args)
    
    try:
        result = subprocess.run(command_str, shell=True, capture_output=True, text=True, check=False, timeout=timeout)
    except FileNotFoundError as exc:
        raise RcloneError("rclone binary is not available in PATH") from exc
    except subprocess.TimeoutExpired as exc:
        raise RcloneError(f"rclone command timed out after {timeout}s") from exc

    stderr_message = (result.stderr or "").strip()
    if result.returncode != 0:
        return RcloneCommandResult(
            status="error",
            stdout=result.stdout or "",
            stderr=result.stderr or "",
            returncode=result.returncode,
            message=stderr_message or f"rclone command failed with exit code {result.returncode}",
        )
    payload = RcloneCommandResult(
        status="success",
        stdout=result.stdout or "",
        stderr=result.stderr or "",
        returncode=result.returncode,
        message=stderr_message,
    )
    if not expect_json:
        return payload
    output = (payload.stdout or "").strip()
    if not output:
        return None
    try:
        return json.loads(output)
    except json.JSONDecodeError as exc:
        raise RcloneError("rclone returned invalid JSON output") from exc


def run_rclone_json(args: list[str], *, timeout: int = DEFAULT_RCLONE_TIMEOUT) -> Any:
    result = run_rclone_command(args, timeout=timeout)
    if result.status != "success":
        raise RcloneError(result.message or "rclone command failed")
    output = (result.stdout or "").strip()
    if not output:
        return None
    try:
        return json.loads(output)
    except json.JSONDecodeError as exc:
        raise RcloneError("rclone returned invalid JSON output") from exc


def list_entries(remote: str, path: str, *, timeout: int = DEFAULT_RCLONE_TIMEOUT) -> list[dict[str, Any]]:
    payload = run_rclone_json(["lsjson", build_rclone_target(remote, path), "--no-mimetype"], timeout=timeout)
    if payload is None:
        return []
    if not isinstance(payload, list):
        raise RcloneError("rclone lsjson returned invalid payload")
    return payload


def list_entries_recursive(
    remote: str,
    path: str,
    *,
    timeout: int = DEFAULT_RCLONE_TIMEOUT,
    dirs_only: bool = False,
    files_only: bool = False,
    fast_list: bool = True,
    include_patterns: list[str] | None = None,
) -> list[dict[str, Any]]:
    args = ["lsjson", build_rclone_target(remote, path), "--recursive", "--no-mimetype"]
    if dirs_only:
        args.append("--dirs-only")
    if files_only:
        args.append("--files-only")
    if fast_list:
        args.append("--fast-list")
    for pattern in include_patterns or []:
        clean_pattern = str(pattern or "").strip()
        if clean_pattern:
            args.extend(["--include", clean_pattern])
    payload = run_rclone_json(args, timeout=timeout)
    if payload is None:
        return []
    if not isinstance(payload, list):
        raise RcloneError("rclone lsjson --recursive returned invalid payload")
    return payload


def is_rclone_not_found_error(error: Exception) -> bool:
    text = str(error).lower()
    return "not found" in text or "directory not found" in text or "object not found" in text


def compute_local_sha256(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
