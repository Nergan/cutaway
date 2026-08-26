"""QuotaReportService — сводка по использованию квоты трафика (§8.4
спецификации: поле quota_limit_bytes/bytes_used без этого сервиса было бы
"мёртвыми" данными, которые некому смотреть)."""

from __future__ import annotations

from dataclasses import dataclass

from another_admin.domain.models import QuotaReportRow
from another_admin.ports.user_repository_port import UserRepositoryPort


@dataclass(frozen=True)
class QuotaReportService:
    repo: UserRepositoryPort

    def generate_report(self) -> list[QuotaReportRow]:
        """Возвращает строки отчёта, отсортированные по проценту
        использования квоты по убыванию — так администратор сразу видит,
        кто ближе всего к лимиту, без ручной сортировки вывода."""
        rows = [
            QuotaReportRow(
                client_id=c.client_id,
                comment=c.comment,
                bytes_used=c.bytes_used,
                quota_limit_bytes=c.quota_limit_bytes,
                is_banned=c.is_banned,
            )
            for c in self.repo.list_clients()
        ]
        rows.sort(key=lambda r: r.percent_used, reverse=True)
        return rows
