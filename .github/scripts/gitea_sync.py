"""Mirror one GitHub repository onto gitea.com/nargan.

Releases keep the GitHub title and text. Gitea has no separate release-link
field, so each file is a link to its GitHub download inside the release text.
The file itself is not uploaded again.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


HOST = "https://gitea.com"
OWNER = "nargan"
ASSET_START = "<!-- github-assets -->"
ASSET_END = "<!-- /github-assets -->"
TOPIC_NAME = re.compile(r"^[a-z0-9][a-z0-9-]{0,34}$")


class SyncError(RuntimeError):
    pass


def main() -> None:
    gitea_token = _env("GITEA_TOKEN")
    github_token = _env("GITHUB_TOKEN")
    repository = _env("GITHUB_REPOSITORY")
    repo_name = repository.split("/", 1)[1]
    github_repo = _github_json(f"https://api.github.com/repos/{repository}", github_token)
    if not isinstance(github_repo, dict) or "private" not in github_repo:
        raise SyncError("GitHub did not return this repository's visibility.")
    private = bool(github_repo["private"])
    default_branch = str(github_repo.get("default_branch") or "main")

    created = _ensure_repo(gitea_token, repo_name, private, default_branch)
    _ensure_privacy(gitea_token, repo_name, private)
    _push_refs(gitea_token, repo_name)
    _apply_settings(gitea_token, repo_name, settings_payload(github_repo))
    topics = sanitize_topics(github_repo.get("topics") or [])
    _gitea(
        "PUT",
        f"/api/v1/repos/{OWNER}/{repo_name}/topics",
        gitea_token,
        {"topics": topics},
        (200, 204),
    )
    releases = _paginate(
        f"https://api.github.com/repos/{repository}/releases?per_page=100",
        _github_headers(github_token),
    )
    gitea_releases = _gitea_releases(gitea_token, repo_name)
    actions = plan_release_sync(releases, gitea_releases)
    _apply_releases(actions, gitea_token, repo_name)
    state = "Created" if created else "Updated"
    print(f"{state} https://gitea.com/{OWNER}/{repo_name} ({'private' if private else 'public'}).")
    print(f"Mirrored releases with {len(actions)} change(s).")


def settings_payload(repo: dict) -> dict:
    """Settings that exist on both GitHub and Gitea."""
    if "private" not in repo:
        raise SyncError("GitHub repository payload has no visibility.")
    homepage = str(repo.get("homepage") or "").strip()
    if not homepage.startswith(("https://", "http://")):
        homepage = ""
    payload = {
        "description": str(repo.get("description") or ""),
        "website": homepage,
        "private": bool(repo["private"]),
        "default_branch": str(repo.get("default_branch") or "").strip() or "main",
    }
    mapping = (
        ("has_issues", "has_issues"),
        ("has_wiki", "has_wiki"),
        ("has_projects", "has_projects"),
        ("allow_merge_commit", "allow_merge_commits"),
        ("allow_rebase_merge", "allow_rebase"),
        ("allow_squash_merge", "allow_squash_merge"),
        ("delete_branch_on_merge", "default_delete_branch_after_merge"),
        ("archived", "archived"),
    )
    for source, target in mapping:
        if repo.get(source) is not None:
            payload[target] = bool(repo[source])
    return payload


def sanitize_topics(topics: list) -> list[str]:
    cleaned: list[str] = []
    for topic in topics:
        text = str(topic or "").strip().lower().replace("_", "-").replace(" ", "-")
        text = re.sub(r"[^a-z0-9-]", "", text)
        text = re.sub(r"-{2,}", "-", text).strip("-")
        if not TOPIC_NAME.fullmatch(text) or text in cleaned:
            continue
        cleaned.append(text)
        if len(cleaned) == 25:
            break
    return cleaned


def github_release_view(release: dict) -> dict | None:
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
        "prerelease": bool(release.get("prerelease")),
        "links": links,
    }


def release_body(description: str, links: list[dict]) -> str:
    base = _strip_assets(description).rstrip()
    if not links:
        return base
    lines = [ASSET_START]
    for link in links:
        lines.append(f"- [{link['name']}]({link['url']})")
    lines.append(ASSET_END)
    block = "\n".join(lines)
    if not base:
        return block + "\n"
    return base + "\n\n" + block + "\n"


def plan_release_sync(github_releases: list, gitea_releases: list) -> list[dict]:
    existing = {}
    for item in gitea_releases:
        if isinstance(item, dict) and item.get("tag_name"):
            existing[str(item["tag_name"])] = item
    actions = []
    for raw in github_releases:
        view = github_release_view(raw)
        if view is None:
            continue
        body = release_body(view["description"], view["links"])
        current = existing.get(view["tag"])
        if current is None:
            actions.append({"op": "create", **view, "body": body})
            continue
        same = (
            _text(current.get("name")) == _text(view["name"])
            and _text(current.get("body")) == _text(body)
            and bool(current.get("prerelease")) == view["prerelease"]
        )
        if not same:
            actions.append({"op": "update", "id": current.get("id"), **view, "body": body})
    return actions


def _strip_assets(description: str) -> str:
    start = description.find(ASSET_START)
    end = description.find(ASSET_END)
    if start < 0 or end < start:
        return description
    return description[:start] + description[end + len(ASSET_END) :]


def _ensure_repo(token: str, repo_name: str, private: bool, default_branch: str) -> bool:
    status, _payload = _gitea("GET", f"/api/v1/repos/{OWNER}/{repo_name}", token, None, (200, 404))
    if status == 200:
        print(f"Gitea project {OWNER}/{repo_name} already exists.")
        return False
    status, payload = _gitea(
        "POST",
        "/api/v1/user/repos",
        token,
        {
            "name": repo_name,
            "private": private,
            "auto_init": False,
            "default_branch": default_branch,
        },
        (201,),
    )
    if status != 201 or not isinstance(payload, dict) or payload.get("private") is not private:
        raise SyncError(f"Gitea create returned {status} and visibility {getattr(payload, 'get', lambda *_: None)('private') if isinstance(payload, dict) else payload}.")
    print(f"Created Gitea project {OWNER}/{repo_name} ({'private' if private else 'public'}).")
    return True


def _ensure_privacy(token: str, repo_name: str, private: bool) -> None:
    status, payload = _gitea("GET", f"/api/v1/repos/{OWNER}/{repo_name}", token, None, (200,))
    if not isinstance(payload, dict) or payload.get("private") is private:
        return
    _gitea("PATCH", f"/api/v1/repos/{OWNER}/{repo_name}", token, {"private": private}, (200,))
    print(f"Set {OWNER}/{repo_name} visibility to {'private' if private else 'public'} before the push.")


def _apply_settings(token: str, repo_name: str, payload: dict) -> None:
    private = payload["private"]
    status, body = _gitea("PATCH", f"/api/v1/repos/{OWNER}/{repo_name}", token, payload, (200, 422))
    if status == 422:
        print("Gitea rejected one repository setting. The mirror keeps visibility, description, site, issues, wiki, projects, and the default branch.")
        core = ("description", "website", "private", "has_issues", "has_wiki", "has_projects", "default_branch")
        payload = {key: value for key, value in payload.items() if key in core}
        status, body = _gitea("PATCH", f"/api/v1/repos/{OWNER}/{repo_name}", token, payload, (200, 422))
    if status == 422:
        payload = dict(payload)
        payload["description"] = str(payload.get("description") or "")[:255]
        status, body = _gitea("PATCH", f"/api/v1/repos/{OWNER}/{repo_name}", token, payload, (200,))
        print("Shortened the description to the length Gitea accepted.")
    if not isinstance(body, dict) or body.get("private") is not private:
        raise SyncError("Gitea settings update did not keep GitHub visibility.")


def _apply_releases(actions: list[dict], token: str, repo_name: str) -> None:
    for action in actions:
        tag = action["tag"]
        body = {
            "tag_name": tag,
            "target_commitish": tag,
            "name": action["name"],
            "body": action["body"],
            "draft": False,
            "prerelease": action["prerelease"],
        }
        if action["op"] == "create":
            _create_release(token, repo_name, body)
            print(f"Created Gitea release {tag}.")
        elif action["op"] == "update":
            if action.get("id") is None:
                raise SyncError(f"Gitea release {tag} has no id.")
            _gitea("PATCH", f"/api/v1/repos/{OWNER}/{repo_name}/releases/{action['id']}", token, body, (200,))
            print(f"Updated Gitea release {tag}.")
        else:
            raise SyncError(f"Unknown release action {action['op']}.")


def _create_release(token: str, repo_name: str, body: dict) -> None:
    path = f"/api/v1/repos/{OWNER}/{repo_name}/releases"
    for attempt in range(4):
        status, payload = _gitea("POST", path, token, body, (201, 404, 409, 422))
        if status == 201:
            return
        if status == 409:
            current = next(
                (
                    item
                    for item in _gitea_releases(token, repo_name)
                    if isinstance(item, dict) and item.get("tag_name") == body["tag_name"]
                ),
                None,
            )
            if current is not None and current.get("id") is not None:
                _gitea(
                    "PATCH",
                    f"/api/v1/repos/{OWNER}/{repo_name}/releases/{current['id']}",
                    token,
                    body,
                    (200,),
                )
                return
        text = _snippet(payload).lower()
        if status in {404, 409, 422} and "tag" in text and attempt < 3:
            time.sleep(2)
            continue
        raise SyncError(f"Gitea release {body['tag_name']} returned {status}: {_snippet(payload)}")


def _push_refs(token: str, repo_name: str) -> None:
    _run(["git", "fetch", "origin", "+refs/heads/*:refs/remotes/origin/*", "+refs/tags/*:refs/tags/*"])
    listed = _run(["git", "for-each-ref", "--format=%(refname:strip=3)", "refs/remotes/origin"]).stdout
    refspecs = []
    for name in listed.splitlines():
        branch = name.strip()
        if not branch or branch == "HEAD":
            continue
        refspecs.append(f"+refs/remotes/origin/{branch}:refs/heads/{branch}")
    if not refspecs:
        raise SyncError("No branches were fetched to mirror.")
    if _run(["git", "tag"]).stdout.strip():
        refspecs.append("+refs/tags/*:refs/tags/*")
    askpass = Path("/tmp/gitea-askpass.sh")
    askpass.write_text(
        "#!/bin/sh\n"
        "case \"$1\" in\n"
        "  *Username*) printf '%s\\n' 'nargan' ;;\n"
        "  *) printf '%s\\n' \"$GITEA_TOKEN\" ;;\n"
        "esac\n",
        encoding="utf-8",
    )
    askpass.chmod(0o700)
    env = os.environ.copy()
    env["GIT_ASKPASS"] = str(askpass)
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GITEA_TOKEN"] = token
    try:
        _run(["git", "remote", "remove", "gitea"], check=False)
        _run(["git", "remote", "add", "gitea", f"{HOST}/{OWNER}/{repo_name}.git"])
        _run(["git", "-c", "credential.helper=", "push", "--prune", "gitea", *refspecs], env=env)
    finally:
        askpass.unlink(missing_ok=True)
    print(f"Pushed branches and tags to {OWNER}/{repo_name}.")


def _gitea_releases(token: str, repo_name: str) -> list:
    found = []
    for page in range(1, 31):
        status, payload = _gitea(
            "GET",
            f"/api/v1/repos/{OWNER}/{repo_name}/releases?limit=50&page={page}",
            token,
            None,
            (200,),
        )
        if not isinstance(payload, list):
            raise SyncError("Gitea releases response was not a list.")
        found.extend(payload)
        if len(payload) < 50:
            break
    return found


def _gitea(method: str, path: str, token: str, payload: dict | None, expected: tuple[int, ...]) -> tuple[int, object]:
    status, parsed = _request(
        method,
        HOST + path,
        {"Authorization": "token " + token, "Content-Type": "application/json", "Accept": "application/json"},
        payload,
    )
    if status not in expected:
        raise SyncError(f"Gitea {method} {path} returned {status}: {_snippet(parsed)}")
    return status, parsed


def _github_json(url: str, token: str) -> object:
    status, parsed = _request("GET", url, _github_headers(token), None)
    if status != 200:
        raise SyncError(f"GitHub returned {status} for {url}.")
    return parsed


def _github_headers(token: str) -> dict[str, str]:
    return {
        "Authorization": "Bearer " + token,
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "nargan-gitea-sync",
    }


def _paginate(url: str, headers: dict[str, str]) -> list:
    found = []
    while url:
        status, payload, response_headers = _raw(method="GET", url=url, headers=headers, payload=None)
        if status != 200:
            raise SyncError(f"GitHub returned {status} for {url}.")
        page = json.loads(payload.decode("utf-8"))
        if not isinstance(page, list):
            raise SyncError("GitHub returned an unexpected page.")
        found.extend(page)
        url = _next_url(url, response_headers)
    return found


def _request(method: str, url: str, headers: dict[str, str], payload: dict | None) -> tuple[int, object]:
    for attempt in range(3):
        status, raw, response_headers = _raw(method, url, headers, payload)
        if status == 429 and attempt < 2:
            time.sleep(int(response_headers.get("Retry-After") or 5))
            continue
        text = raw.decode("utf-8", "replace")
        text = _redact(text)
        try:
            parsed = json.loads(text) if text else None
        except json.JSONDecodeError:
            parsed = text[:500]
        return status, parsed
    raise SyncError(f"{method} {url} stayed rate limited.")


def _raw(method: str, url: str, headers: dict[str, str], payload: dict | None) -> tuple[int, bytes, dict[str, str]]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            return int(response.status), response.read(), dict(response.headers.items())
    except urllib.error.HTTPError as error:
        body = error.read() if error.fp is not None else b""
        response_headers = {key: value for key, value in error.headers.items()} if error.headers else {}
        return int(error.code), body, response_headers


def _run(args: list[str], env: dict | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(args, cwd=Path.cwd(), env=env, text=True, capture_output=True)
    if check and result.returncode != 0:
        detail = _redact((result.stderr or result.stdout or "git command failed")[-2000:])
        raise SyncError(detail)
    return result


def _next_url(url: str, headers: dict[str, str]) -> str:
    link = headers.get("Link") or headers.get("link") or ""
    for part in link.split(","):
        if 'rel="next"' not in part:
            continue
        start = part.find("<")
        end = part.find(">")
        if start >= 0 and end > start:
            return part[start + 1 : end]
    return ""


def _env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise SyncError(f"Secret {name} is missing on this repository.")
    return value


def _text(value: object) -> str:
    return str(value or "").replace("\r\n", "\n").strip()


def _snippet(payload: object) -> str:
    if isinstance(payload, (dict, list)):
        text = json.dumps(payload, ensure_ascii=True)
    else:
        text = str(payload or "")
    return _redact(text)[:500]


def _redact(text: str) -> str:
    token = os.environ.get("GITEA_TOKEN", "").strip()
    github = os.environ.get("GITHUB_TOKEN", "").strip()
    if token:
        text = text.replace(token, "[redacted]")
    if github:
        text = text.replace(github, "[redacted]")
    return text


if __name__ == "__main__":
    try:
        main()
    except SyncError as exc:
        raise SystemExit(str(exc)) from exc
