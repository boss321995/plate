"""
hikvision_rtsp.py — Hikvision RTSP URL Builder (MEGA v7, Part 18)

Hikvision NVR/DVR channel numbering:
  Channel 1 Sub  Stream → /Streaming/Channels/102
  Channel 1 Main Stream → /Streaming/Channels/101
  Channel 2 Sub  Stream → /Streaming/Channels/202
  Channel 2 Main Stream → /Streaming/Channels/201
  Channel N Sub  Stream → /Streaming/Channels/{N}02
  Channel N Main Stream → /Streaming/Channels/{N}01

Usage:
    from hikvision_rtsp import build_rtsp, build_sub_rtsp, build_main_rtsp

    sub  = build_sub_rtsp("admin", "pass", "192.168.1.50", channel=1)
    main = build_main_rtsp("admin", "pass", "192.168.1.50", channel=1)
    # → rtsp://admin:pass@192.168.1.50:554/Streaming/Channels/102
    # → rtsp://admin:pass@192.168.1.50:554/Streaming/Channels/101
"""

from __future__ import annotations

import re
import urllib.parse


def build_rtsp(
    username:    str,
    password:    str,
    ip:          str,
    channel:     int  = 1,
    stream_type: str  = "sub",   # "sub" | "main" | "01" | "02"
    port:        int  = 554,
) -> str:
    """
    Build a Hikvision RTSP URL.

    stream_type:
        "sub"  / "02" → sub stream  (low res, always-on)
        "main" / "01" → main stream (high res, on-demand)
    """
    if stream_type in ("sub", "substream", "02", 2):
        suffix = "02"
    else:
        suffix = "01"

    channel_id = f"{int(channel)}{suffix}"

    # URL-encode credentials to handle special characters
    user_enc = urllib.parse.quote(str(username), safe="")
    pass_enc = urllib.parse.quote(str(password), safe="")

    return f"rtsp://{user_enc}:{pass_enc}@{ip}:{port}/Streaming/Channels/{channel_id}"


def build_sub_rtsp(
    username: str,
    password: str,
    ip:       str,
    channel:  int = 1,
    port:     int = 554,
) -> str:
    """Build sub-stream URL (for detection + LiveView)."""
    return build_rtsp(username, password, ip, channel, "sub", port)


def build_main_rtsp(
    username: str,
    password: str,
    ip:       str,
    channel:  int = 1,
    port:     int = 554,
) -> str:
    """Build main-stream URL (for OCR snapshot, on-demand only)."""
    return build_rtsp(username, password, ip, channel, "main", port)


def parse_hikvision_url(url: str) -> dict:
    """
    Parse a Hikvision RTSP URL back into components.
    Returns dict with keys: username, ip, port, channel, stream_type, suffix
    """
    pattern = r"rtsp://([^:@]+):([^@]+)@([^:/]+):?(\d+)?/Streaming/Channels/(\d+)"
    m = re.match(pattern, url)
    if not m:
        return {}
    channel_full = m.group(5)
    suffix       = channel_full[-2:]
    channel      = int(channel_full[:-2]) if len(channel_full) > 2 else 1
    return {
        "username":    urllib.parse.unquote(m.group(1)),
        "ip":          m.group(3),
        "port":        int(m.group(4) or 554),
        "channel":     channel,
        "suffix":      suffix,
        "stream_type": "sub" if suffix == "02" else "main",
    }


def mask_rtsp_url(url: str) -> str:
    """Replace password with *** — safe for logging."""
    return re.sub(r"(rtsp://[^:]+:)[^@]+(@)", r"\1***\2", url)


# ─── Quick test ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    sub  = build_sub_rtsp("admin", "Aa123456", "192.168.1.50", channel=1)
    main = build_main_rtsp("admin", "Aa123456", "192.168.1.50", channel=1)
    cam2 = build_sub_rtsp("admin", "Aa123456", "192.168.1.50", channel=2)
    print("Sub  stream ch1:", mask_rtsp_url(sub))
    print("Main stream ch1:", mask_rtsp_url(main))
    print("Sub  stream ch2:", mask_rtsp_url(cam2))
    print("Parsed:", parse_hikvision_url(sub))
