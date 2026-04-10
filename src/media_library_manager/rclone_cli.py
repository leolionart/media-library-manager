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


def list_remotes(*, timeout: int = 30) -> list[dict[str, str]]:
    """List all remotes using rclone listremotes --json."""
    payload = run_rclone_json(["listremotes", "--json"], timeout=timeout)
    if payload is None:
        return []
    if not isinstance(payload, list):
        raise RcloneError("rclone listremotes returned invalid payload")
    return payload


def create_remote(name: str, rclone_type: str, config: dict[str, str], *, timeout: int = 60) -> Any:
    """Create a new remote using rclone config create."""
    args = ["config", "create", name, rclone_type]
    for key, value in config.items():
        args.append(f"{key}={value}")
    return run_rclone_command(args, timeout=timeout)


def delete_remote(name: str, *, timeout: int = 30) -> Any:
    """Delete a remote using rclone config delete."""
    return run_rclone_command(["config", "delete", name], timeout=timeout)


def mount_remote(
    remote: str,
    mount_point: str | Path,
    *,
    vfs_cache_mode: str = "writes",
    allow_other: bool = True,
    read_only: bool = False,
    args: list[str] | None = None,
) -> Any:
    """
    Mount a remote to a local path.
    On non-Windows, uses --daemon.
    """
    import platform
    
    mount_path = Path(mount_point)
    if not mount_path.exists():
        mount_path.mkdir(parents=True, exist_ok=True)
    
    cmd_args = ["mount", f"{remote}:", str(mount_path), "--vfs-cache-mode", vfs_cache_mode]
    if read_only:
        cmd_args.append("--read-only")
    
    is_windows = platform.system().lower() == "windows"
    if not is_windows:
        cmd_args.append("--daemon")
        if allow_other:
            cmd_args.append("--allow-other")
            
    if args:
        cmd_args.extend(args)
        
    return run_rclone_command(cmd_args)


def unmount_path(mount_point: str | Path) -> Any:
    """Unmount a path using system-specific command."""
    import platform
    import subprocess
    
    mount_path = str(mount_point)
    is_windows = platform.system().lower() == "windows"
    
    if is_windows:
        # On Windows, rclone mount usually needs to be killed if not using --daemon (which is not supported)
        # However, rclone unmount is not a thing. We might need to find the process.
        # For now, let's assume we can't easily unmount via CLI without PID.
        raise NotImplementedError("Unmount on Windows is not implemented yet")
        
    # On Linux/macOS
    system = platform.system().lower()
    if system == "darwin":
        cmd = ["umount", mount_path]
    else:
        # Try fusermount3 then fusermount then umount
        try:
            subprocess.run(["fusermount3", "-u", mount_path], check=True, capture_output=True)
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            try:
                subprocess.run(["fusermount", "-u", mount_path], check=True, capture_output=True)
                return True
            except (subprocess.CalledProcessError, FileNotFoundError):
                cmd = ["umount", mount_path]
                
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RcloneError(f"unmount failed: {result.stderr or result.stdout}")
    return True


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
