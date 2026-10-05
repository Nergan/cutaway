"""Mirror GitHub Releases onto the GitLab project during repository sync."""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request


class SyncError(RuntimeError):
    pass


def main() -> None:
    github_token = os.environ.get("GITHUB_TOKEN", "").strip()
    gitlab_token = os.environ.get("GITLAB_TOKEN", "").strip()
    github_repo = os.environ.get("GITHUB_REPOSITORY", "").strip()
    gitlab_project = os.environ.get("GITLAB_PROJECT", "").strip()
    if not github_token or not gitlab_token or not github_repo or not gitlab_project:
        raise SyncError("GITHUB_TOKEN, GITLAB_TOKEN, GITHUB_REPOSITORY and GITLAB_PROJECT are required.")

    github_releases = _paginate(
        f"https://api.github.com/repos/{github_repo}/releases?per_page=100",
        {
            "Authorization": f"Bearer {github_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "cutaway-gitlab-sync",
        },
    )
    project = urllib.parse.quote(gitlab_project, safe="")
    gitlab_releases = _paginate(
        f"https://gitlab.com/api/v4/projects/{project}/releases?per_page=100",
        {"PRIVATE-TOKEN": gitlab_token},
    )
    actions = plan_release_sync(github_releases, gitlab_releases)
    if not actions and not any(github_release_view(item) for item in github_releases):
        print("No GitHub releases to mirror.")
        return
    _apply(actions, project, gitlab_token)
    print(f"Mirrored GitHub releases to {gitlab_project} ({len(actions)} change(s)).")


def github_release_view(release: dict) -> dict | None:
    """Published GitHub release as the GitLab fields we keep in sync."""
    if not isinstance(release, dict) or release.get("draft"):
        return None
    tag = str(release.get("tag_name") or "").strip()
    if not tag:
        return None
    links = []
    for asset in release.get("assets") or []:
        if not isinstance(asset, dict):
            continue
        url = str(asset.get("browser_download_url") or "").strip()
        if not url.startswith(("https://", "http://")):
            continue
        name = str(asset.get("name") or "").strip() or url.rsplit("/", 1)[-1]
        links.append({"name": name, "url": url})
    return {
        "tag": tag,
        "name": str(release.get("name") or "").strip() or tag,
        "description": str(release.get("body") or ""),
        "links": links,
    }


def plan_release_sync(github_releases: list, gitlab_releases: list) -> list[dict]:
    """Return create, update, and link changes that make GitLab match GitHub."""
    gitlab_by_tag = {}
    for item in gitlab_releases:
        if isinstance(item, dict) and item.get("tag_name"):
            gitlab_by_tag[str(item["tag_name"])] = item
    actions: list[dict] = []
    for raw in github_releases:
        view = github_release_view(raw)
        if view is None:
            continue
        current = gitlab_by_tag.get(view["tag"])
        if current is None:
            actions.append({"op": "create", **view})
            continue
        if _text(current.get("name")) != _text(view["name"]) or _text(current.get("description")) != _text(view["description"]):
            actions.append(
                {
                    "op": "update",
                    "tag": view["tag"],
                    "name": view["name"],
                    "description": view["description"],
                }
            )
        existing = []
        assets = current.get("assets") if isinstance(current.get("assets"), dict) else {}
        for link in assets.get("links") or []:
            if not isinstance(link, dict):
                continue
            existing.append(
                {
                    "id": link.get("id"),
                    "name": str(link.get("name") or ""),
                    "url": str(link.get("url") or ""),
                }
            )
        desired = {(link["name"], link["url"]) for link in view["links"]}
        have = {(link["name"], link["url"]) for link in existing}
        for link in existing:
            if (link["name"], link["url"]) not in desired and link["id"] is not None:
                actions.append({"op": "delete_link", "tag": view["tag"], "link_id": link["id"]})
        for link in view["links"]:
            if (link["name"], link["url"]) not in have:
                actions.append({"op": "add_link", "tag": view["tag"], "name": link["name"], "url": link["url"]})
    return actions


def _apply(actions: list[dict], project: str, token: str) -> None:
    headers = {"PRIVATE-TOKEN": token, "Content-Type": "application/json"}
    for action in actions:
        tag = urllib.parse.quote(str(action["tag"]), safe="")
        op = action["op"]
        if op == "create":
            url = f"https://gitlab.com/api/v4/projects/{project}/releases"
            payload = {
                "tag_name": action["tag"],
                "name": action["name"],
                "description": action["description"],
                "assets": {
                    "links": [
                        {"name": link["name"], "url": link["url"], "link_type": "other"}
                        for link in action["links"]
                    ]
                },
            }
            _send("POST", url, headers, payload, retry_missing_tag=True)
            print(f"Created GitLab release {action['tag']}.")
        elif op == "update":
            url = f"https://gitlab.com/api/v4/projects/{project}/releases/{tag}"
            _send(
                "PUT",
                url,
                headers,
                {"name": action["name"], "description": action["description"]},
            )
            print(f"Updated GitLab release {action['tag']}.")
        elif op == "add_link":
            url = f"https://gitlab.com/api/v4/projects/{project}/releases/{tag}/assets/links"
            _send(
                "POST",
                url,
                headers,
                {"name": action["name"], "url": action["url"], "link_type": "other"},
            )
            print(f"Added {action['name']} to GitLab release {action['tag']}.")
        elif op == "delete_link":
            url = f"https://gitlab.com/api/v4/projects/{project}/releases/{tag}/assets/links/{action['link_id']}"
            _send("DELETE", url, headers, None)
            print(f"Removed an outdated file from GitLab release {action['tag']}.")
        else:
            raise SyncError(f"Unknown release action {op}.")


def _paginate(url: str, headers: dict[str, str]) -> list:
    found: list = []
    while url:
        status, payload, response_headers = _request("GET", url, headers, None)
        if status != 200:
            raise SyncError(f"GET {url} returned {status}: {_snippet(payload)}")
        page = json.loads(payload.decode("utf-8"))
        if not isinstance(page, list):
            raise SyncError(f"GET {url} returned an unexpected payload.")
        found.extend(page)
        url = _next_url(url, response_headers)
    return found


def _send(method: str, url: str, headers: dict[str, str], payload: dict | None, retry_missing_tag: bool = False) -> None:
    attempts = 4 if retry_missing_tag else 1
    for attempt in range(attempts):
        status, body, _headers = _request(method, url, headers, payload)
        if status in {200, 201, 204}:
            return
        text = _snippet(body)
        missing_tag = status == 400 and "tag" in text.lower()
        if missing_tag and attempt + 1 < attempts:
            time.sleep(2)
            continue
        raise SyncError(f"{method} {url} returned {status}: {text}")


def _request(method: str, url: str, headers: dict[str, str], payload: dict | None) -> tuple[int, bytes, dict[str, str]]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return int(getattr(response, "status", 200)), response.read(), dict(response.headers.items())
    except urllib.error.HTTPError as exc:
        body = exc.read() if exc.fp is not None else b""
        response_headers = {key: value for key, value in exc.headers.items()} if exc.headers else {}
        return int(exc.code), body, response_headers


def _next_url(url: str, headers: dict[str, str]) -> str:
    link = headers.get("Link") or headers.get("link") or ""
    for part in link.split(","):
        if 'rel="next"' not in part:
            continue
        match_start = part.find("<")
        match_end = part.find(">")
        if match_start >= 0 and match_end > match_start:
            return part[match_start + 1 : match_end]
    next_page = headers.get("X-Next-Page") or headers.get("x-next-page") or ""
    if not next_page:
        return ""
    parsed = urllib.parse.urlsplit(url)
    query = dict(urllib.parse.parse_qsl(parsed.query, keep_blank_values=True))
    query["page"] = next_page
    return urllib.parse.urlunsplit(parsed._replace(query=urllib.parse.urlencode(query)))


def _text(value: object) -> str:
    return str(value or "").replace("\r\n", "\n").strip()


def _snippet(payload: bytes) -> str:
    return payload.decode("utf-8", "replace")[:500].replace("\n", " ")


if __name__ == "__main__":
    try:
        main()
    except SyncError as exc:
        raise SystemExit(str(exc)) from exc
