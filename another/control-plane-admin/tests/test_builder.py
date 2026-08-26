from another_admin.domain.builder import EMBED_PKG, plan_installer, try_compile


def test_plan_contains_ldflags_not_private_key():
    plan = plan_installer(
        client_id="drug-1",
        enrollment_token="aabbcc",
        nodes_json='[{"name":"cf"}]',
        platforms=["windows/amd64", "linux/amd64", "android/arm64"],
        core_src="/tmp/core",
        output_dir="out",
    )
    assert f"{EMBED_PKG}.embeddedToken=aabbcc" in plan.ldflags
    assert "embeddedClientID=drug-1" in plan.ldflags
    assert "private" not in plan.ldflags.lower()
    platforms = {a.platform for a in plan.artifacts}
    assert platforms == {"windows/amd64", "linux/amd64", "android/arm64"}
    android = next(a for a in plan.artifacts if a.platform.startswith("android"))
    assert "gomobile bind" in android.command
    assert android.compiled is False


def test_try_compile_skipped_when_disabled():
    plan = plan_installer(
        client_id="c1",
        enrollment_token="tok",
        nodes_json="[]",
        platforms=["linux/amd64"],
        core_src="/tmp/core",
        output_dir="out",
    )
    out = try_compile(plan, enabled=False)
    assert all(not a.compiled for a in out.artifacts)
