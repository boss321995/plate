"""
hikvision_discovery.py — Hikvision Camera Discovery (MEGA v7, Part 22)

Scans a subnet (e.g. 192.168.1.0/24) for devices with port 554 open,
then probes each with a quick RTSP OPTIONS request to confirm Hikvision.

Optionally queries Hikvision ISAPI HTTP endpoint for model + serial info.

Usage:
    from hikvision_discovery import discover
    cameras = discover("192.168.1.0/24", username="admin", password="pass")
    for cam in cameras:
        print(cam)
"""

from __future__ import annotations

import os
import re
import socket
import logging
import ipaddress
import urllib.request
import urllib.parse
import concurrent.futures
from typing import Optional

log = logging.getLogger(__name__)

DEFAULT_TIMEOUT   = float(os.getenv("DISCOVERY_TIMEOUT",  "0.5"))
DEFAULT_WORKERS   = int(os.getenv("DISCOVERY_WORKERS",    "64"))
RTSP_PORT         = 554
HTTP_PORTS        = [80, 443, 8080]
ISAPI_DEVICE_INFO = "/ISAPI/System/deviceInfo"


def _port_open(ip: str, port: int, timeout: float) -> bool:
    try:
        with socket.create_connection((ip, port), timeout=timeout):
            return True
    except OSError:
        return False


def _rtsp_options(ip: str, port: int = 554, timeout: float = 1.5) -> bool:
    """
    Send RTSP OPTIONS to verify it's an RTSP server (not just open port).
    Hikvision cameras respond with Public: DESCRIBE, SETUP, …
    """
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        s.connect((ip, port))
        request = (
            f"OPTIONS rtsp://{ip}:{port}/ RTSP/1.0\r\n"
            f"CSeq: 1\r\n"
            f"User-Agent: LPR-Discovery/1.0\r\n\r\n"
        ).encode()
        s.sendall(request)
        response = s.recv(512).decode(errors="ignore")
        s.close()
        return "RTSP/1.0 200" in response
    except Exception:
        return False


def _query_isapi(ip: str, username: str, password: str,
                 timeout: float = 2.0) -> Optional[dict]:
    """
    Query Hikvision ISAPI /System/deviceInfo for model, serial, firmware.
    Returns None if unreachable or not a Hikvision device.
    """
    for scheme, port in [("http", 80), ("https", 443), ("http", 8080)]:
        url = f"{scheme}://{ip}:{port}{ISAPI_DEVICE_INFO}"
        try:
            password_mgr = urllib.request.HTTPPasswordMgrWithDefaultRealm()
            password_mgr.add_password(None, url, username, password)
            auth_handler  = urllib.request.HTTPBasicAuthHandler(password_mgr)
            opener        = urllib.request.build_opener(auth_handler)
            opener.addheaders = [("User-Agent", "LPR-Discovery/1.0")]
            req = urllib.request.Request(url)
            with opener.open(req, timeout=timeout) as r:
                body = r.read().decode(errors="ignore")
            # Parse basic XML fields
            def _extract(tag: str) -> str:
                m = re.search(rf"<{tag}>([^<]+)</{tag}>", body)
                return m.group(1) if m else ""
            return {
                "model":    _extract("model"),
                "serial":   _extract("serialNumber"),
                "firmware": _extract("firmwareVersion"),
                "http_port": port,
                "scheme":   scheme,
            }
        except Exception:
            continue
    return None


def _probe_ip(
    ip:       str,
    username: str,
    password: str,
    timeout:  float,
    deep:     bool,
) -> Optional[dict]:
    """Full probe for one IP: port check → RTSP verify → ISAPI query."""
    if not _port_open(ip, RTSP_PORT, timeout):
        return None

    rtsp_ok = _rtsp_options(ip, RTSP_PORT, timeout * 2)

    info: dict = {
        "ip":           ip,
        "rtsp_port":    RTSP_PORT,
        "rtsp_ok":      rtsp_ok,
        "manufacturer": "unknown",
        "model":        "",
        "serial":       "",
        "firmware":     "",
        "status":       "online",
    }

    if deep and username:
        device = _query_isapi(ip, username, password, timeout=2.0)
        if device:
            info["manufacturer"] = "Hikvision"
            info["model"]        = device.get("model", "")
            info["serial"]       = device.get("serial", "")
            info["firmware"]     = device.get("firmware", "")
            info["http_port"]    = device.get("http_port", 80)

    return info


def discover(
    subnet:   str  = "192.168.1.0/24",
    username: str  = "",
    password: str  = "",
    timeout:  float = DEFAULT_TIMEOUT,
    workers:  int  = DEFAULT_WORKERS,
    deep:     bool = True,
) -> list[dict]:
    """
    Scan subnet for Hikvision cameras.

    Args:
        subnet:   CIDR notation, e.g. "192.168.1.0/24"
        username: Hikvision admin username (for ISAPI query)
        password: Hikvision admin password
        timeout:  TCP connect timeout per host (seconds)
        workers:  Parallel probe threads
        deep:     If True, query ISAPI for model/serial info

    Returns:
        List of discovered camera dicts sorted by IP.
    """
    try:
        network = ipaddress.ip_network(subnet, strict=False)
    except ValueError as exc:
        log.error("[Discovery] Invalid subnet %s: %s", subnet, exc)
        return []

    hosts      = list(network.hosts())
    total      = len(hosts)
    found: list[dict] = []

    log.info("[Discovery] Scanning %s (%d hosts, timeout=%.1fs, workers=%d)",
             subnet, total, timeout, workers)

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(_probe_ip, str(ip), username, password, timeout, deep): ip
            for ip in hosts
        }
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            if result:
                found.append(result)

    found.sort(key=lambda x: ipaddress.ip_address(x["ip"]))
    log.info("[Discovery] Found %d cameras in %s", len(found), subnet)
    return found


# ─── CLI usage ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    subnet   = sys.argv[1] if len(sys.argv) > 1 else "192.168.1.0/24"
    username = os.getenv("HIKVISION_USERNAME", "admin")
    password = os.getenv("HIKVISION_PASSWORD", "")

    results = discover(subnet, username=username, password=password)
    for cam in results:
        print(f"  {cam['ip']:16s}  {cam['manufacturer']:10s}  "
              f"{cam['model']:20s}  {cam['serial']:15s}  fw={cam['firmware']}")
    print(f"\nTotal: {len(results)} cameras found")
