"""Waypoint lines from Xaero's Minimap, and checks for map suggestions."""

from __future__ import annotations

import re

COLORS = (
    "#000000",
    "#0000AA",
    "#00AA00",
    "#00AAAA",
    "#AA0000",
    "#AA00AA",
    "#FFAA00",
    "#AAAAAA",
    "#555555",
    "#5555FF",
    "#55FF55",
    "#55FFFF",
    "#FF5555",
    "#FF55FF",
    "#FFFF55",
    "#FFFFFF",
)

_DIMENSION = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")
_BLOCK = 30_000_000
_FIELDS = 14


def color_hex(index: int) -> str:
    if 0 <= index < len(COLORS):
        return COLORS[index]
    return COLORS[-1]


def parse_waypoints(text: str) -> list[dict]:
    markers = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line.startswith("waypoint:"):
            continue
        parts = line.split(":")
        if len(parts) < _FIELDS:
            continue
        extra = len(parts) - _FIELDS
        name = ":".join(parts[1 : 2 + extra]).strip()
        initials = parts[2 + extra]
        tail = parts[3 + extra :]
        if tail[4] == "true":
            continue
        try:
            x, y, z = int(tail[0]), int(tail[1]), int(tail[2])
            color = int(tail[3])
        except ValueError:
            continue
        markers.append(
            {
                "name": name or initials or "?",
                "initials": initials or "?",
                "x": x,
                "y": y,
                "z": z,
                "color": color_hex(color),
            }
        )
    return markers


def _block(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    if abs(value) > _BLOCK:
        return None
    return value


def filter_markers(dimensions: list[dict], *, dimension: str, query: str, limit: int) -> list[dict]:
    needle = query.casefold()
    found = []
    for item in dimensions:
        if dimension and item.get("id") != dimension:
            continue
        for marker in item.get("waypoints") or []:
            name = str(marker.get("name") or "")
            initials = str(marker.get("initials") or "")
            if needle and needle not in name.casefold() and needle not in initials.casefold():
                continue
            found.append(
                {
                    "dimension": item.get("id") or "",
                    "name": name,
                    "initials": initials,
                    "x": marker["x"],
                    "y": marker["y"],
                    "z": marker["z"],
                    "color": marker.get("color") or "#FFFFFF",
                }
            )
            if len(found) >= limit:
                return found
    return found


def check_suggestion(body: object) -> dict | str:
    if not isinstance(body, dict):
        return "body"
    kind = body.get("kind")
    if kind not in {"add", "rename", "delete"}:
        return "kind"
    dimension = body.get("dimension")
    if not isinstance(dimension, str) or _DIMENSION.fullmatch(dimension) is None:
        return "dimension"
    x, z = _block(body.get("x")), _block(body.get("z"))
    if x is None or z is None:
        return "place"
    y_raw = body.get("y")
    y = None if y_raw is None else _block(y_raw)
    if y_raw is not None and y is None:
        return "place"
    name = body.get("name") if isinstance(body.get("name"), str) else ""
    waypoint = body.get("waypoint") if isinstance(body.get("waypoint"), str) else ""
    name, waypoint = name.strip(), waypoint.strip()
    if len(name) > 80 or len(waypoint) > 80:
        return "name"
    if kind in {"add", "rename"} and not name:
        return "name"
    if kind in {"rename", "delete"} and not waypoint:
        return "name"
    return {
        "kind": kind,
        "dimension": dimension,
        "x": x,
        "y": y,
        "z": z,
        "name": name,
        "waypoint": waypoint,
    }
