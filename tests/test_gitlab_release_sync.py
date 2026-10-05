import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "gitlab_releases",
    ROOT / ".github" / "scripts" / "gitlab_releases.py",
)
gitlab_releases = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gitlab_releases)


def test_missing_github_release_is_created_with_its_files():
    actions = gitlab_releases.plan_release_sync(
        [
            {
                "tag_name": "netlazy-v0.2.0",
                "name": "netlazy v0.2.0",
                "body": "Fixes the player.\n",
                "draft": False,
                "assets": [
                    {
                        "name": "netlazy-0.2.0.apk",
                        "browser_download_url": "https://github.com/Nergan/cutaway/releases/download/netlazy-v0.2.0/netlazy-0.2.0.apk",
                    }
                ],
            }
        ],
        [],
    )
    assert actions == [
        {
            "op": "create",
            "tag": "netlazy-v0.2.0",
            "name": "netlazy v0.2.0",
            "description": "Fixes the player.\n",
            "links": [
                {
                    "name": "netlazy-0.2.0.apk",
                    "url": "https://github.com/Nergan/cutaway/releases/download/netlazy-v0.2.0/netlazy-0.2.0.apk",
                }
            ],
        }
    ]


def test_drafts_are_skipped_and_an_existing_release_keeps_quiet_when_it_matches():
    actions = gitlab_releases.plan_release_sync(
        [
            {"tag_name": "netlazy-v0.1.0", "name": "hidden", "body": "", "draft": True, "assets": []},
            {
                "tag_name": "netlazy-v0.2.0",
                "name": "netlazy v0.2.0",
                "body": "Same notes",
                "draft": False,
                "prerelease": True,
                "assets": [
                    {
                        "name": "netlazy-0.2.0.apk",
                        "browser_download_url": "https://github.com/Nergan/cutaway/releases/download/netlazy-v0.2.0/netlazy-0.2.0.apk",
                    }
                ],
            },
        ],
        [
            {
                "tag_name": "netlazy-v0.2.0",
                "name": "netlazy v0.2.0",
                "description": "Same notes",
                "assets": {
                    "links": [
                        {
                            "id": 7,
                            "name": "netlazy-0.2.0.apk",
                            "url": "https://github.com/Nergan/cutaway/releases/download/netlazy-v0.2.0/netlazy-0.2.0.apk",
                        }
                    ]
                },
            }
        ],
    )
    assert actions == []


def test_changed_notes_and_files_update_the_gitlab_release():
    actions = gitlab_releases.plan_release_sync(
        [
            {
                "tag_name": "netlazy-v0.2.0",
                "name": "netlazy v0.2.0",
                "body": "New notes",
                "draft": False,
                "assets": [
                    {
                        "name": "netlazy-0.2.0.apk",
                        "browser_download_url": "https://github.com/Nergan/cutaway/releases/download/netlazy-v0.2.0/netlazy-0.2.0.apk",
                    }
                ],
            }
        ],
        [
            {
                "tag_name": "netlazy-v0.2.0",
                "name": "netlazy v0.2.0",
                "description": "Old notes",
                "assets": {
                    "links": [
                        {
                            "id": 4,
                            "name": "old.apk",
                            "url": "https://github.com/Nergan/cutaway/releases/download/netlazy-v0.2.0/old.apk",
                        }
                    ]
                },
            }
        ],
    )
    assert actions == [
        {
            "op": "update",
            "tag": "netlazy-v0.2.0",
            "name": "netlazy v0.2.0",
            "description": "New notes",
        },
        {"op": "delete_link", "tag": "netlazy-v0.2.0", "link_id": 4},
        {
            "op": "add_link",
            "tag": "netlazy-v0.2.0",
            "name": "netlazy-0.2.0.apk",
            "url": "https://github.com/Nergan/cutaway/releases/download/netlazy-v0.2.0/netlazy-0.2.0.apk",
        },
    ]
