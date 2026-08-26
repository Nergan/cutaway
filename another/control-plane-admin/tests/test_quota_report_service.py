from __future__ import annotations

from another_admin.domain.models import ClientRecord
from another_admin.domain.quota_report_service import QuotaReportService


class FakeRepoForReport:
    def __init__(self, clients: list[ClientRecord]) -> None:
        self._clients = clients

    def list_clients(self) -> list[ClientRecord]:
        return self._clients


def make_client(client_id: str, bytes_used: int, quota: int, banned: bool = False) -> ClientRecord:
    return ClientRecord(
        client_id=client_id,
        comment=f"comment-{client_id}",
        public_key_hex=None,
        vless_user_id_hex=None,
        is_banned=banned,
        quota_limit_bytes=quota,
        bytes_used=bytes_used,
        enrollment_token_hash=None,
        enrollment_expires_at=None,
    )


def test_report_sorted_by_percent_used_descending():
    repo = FakeRepoForReport(
        [
            make_client("low", bytes_used=100, quota=1000),  # 10%
            make_client("high", bytes_used=900, quota=1000),  # 90%
            make_client("mid", bytes_used=500, quota=1000),  # 50%
        ]
    )
    rows = QuotaReportService(repo=repo).generate_report()
    assert [r.client_id for r in rows] == ["high", "mid", "low"]


def test_unlimited_quota_reports_zero_percent():
    repo = FakeRepoForReport([make_client("unlimited", bytes_used=999_999, quota=0)])
    rows = QuotaReportService(repo=repo).generate_report()
    assert rows[0].percent_used == 0.0


def test_empty_repo_returns_empty_report():
    rows = QuotaReportService(repo=FakeRepoForReport([])).generate_report()
    assert rows == []
