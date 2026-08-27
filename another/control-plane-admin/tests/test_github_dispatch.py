from another_admin.adapters.github_dispatch import dispatch_installer
from another_admin.api.config import ApiConfig


def _cfg(**kwargs) -> ApiConfig:
    values = dict(
        mongo_uri="memory",
        mongo_db_name="another",
        service_secret="test-secret",
        control_plane_url="https://cf-worker.another.example",
        edge_internal_url="",
        events_capped_bytes=1024,
    )
    values.update(kwargs)
    return ApiConfig(**values)


def test_dispatch_skipped_without_secrets():
    assert dispatch_installer(_cfg(), "job-1") is False
    assert dispatch_installer(_cfg(github_repo="Nergan/cutaway"), "job-1") is False
