from __future__ import annotations

import re
import subprocess
from collections import defaultdict
from typing import Any


SERVICE_DEFINITIONS = {
    "_smb._tcp": {"label": "SMB", "scheme": "smb"},
    "_nfs._tcp": {"label": "NFS", "scheme": "nfs"},
    "_afpovertcp._tcp": {"label": "AFP", "scheme": "afp"},
}

BROWSE_LINE_RE = re.compile(
    r"^\s*\S+\s+(Add|Rmv)\s+\S+\s+\S+\s+(?P<domain>\S+)\s+(?P<service>_[^\s]+)\s+(?P<instance>.+?)\s*$"
)
RESOLVE_RE = re.compile(r"can be reached at (?P<target>[^ ]+?)\s*:\s*(?P<port>\d+)")
ARP_LINE_RE = re.compile(
    r"^(?P<host>.+?)\s+\((?P<ip>\d+\.\d+\.\d+\.\d+)\)\s+at\s+(?P<mac>[0-9a-f:]+|[^\s]+)\s+on\s+(?P<iface>\S+)"
)
IP_NEIGH_LINE_RE = re.compile(
    r"^(?P<ip>\d+\.\d+\.\d+\.\d+)\s+dev\s+(?P<iface>\S+)(?:\s+lladdr\s+(?P<mac>[0-9a-f:]+))?.*$",
    re.IGNORECASE,
)


def discover_lan_devices() -> dict[str, Any]:
    services = discover_bonjour_services()
    arp_hosts = discover_arp_hosts()

    devices: dict[str, dict[str, Any]] = {}

    for host in arp_hosts:
        key = host["device_key"]
        devices[key] = {
            "device_key": key,
            "display_name": host["display_name"],
            "hostname": host["hostname"],
            "ip_address": host["ip_address"],
            "mac_address": host["mac_address"],
            "interface": host["interface"],
            "services": [],
            "connect_urls": [],
            "sources": ["arp"],
        }

    for service in services:
        key = service["device_key"]
        device = devices.setdefault(
            key,
            {
                "device_key": key,
                "display_name": service["target"],
                "hostname": service["target"],
                "ip_address": None,
                "mac_address": None,
                "interface": None,
                "services": [],
                "connect_urls": [],
                "sources": [],
            },
        )
        device["display_name"] = best_display_name(device["display_name"], service["instance"], service["target"])
        device["hostname"] = device["hostname"] or service["target"]
        if "bonjour" not in device["sources"]:
            device["sources"].append("bonjour")
        device["services"].append(service)
        if service["connect_url"] and service["connect_url"] not in device["connect_urls"]:
            device["connect_urls"].append(service["connect_url"])

    ordered_devices = sorted(
        devices.values(),
        key=lambda item: (
            0 if item["services"] else 1,
            (item["display_name"] or item["hostname"] or item["ip_address"] or "").lower(),
        ),
    )

    return {
        "summary": {
            "devices": len(ordered_devices),
            "bonjour_services": len(services),
            "arp_hosts": len(arp_hosts),
        },
        "devices": ordered_devices,
    }


def discover_bonjour_services() -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for service_type in SERVICE_DEFINITIONS:
        for instance in browse_service_instances(service_type):
            resolved = resolve_service_instance(instance["instance"], service_type, instance["domain"])
            if resolved is None:
                continue
            results.append(
                {
                    "instance": instance["instance"],
                    "service_type": service_type,
                    "service_label": SERVICE_DEFINITIONS[service_type]["label"],
                    "domain": instance["domain"],
                    "target": resolved["target"],
                    "port": resolved["port"],
                    "connect_url": build_connect_url(SERVICE_DEFINITIONS[service_type]["scheme"], resolved["target"]),
                    "device_key": normalize_device_key(resolved["target"]),
                }
            )
    return results


def browse_service_instances(service_type: str) -> list[dict[str, str]]:
    output = run_command(["dns-sd", "-B", service_type, "local."], timeout=1)
    instances: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for raw_line in output.splitlines():
        line = raw_line.strip()
        match = BROWSE_LINE_RE.match(line)
        if not match or "Add" not in line:
            continue
        instance_name = match.group("instance").strip()
        domain = match.group("domain").strip()
        key = (instance_name, domain)
        if key in seen:
            continue
        seen.add(key)
        instances.append({"instance": instance_name, "domain": domain})
    return instances


def resolve_service_instance(instance: str, service_type: str, domain: str) -> dict[str, Any] | None:
    output = run_command(["dns-sd", "-L", instance, service_type, domain], timeout=1)
    for raw_line in output.splitlines():
        match = RESOLVE_RE.search(raw_line)
        if not match:
            continue
        target = match.group("target").rstrip(".")
        return {"target": target, "port": int(match.group("port"))}
    return None


def discover_arp_hosts() -> list[dict[str, Any]]:
    output = run_command(["arp", "-a"], timeout=1)
    if not output.strip():
        output = run_command(["ip", "neigh"], timeout=1)
        if output.strip():
            return parse_ip_neigh_hosts(output)
    hosts: list[dict[str, Any]] = []
    for raw_line in output.splitlines():
        match = ARP_LINE_RE.match(raw_line.strip())
        if not match:
            continue
        host = match.group("host").strip()
        ip = match.group("ip")
        mac = match.group("mac")
        iface = match.group("iface")
        hostname = None if host == "?" else host
        hosts.append(
            {
                "device_key": normalize_device_key(hostname or ip),
                "display_name": hostname or ip,
                "hostname": hostname,
                "ip_address": ip,
                "mac_address": mac if mac != "(incomplete)" else None,
                "interface": iface,
            }
        )
    return hosts


def parse_ip_neigh_hosts(output: str) -> list[dict[str, Any]]:
    hosts: list[dict[str, Any]] = []
    for raw_line in output.splitlines():
        match = IP_NEIGH_LINE_RE.match(raw_line.strip())
        if not match:
            continue
        ip = match.group("ip")
        iface = match.group("iface")
        mac = match.group("mac")
        hosts.append(
            {
                "device_key": normalize_device_key(ip),
                "display_name": ip,
                "hostname": None,
                "ip_address": ip,
                "mac_address": mac,
                "interface": iface,
            }
        )
    return hosts


def run_command(command: list[str], *, timeout: int) -> str:
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)
        return completed.stdout or ""
    except FileNotFoundError:
        return ""
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout
        if stdout is None:
            return ""
        if isinstance(stdout, bytes):
            return stdout.decode("utf-8", errors="replace")
        return stdout


def build_connect_url(scheme: str, target: str) -> str:
    return f"{scheme}://{target}"


def normalize_device_key(value: str) -> str:
    return value.strip().rstrip(".").lower()


def best_display_name(current: str | None, instance: str, target: str) -> str:
    for candidate in [current, instance, target]:
        if candidate and candidate != "?":
            return candidate
    return target
