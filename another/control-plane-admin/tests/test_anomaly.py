from datetime import datetime, timedelta, timezone

from another_admin.domain.anomaly import AlertThresholds, evaluate


def _ts(seconds_ago: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(seconds=seconds_ago)).isoformat()


def test_auth_fail_burst_and_per_client():
    events = [
        {"category": "auth_fail", "client_id": "c1", "ts": _ts(10)}
        for _ in range(8)
    ] + [
        {"category": "auth_fail", "client_id": None, "ts": _ts(10)}
        for _ in range(15)
    ]
    alerts = evaluate(
        events=events,
        sessions=[],
        thresholds=AlertThresholds(auth_fail_count=20, auth_fail_per_client=8),
    )
    types = {a.alert_type for a in alerts}
    assert "auth_fail_burst" in types
    assert "auth_fail_client" in types


def test_concurrent_sessions_different_ip_hash():
    sessions = [
        {"client_id": "c1", "ip_hash": "aaaa", "session_id": "c1:aaaa"},
        {"client_id": "c1", "ip_hash": "bbbb", "session_id": "c1:bbbb"},
    ]
    alerts = evaluate(events=[], sessions=sessions)
    assert any(a.alert_type == "concurrent_sessions" for a in alerts)


def test_ping_fail_streak():
    events = [
        {"category": "ping_fail", "detail": {"name": "hf"}, "ts": _ts(10)},
        {"category": "ping_fail", "detail": {"name": "hf"}, "ts": _ts(20)},
        {"category": "ping_fail", "detail": {"name": "hf"}, "ts": _ts(30)},
        {"category": "ping_ok", "detail": {"name": "render"}, "ts": _ts(5)},
    ]
    alerts = evaluate(
        events=events,
        sessions=[],
        thresholds=AlertThresholds(ping_fail_streak=3),
    )
    assert any(a.alert_type == "ping_fail_streak" and a.detail["name"] == "hf" for a in alerts)


def test_bytes_spike():
    sessions = [{"client_id": "c1", "ip_hash": "aa", "bytes_window": 2_000_000_000, "session_id": "s1"}]
    alerts = evaluate(events=[], sessions=sessions, thresholds=AlertThresholds(bytes_spike_bytes=1_000_000_000))
    assert any(a.alert_type == "bytes_spike" for a in alerts)


def test_no_alert_below_thresholds():
    alerts = evaluate(
        events=[{"category": "auth_fail", "ts": _ts(1)}],
        sessions=[{"client_id": "c1", "ip_hash": "aa", "bytes_window": 10}],
    )
    assert alerts == []
