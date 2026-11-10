import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "gitea_sync",
    ROOT / ".github" / "scripts" / "gitea_sync.py",
)
gitea_sync = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gitea_sync)


def test_private_repository_stays_private_and_public_stays_public():
    private = gitea_sync.settings_payload(
        {
            "private": True,
            "description": "closed",
            "homepage": "https://github.com/Nergan/jenny-port-mod",
            "default_branch": "main",
            "has_issues": False,
            "has_wiki": True,
            "allow_merge_commit": True,
        }
    )
    public = gitea_sync.settings_payload(
        {
            "private": False,
            "description": "",
            "homepage": "not a url",
            "default_branch": "main",
        }
    )
    assert private["private"] is True
    assert private["website"] == "https://github.com/Nergan/jenny-port-mod"
    assert private["has_issues"] is False
    assert private["has_wiki"] is True
    assert private["allow_merge_commits"] is True
    assert "has_projects" not in private
    assert public["private"] is False
    assert public["website"] == ""


def test_topics_keep_only_names_gitea_accepts():
    assert gitea_sync.sanitize_topics(["Minecraft Mod", "MPL-2.0", "already", "Already", "", "ok"]) == [
        "minecraft-mod",
        "mpl-20",
        "already",
        "ok",
    ]


def test_release_links_point_at_github_and_replace_the_old_list():
    body = gitea_sync.release_body("Player build.\n", [{"name": "app.apk", "url": "https://github.com/Nergan/cutaway/releases/download/v1/app.apk"}])
    assert body.startswith("Player build.")
    assert "https://github.com/Nergan/cutaway/releases/download/v1/app.apk" in body
    replaced = gitea_sync.release_body(body, [{"name": "app.apk", "url": "https://github.com/Nergan/cutaway/releases/download/v2/app.apk"}])
    assert replaced.count("github-assets") == 2
    assert "download/v1/" not in replaced
    assert "download/v2/" in replaced
    assert gitea_sync.release_body(body, []).strip() == "Player build."


def test_draft_is_skipped_and_existing_release_is_updated():
    actions = gitea_sync.plan_release_sync(
        [
            {"tag_name": "v0", "name": "Hidden", "body": "no", "draft": True, "assets": []},
            {
                "tag_name": "v1",
                "name": "Shown",
                "body": "notes",
                "draft": False,
                "prerelease": False,
                "assets": [{"name": "mod.jar", "browser_download_url": "https://github.com/Nergan/mod/releases/download/v1/mod.jar"}],
            },
        ],
        [{"id": 7, "tag_name": "v1", "name": "Old", "body": "notes", "prerelease": False}],
    )
    assert [item["op"] for item in actions] == ["update"]
    assert actions[0]["id"] == 7
    assert actions[0]["links"] == [{"name": "mod.jar", "url": "https://github.com/Nergan/mod/releases/download/v1/mod.jar"}]
    assert "mod.jar" in actions[0]["body"]
