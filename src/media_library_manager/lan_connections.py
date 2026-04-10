from __future__ import annotations

import re
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any


SMB_CONNECTION_KEYS = [
    "id",
    "label",
    "protocol",
    "host",
    "port",
    "share_name",
    "base_path",
    "username",
    "password",
    "domain",
    "version",
    "enabled",
]

RCLONE_CONNECTION_KEYS = [
    "id",
    "label",
    "protocol",
    "rclone_name",
    "config",
    "enabled",
]


SMBCLIENT_MISSING_MESSAGE = (
    "smbclient is not installed in the runtime. "
    "Install the Samba client for local runs, or use the Docker image which already includes smbclient."
)


def default_lan_connections() -> dict[str, Any]:
    return {"smb": [], "rclone": []}


def default_smb_connection() -> dict[str, Any]:
    return {
        "id": "",
        "label": "",
        "protocol": "smb",
        "host": "",
        "port": 445,
        "share_name": "",
        "base_path": "",
        "username": "",
        "password": "",
        "domain": "",
        "version": "3.0",
        "enabled": True,
    }


def default_rclone_connection() -> dict[str, Any]:
    return {
        "id": "",
        "label": "",
        "protocol": "rclone",
        "rclone_name": "",
        "config": {},
        "enabled": True,
    }


def normalize_lan_connections(raw: dict[str, Any] | None) -> dict[str, Any]:
    normalized = default_lan_connections()
    raw = raw or {}
    normalized["smb"] = [normalize_stored_smb_connection(item) for item in raw.get("smb", [])]
    normalized["rclone"] = [normalize_stored_rclone_connection(item) for item in raw.get("rclone", [])]
    return normalized


def normalize_stored_smb_connection(connection: dict[str, Any]) -> dict[str, Any]:
    normalized = default_smb_connection()
    normalized.update({key: connection.get(key, normalized.get(key)) for key in SMB_CONNECTION_KEYS})
    normalized["id"] = str(normalized.get("id") or f"smb-{time.time_ns()}")
    normalized["label"] = str(normalized.get("label") or "").strip()
    normalized["protocol"] = "smb"
    normalized["host"] = str(normalized.get("host") or "").strip()
    normalized["port"] = int(normalized.get("port") or 445)
    normalized["share_name"] = str(normalized.get("share_name") or "").strip().strip("/")
    normalized["base_path"] = normalize_share_path(str(normalized.get("base_path") or ""))
    normalized["username"] = str(normalized.get("username") or "").strip()
    normalized["password"] = str(normalized.get("password") or "")
    normalized["domain"] = str(normalized.get("domain") or "").strip()
    normalized["version"] = str(normalized.get("version") or "3.0").strip() or "3.0"
    normalized["enabled"] = bool(normalized.get("enabled", True))
    if not normalized["label"]:
        target = normalized["share_name"] or normalized["host"] or normalized["id"]
        normalized["label"] = f"SMB {target}"
    return normalized


def normalize_stored_rclone_connection(connection: dict[str, Any]) -> dict[str, Any]:
    normalized = default_rclone_connection()
    normalized.update({key: connection.get(key, normalized.get(key)) for key in RCLONE_CONNECTION_KEYS})
    normalized["id"] = str(normalized.get("id") or f"rclone-{time.time_ns()}")
    normalized["label"] = str(normalized.get("label") or "").strip()
    normalized["protocol"] = "rclone"
    normalized["rclone_name"] = str(normalized.get("rclone_name") or "").strip()
    normalized["config"] = dict(normalized.get("config") or {})
    normalized["enabled"] = bool(normalized.get("enabled", True))
    if not normalized["label"]:
        normalized["label"] = f"Rclone {normalized['rclone_name'] or normalized['id']}"
    return normalized


def normalize_share_path(value: str) -> str:
    value = value.strip()
    if not value:
        return ""
    return "/" + value.strip("/")


def upsert_smb_connection(connections: dict[str, Any], payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    normalized = normalize_lan_connections(connections)
    existing_index = next((index for index, item in enumerate(normalized["smb"]) if item["id"] == payload.get("id")), None)
    existing = normalized["smb"][existing_index] if existing_index is not None else None
    merged = normalize_stored_smb_connection({**(existing or {}), **payload})
    if existing is not None and "password" not in payload:
        merged["password"] = existing.get("password", "")
    if existing_index is None:
        normalized["smb"].append(merged)
    else:
        normalized["smb"][existing_index] = merged
    normalized["smb"].sort(key=lambda item: (not item.get("enabled", True), item["label"].lower(), item["host"].lower()))
    return normalized, merged


def upsert_rclone_connection(connections: dict[str, Any], payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    normalized = normalize_lan_connections(connections)
    existing_index = next((index for index, item in enumerate(normalized["rclone"]) if item["id"] == payload.get("id")), None)
    existing = normalized["rclone"][existing_index] if existing_index is not None else None
    merged = normalize_stored_rclone_connection({**(existing or {}), **payload})
    if existing_index is None:
        normalized["rclone"].append(merged)
    else:
        normalized["rclone"][existing_index] = merged
    normalized["rclone"].sort(key=lambda item: (not item.get("enabled", True), item["label"].lower(), item["rclone_name"].lower()))
    return normalized, merged


def remove_smb_connection(connections: dict[str, Any], connection_id: str) -> tuple[dict[str, Any], dict[str, Any] | None]:
    normalized = normalize_lan_connections(connections)
    removed = next((item for item in normalized["smb"] if item["id"] == connection_id), None)
    normalized["smb"] = [item for item in normalized["smb"] if item["id"] != connection_id]
    return normalized, removed


def remove_rclone_connection(connections: dict[str, Any], connection_id: str) -> tuple[dict[str, Any], dict[str, Any] | None]:
    normalized = normalize_lan_connections(connections)
    removed = next((item for item in normalized["rclone"] if item["id"] == connection_id), None)
    normalized["rclone"] = [item for item in normalized["rclone"] if item["id"] != connection_id]
    return normalized, removed


def redact_lan_connections(connections: dict[str, Any]) -> dict[str, Any]:
    normalized = normalize_lan_connections(connections)
    return {
        "smb": [redact_smb_connection(connection) for connection in normalized["smb"]],
        "rclone": [redact_rclone_connection(connection) for connection in normalized["rclone"]],
    }


def redact_smb_connection(connection: dict[str, Any]) -> dict[str, Any]:
    redacted = {**connection}
    redacted["has_password"] = bool(redacted.get("password"))
    redacted["password"] = ""
    return redacted


def redact_rclone_connection(connection: dict[str, Any]) -> dict[str, Any]:
    redacted = {**connection}
    # Rclone config can contain secrets, we should probably redact the whole config
    # or at least known secret keys. For now, let's just mark it as having config.
    redacted["has_config"] = bool(redacted.get("config"))
    # redacted["config"] = {} # Keeping config for now as it might be needed for UI display (non-secret parts)
    # Actually, rclone config often has tokens. Let's redact it for the API payload.
    redacted["config"] = {k: "********" if "token" in k or "secret" in k or "password" in k else v for k, v in redacted.get("config", {}).items()}
    return redacted


def resolve_smb_connection_for_test(connections: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    normalized = normalize_lan_connections(connections)
    base = next((item for item in normalized["smb"] if item["id"] == payload.get("id")), None)
    merged = {**(base or {}), **payload}
    if base is not None and "password" not in payload:
        merged["password"] = base.get("password", "")
    return normalize_stored_smb_connection(merged)


def resolve_smb_connection(connections: dict[str, Any], connection_id: str) -> dict[str, Any] | None:
    normalized = normalize_lan_connections(connections)
    return next((item for item in normalized["smb"] if item["id"] == connection_id), None)


def resolve_rclone_connection(connections: dict[str, Any], connection_id: str) -> dict[str, Any] | None:
    normalized = normalize_lan_connections(connections)
    return next((item for item in normalized["rclone"] if item["id"] == connection_id), None)


def test_smb_connection(connection: dict[str, Any], *, timeout: int = 8) -> dict[str, Any]:
    normalized = normalize_stored_smb_connection(connection)
    if not normalized["host"]:
        return {"status": "error", "message": "host is required"}
    if not normalized["username"]:
        return {"status": "error", "message": "username is required"}

    host_target = f"//{normalized['host']}"
    target = host_target
    auth_file = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as handle:
            auth_file = Path(handle.name)
            handle.write(f"username = {normalized['username']}\n")
            handle.write(f"password = {normalized['password']}\n")
            if normalized["domain"]:
                handle.write(f"domain = {normalized['domain']}\n")

        if normalized["share_name"]:
            target = f"{target}/{normalized['share_name']}"
            completed = subprocess.run(
                [
                    "smbclient",
                    target,
                    "-A",
                    str(auth_file),
                    "-m",
                    f"SMB{normalized['version']}",
                    "-g",
                    "-c",
                    f"{build_cd_command(normalized['base_path'])}ls",
                ],
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        else:
            completed = subprocess.run(
                [
                    "smbclient",
                    "-L",
                    host_target,
                    "-A",
                    str(auth_file),
                    "-m",
                    f"SMB{normalized['version']}",
                    "-g",
                ],
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
    except FileNotFoundError:
        return {"status": "error", "message": SMBCLIENT_MISSING_MESSAGE}
    except subprocess.TimeoutExpired:
        return {"status": "error", "message": "SMB connection test timed out"}
    finally:
        if auth_file and auth_file.exists():
            auth_file.unlink(missing_ok=True)

    if completed.returncode != 0:
        error = (completed.stderr or completed.stdout or "SMB connection test failed").strip()
        return {
            "status": "error",
            "message": error,
            "target": target,
        }

    result = {
        "status": "success",
        "target": target,
        "share_name": normalized["share_name"] or None,
        "base_path": normalized["base_path"] or "/",
    }
    if not normalized["share_name"]:
        result["shares"] = parse_smbclient_shares(completed.stdout or "")
    else:
        result["listing_preview"] = parse_smbclient_listing(completed.stdout or "")
        try:
            shares_completed = subprocess.run(
                [
                    "smbclient",
                    "-L",
                    host_target,
                    "-A",
                    str(auth_file),
                    "-m",
                    f"SMB{normalized['version']}",
                    "-g",
                ],
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            shares_completed = None
        if shares_completed and shares_completed.returncode == 0:
            result["shares"] = parse_smbclient_shares(shares_completed.stdout or "")
    return result


def browse_smb_path(
    connection: dict[str, Any],
    raw_path: str | None = None,
    *,
    timeout: int = 20,
    share_name: str | None = None,
    host_scope: bool = False,
) -> dict[str, Any]:
    normalized = normalize_stored_smb_connection(connection)
    if not normalized["host"]:
        return {"status": "error", "message": "host is required"}
    if not normalized["username"]:
        return {"status": "error", "message": "username is required"}

    effective_share_name = "" if host_scope else str(share_name or normalized["share_name"] or "").strip().strip("/")
    if not effective_share_name:
        share_result = list_smb_shares(normalized, timeout=timeout)
        if share_result["status"] != "success":
            return share_result
        return {
            "status": "success",
            "scope": "host",
            "connection": {
                "id": normalized["id"],
                "label": normalized["label"],
                "host": normalized["host"],
                "share_name": "",
            },
            "path": "/",
            "parent": None,
            "breadcrumbs": [{"name": normalized["host"], "path": "/", "share_name": ""}],
            "entries": [
                {
                    "name": share["name"],
                    "path": "/",
                    "type": "share",
                    "share_name": share["name"],
                    "comment": share.get("comment", ""),
                }
                for share in share_result.get("shares", [])
            ],
        }

    browser_connection = {**normalized, "share_name": effective_share_name}
    validation_error = validate_smb_browser_connection(browser_connection)
    if validation_error:
        return {"status": "error", "message": validation_error}

    current_path = normalize_share_path(raw_path or browser_connection["base_path"])
    command = f'{build_cd_command(current_path)}ls'
    completed = run_smbclient_command(browser_connection, command, timeout=timeout)
    if completed["status"] != "success":
        return completed

    entries = parse_smbclient_entries(str(completed.get("stdout") or ""))
    directories = [
        {
            **entry,
            "path": join_share_path(current_path, entry["name"]),
            "share_name": browser_connection["share_name"],
        }
        for entry in entries
        if entry["type"] == "directory"
    ]
    return {
        "status": "success",
        "scope": "share",
        "connection": {
            "id": browser_connection["id"],
            "label": browser_connection["label"],
            "host": browser_connection["host"],
            "share_name": browser_connection["share_name"],
        },
        "path": current_path or "/",
        "parent": parent_share_path(current_path),
        "breadcrumbs": build_share_breadcrumbs(current_path, share_name=browser_connection["share_name"]),
        "entries": directories,
    }


def create_smb_directory(connection: dict[str, Any], parent_path: str | None, folder_name: str, *, timeout: int = 10) -> dict[str, Any]:
    normalized = normalize_stored_smb_connection(connection)
    validation_error = validate_smb_browser_connection(normalized)
    if validation_error:
        return {"status": "error", "message": validation_error}

    clean_name = str(folder_name or "").strip().strip("/")
    if not clean_name:
        return {"status": "error", "message": "folder name is required"}
    if any(part in {"..", "."} for part in clean_name.split("/")):
        return {"status": "error", "message": "folder name must not contain relative path segments"}

    current_path = normalize_share_path(parent_path or normalized["base_path"])
    target_path = join_share_path(current_path, clean_name)
    command = f'{build_cd_command(current_path)}mkdir "{clean_name}"'
    completed = run_smbclient_command(normalized, command, timeout=timeout)
    if completed["status"] != "success":
        return completed

    return {
        "status": "success",
        "message": "Folder created.",
        "path": target_path,
        "parent": current_path or "/",
    }


def delete_smb_directory(connection: dict[str, Any], raw_path: str, *, timeout: int = 10) -> dict[str, Any]:
    normalized = normalize_stored_smb_connection(connection)
    validation_error = validate_smb_browser_connection(normalized)
    if validation_error:
        return {"status": "error", "message": validation_error}

    target_path = normalize_share_path(raw_path)
    if not target_path or target_path == "/":
        return {"status": "error", "message": "root folder cannot be deleted"}

    parent_path = parent_share_path(target_path) or "/"
    folder_name = Path(target_path).name
    command = f'{build_cd_command(parent_path)}rmdir "{folder_name}"'
    completed = run_smbclient_command(normalized, command, timeout=timeout)
    if completed["status"] != "success":
        return completed

    return {
        "status": "success",
        "message": "Folder deleted.",
        "path": target_path,
        "parent": parent_path,
    }


def parse_smbclient_shares(output: str) -> list[dict[str, str]]:
    shares: list[dict[str, str]] = []
    for line in output.splitlines():
        parts = [part.strip() for part in line.split("|")]
        if len(parts) < 2 or parts[0] != "Disk":
            continue
        shares.append({"name": parts[1], "comment": parts[2] if len(parts) > 2 else ""})
    return shares


def parse_smbclient_listing(output: str) -> list[dict[str, str]]:
    entries = parse_smbclient_entries(output)
    preview: list[dict[str, str]] = []
    for entry in entries:
        if entry["type"] != "directory":
            continue
        preview.append({"name": entry["name"], "path": entry["path"], "type": entry["type"]})
        if len(preview) >= 12:
            break
    return preview


def list_smb_shares(connection: dict[str, Any], *, timeout: int) -> dict[str, Any]:
    completed = run_smbclient_share_listing(connection, timeout=timeout)
    if completed["status"] != "success":
        return completed
    return {"status": "success", "shares": parse_smbclient_shares(str(completed.get("stdout") or ""))}


def validate_smb_browser_connection(connection: dict[str, Any]) -> str | None:
    if not connection["host"]:
        return "host is required"
    if not connection["share_name"]:
        return "share name is required"
    if not connection["username"]:
        return "username is required"
    return None


def run_smbclient_command(connection: dict[str, Any], smb_command: str, *, timeout: int) -> dict[str, Any]:
    target = f"//{connection['host']}/{connection['share_name']}"
    auth_file = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as handle:
            auth_file = Path(handle.name)
            handle.write(f"username = {connection['username']}\n")
            handle.write(f"password = {connection['password']}\n")
            if connection["domain"]:
                handle.write(f"domain = {connection['domain']}\n")

        completed = subprocess.run(
            [
                "smbclient",
                target,
                "-A",
                str(auth_file),
                "-m",
                f"SMB{connection['version']}",
                "-g",
                "-c",
                smb_command,
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError:
        return {"status": "error", "message": SMBCLIENT_MISSING_MESSAGE}
    except subprocess.TimeoutExpired:
        return {"status": "error", "message": "SMB command timed out"}
    finally:
        if auth_file and auth_file.exists():
            auth_file.unlink(missing_ok=True)

    if completed.returncode != 0:
        error = (completed.stderr or completed.stdout or "SMB command failed").strip()
        return {"status": "error", "message": error, "target": target}

    return {"status": "success", "stdout": completed.stdout or "", "target": target}


def run_smbclient_share_listing(connection: dict[str, Any], *, timeout: int) -> dict[str, Any]:
    target = f"//{connection['host']}"
    auth_file = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as handle:
            auth_file = Path(handle.name)
            handle.write(f"username = {connection['username']}\n")
            handle.write(f"password = {connection['password']}\n")
            if connection["domain"]:
                handle.write(f"domain = {connection['domain']}\n")

        completed = subprocess.run(
            [
                "smbclient",
                "-L",
                target,
                "-A",
                str(auth_file),
                "-m",
                f"SMB{connection['version']}",
                "-g",
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError:
        return {"status": "error", "message": SMBCLIENT_MISSING_MESSAGE}
    except subprocess.TimeoutExpired:
        return {"status": "error", "message": "SMB share listing timed out"}
    finally:
        if auth_file and auth_file.exists():
            auth_file.unlink(missing_ok=True)

    if completed.returncode != 0:
        error = (completed.stderr or completed.stdout or "SMB share listing failed").strip()
        return {"status": "error", "message": error, "target": target}

    return {"status": "success", "stdout": completed.stdout or "", "target": target}


def build_cd_command(path: str) -> str:
    normalized = normalize_share_path(path)
    if not normalized or normalized == "/":
        return ""
    return f'cd "{normalized.strip("/")}";'


def join_share_path(base_path: str, name: str) -> str:
    base = normalize_share_path(base_path)
    clean_name = name.strip().strip("/")
    if not base or base == "/":
        return f"/{clean_name}"
    return f"{base}/{clean_name}"


def parent_share_path(path: str) -> str | None:
    normalized = normalize_share_path(path)
    if not normalized or normalized == "/":
        return None
    parent = str(Path(normalized).parent)
    return parent if parent.startswith("/") else f"/{parent}"


def build_share_breadcrumbs(path: str, *, share_name: str = "") -> list[dict[str, str]]:
    normalized = normalize_share_path(path) or "/"
    crumbs = [{"name": share_name or "/", "path": "/", "share_name": share_name}]
    current = ""
    for part in Path(normalized).parts[1:]:
        current = f"{current}/{part}"
        crumbs.append({"name": part, "path": current, "share_name": share_name})
    return crumbs


def parse_smbclient_entries(output: str) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    structured_line = re.compile(r"^\s*(?P<name>.+?)\s{2,}(?P<attrs>[A-Z]+)\s+(?P<size>\d+)\s+(?P<modified>.+?)\s*$")
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        parts = [part.strip() for part in raw_line.split("|")]
        if len(parts) >= 5:
            name = parts[0]
            if name in {".", ".."}:
                continue
            attributes = parts[4].upper()
            entry_type = "directory" if "D" in attributes else "file"
            entries.append(
                {
                    "name": name,
                    "path": normalize_share_path(name),
                    "type": entry_type,
                    "size": parts[1] if len(parts) > 1 else "",
                    "modified_at": " ".join(part for part in parts[2:4] if part),
                }
            )
            continue

        match = structured_line.match(raw_line.rstrip())
        if match:
            name = match.group("name").strip()
            if name in {".", ".."}:
                continue
            attributes = match.group("attrs").upper()
            entries.append(
                {
                    "name": name,
                    "path": normalize_share_path(name),
                    "type": "directory" if "D" in attributes else "file",
                    "size": match.group("size"),
                    "modified_at": match.group("modified").strip(),
                }
            )
            continue

        stripped = raw_line.rstrip()
        if stripped.startswith((".", "..")) or stripped.startswith("blocks of size"):
            continue
        if "<DIR>" in stripped.upper():
            name = stripped.split("<", 1)[0].strip()
            if name:
                entries.append({"name": name, "path": normalize_share_path(name), "type": "directory", "size": "", "modified_at": ""})

    entries.sort(key=lambda item: (item["type"] != "directory", item["name"].lower()))
    return entries
