"""Детектор аномалий для админ-монитора (docs/observability.md).

Поллинг агрегатов, не ML. Пороги задаёт оператор. Алерт — запись в events
категории anomaly плюс колокольчик acked/unacked; этот модуль только
предлагает события, не пишет в store.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def parse_ts(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    if isinstance(value, str) and value:
        try:
            normalized = value.replace("Z", "+00:00")
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    return None


@dataclass(frozen=True)
class AlertThresholds:
    auth_fail_window_s: int = 300
    auth_fail_count: int = 20
    auth_fail_per_client: int = 8
    ping_fail_streak: int = 3
    concurrent_ip_hashes: int = 2
    session_active_s: int = 180
    bytes_spike_bytes: int = 1_073_741_824  # 1 ГиБ за окно сессии

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> AlertThresholds:
        if not raw:
            return cls()
        return cls(
            auth_fail_window_s=int(raw.get("auth_fail_window_s", 300)),
            auth_fail_count=int(raw.get("auth_fail_count", 20)),
            auth_fail_per_client=int(raw.get("auth_fail_per_client", 8)),
            ping_fail_streak=int(raw.get("ping_fail_streak", 3)),
            concurrent_ip_hashes=int(raw.get("concurrent_ip_hashes", 2)),
            session_active_s=int(raw.get("session_active_s", 180)),
            bytes_spike_bytes=int(raw.get("bytes_spike_bytes", 1_073_741_824)),
        )

    def to_dict(self) -> dict[str, int]:
        return {
            "auth_fail_window_s": self.auth_fail_window_s,
            "auth_fail_count": self.auth_fail_count,
            "auth_fail_per_client": self.auth_fail_per_client,
            "ping_fail_streak": self.ping_fail_streak,
            "concurrent_ip_hashes": self.concurrent_ip_hashes,
            "session_active_s": self.session_active_s,
            "bytes_spike_bytes": self.bytes_spike_bytes,
        }


@dataclass(frozen=True)
class SuggestedAlert:
    alert_type: str
    summary: str
    fingerprint: str
    detail: dict[str, Any] = field(default_factory=dict)

    def as_event(self) -> dict[str, Any]:
        return {
            "category": "anomaly",
            "client_id": self.detail.get("client_id"),
            "detail": {
                "type": self.alert_type,
                "summary": self.summary,
                "fingerprint": self.fingerprint,
                **self.detail,
            },
            "source": "anomaly-detector",
        }


def evaluate(
    *,
    events: list[dict[str, Any]],
    sessions: list[dict[str, Any]],
    thresholds: AlertThresholds | None = None,
    now: datetime | None = None,
) -> list[SuggestedAlert]:
    """Вернуть новые предложения алертов. Дедуп по fingerprint — на стороне store."""
    th = thresholds or AlertThresholds()
    clock = now or _utcnow()
    out: list[SuggestedAlert] = []
    out.extend(_auth_fail_burst(events, th, clock))
    out.extend(_auth_fail_per_client(events, th, clock))
    out.extend(_concurrent_sessions(sessions, th))
    out.extend(_ping_fail_streaks(events, th))
    out.extend(_bytes_spikes(sessions, th))
    return out


def _auth_fail_burst(
    events: list[dict[str, Any]], th: AlertThresholds, now: datetime
) -> list[SuggestedAlert]:
    cutoff = now - timedelta(seconds=th.auth_fail_window_s)
    n = sum(1 for e in events if e.get("category") == "auth_fail" and _event_ts(e) and _event_ts(e) >= cutoff)
    if n < th.auth_fail_count:
        return []
    return [
        SuggestedAlert(
            alert_type="auth_fail_burst",
            summary=f"всплеск 4xx /auth: {n} за {th.auth_fail_window_s}с",
            fingerprint=f"auth_fail_burst:{th.auth_fail_window_s}",
            detail={"count": n, "window_s": th.auth_fail_window_s},
        )
    ]


def _auth_fail_per_client(
    events: list[dict[str, Any]], th: AlertThresholds, now: datetime
) -> list[SuggestedAlert]:
    cutoff = now - timedelta(seconds=th.auth_fail_window_s)
    counts: dict[str, int] = defaultdict(int)
    for e in events:
        if e.get("category") != "auth_fail":
            continue
        ts = _event_ts(e)
        if ts is None or ts < cutoff:
            continue
        cid = e.get("client_id")
        if cid:
            counts[str(cid)] += 1
    alerts: list[SuggestedAlert] = []
    for cid, n in counts.items():
        if n >= th.auth_fail_per_client:
            alerts.append(
                SuggestedAlert(
                    alert_type="auth_fail_client",
                    summary=f"auth_fail {n} раз у {cid}",
                    fingerprint=f"auth_fail_client:{cid}",
                    detail={"client_id": cid, "count": n},
                )
            )
    return alerts


def _concurrent_sessions(
    sessions: list[dict[str, Any]], th: AlertThresholds
) -> list[SuggestedAlert]:
    by_client: dict[str, set[str]] = defaultdict(set)
    for s in sessions:
        cid = str(s.get("client_id") or "")
        iph = str(s.get("ip_hash") or "")
        if cid and iph:
            by_client[cid].add(iph)
    alerts: list[SuggestedAlert] = []
    for cid, hashes in by_client.items():
        if len(hashes) >= th.concurrent_ip_hashes:
            alerts.append(
                SuggestedAlert(
                    alert_type="concurrent_sessions",
                    summary=f"{len(hashes)} живых сессий {cid} с разных ip_hash",
                    fingerprint=f"concurrent_sessions:{cid}",
                    detail={"client_id": cid, "ip_hashes": sorted(hashes), "count": len(hashes)},
                )
            )
    return alerts


def _ping_fail_streaks(events: list[dict[str, Any]], th: AlertThresholds) -> list[SuggestedAlert]:
    by_name: dict[str, list[tuple[datetime, str]]] = defaultdict(list)
    for e in events:
        cat = e.get("category")
        if cat not in ("ping_fail", "ping_ok"):
            continue
        ts = _event_ts(e) or datetime.min.replace(tzinfo=timezone.utc)
        name = str((e.get("detail") or {}).get("name") or "unknown")
        by_name[name].append((ts, str(cat)))
    alerts: list[SuggestedAlert] = []
    for name, rows in by_name.items():
        rows.sort(key=lambda r: r[0], reverse=True)
        streak = 0
        for _, cat in rows:
            if cat == "ping_fail":
                streak += 1
                continue
            break
        if streak >= th.ping_fail_streak:
            alerts.append(
                SuggestedAlert(
                    alert_type="ping_fail_streak",
                    summary=f"пинг {name} упал {streak} раз подряд",
                    fingerprint=f"ping_fail_streak:{name}",
                    detail={"name": name, "streak": streak},
                )
            )
    return alerts


def _bytes_spikes(sessions: list[dict[str, Any]], th: AlertThresholds) -> list[SuggestedAlert]:
    alerts: list[SuggestedAlert] = []
    for s in sessions:
        used = int(s.get("bytes_window") or 0)
        if used < th.bytes_spike_bytes:
            continue
        cid = str(s.get("client_id") or "")
        alerts.append(
            SuggestedAlert(
                alert_type="bytes_spike",
                summary=f"скачок трафика {used} байт у {cid or 'unknown'}",
                fingerprint=f"bytes_spike:{cid}:{s.get('session_id')}",
                detail={"client_id": cid, "bytes_window": used, "session_id": s.get("session_id")},
            )
        )
    return alerts


def _event_ts(event: dict[str, Any]) -> datetime | None:
    return parse_ts(event.get("ts"))


def fingerprint_from_event(event: dict[str, Any]) -> str | None:
    detail = event.get("detail") or {}
    if event.get("category") != "anomaly":
        return None
    fp = detail.get("fingerprint")
    return str(fp) if fp else None
