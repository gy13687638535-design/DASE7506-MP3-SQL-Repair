#!/usr/bin/env python3
"""Explicit, append-only GitHub publication using the existing Git credential helper.

Credentials are passed in memory only, never printed or written to files. This helper
does not push source commits, update/delete resources, or replace release assets.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request


class GitHub:
    def __init__(self, expected_login: str):
        environment = dict(os.environ, GIT_TERMINAL_PROMPT="0", GCM_INTERACTIVE="Never")
        result = subprocess.run(
            ["git", "credential", "fill"],
            input=f"protocol=https\nhost=github.com\nusername={expected_login}\n\n",
            capture_output=True, text=True, env=environment, timeout=30, check=False,
        )
        if result.returncode:
            raise RuntimeError("Git credential helper could not supply the existing login; no credential output was displayed.")
        credential = dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)
        self._token = credential.get("password")
        if not self._token:
            raise RuntimeError("The existing Git credential has no access token.")
        profile = self.request("GET", "/user")
        if profile.get("login", "").casefold() != expected_login.casefold():
            raise RuntimeError("The stored Git credential belongs to a different account.")
        self.login = profile["login"]

    def request(self, method: str, path: str, payload=None, *, upload: Path | None = None):
        url = path if path.startswith("https://") else "https://api.github.com" + path
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme != "https" or parsed.hostname not in {"api.github.com", "uploads.github.com"}:
            raise ValueError("Only the official GitHub API and asset upload host are allowed.")
        if parsed.username or parsed.password or parsed.port not in (None, 443):
            raise ValueError("Unexpected URL credentials or port.")
        headers = {"Authorization": "Bearer " + self._token, "Accept": "application/vnd.github+json",
                   "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "DASE7506-MP3-Publication"}
        data = None
        if upload is not None:
            data = upload.read_bytes()
            headers["Content-Type"] = "application/zip"
        elif payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            # Response bodies and request headers are deliberately not logged.
            raise RuntimeError(f"GitHub returned HTTP {exc.code} for {method} {parsed.path}; nothing was overwritten.") from None
        except urllib.error.URLError:
            raise RuntimeError("Could not reach GitHub. Check network or sandbox permissions.") from None


def repository(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", value):
        raise argparse.ArgumentTypeError("Expected owner/repository")
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--login", required=True, help="Expected already-authenticated GitHub username")
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create-repo", help="Create a new public repository; existing names are rejected")
    create.add_argument("--name", required=True)
    create.add_argument("--description", required=True)
    release = commands.add_parser("release", help="Create a new release and upload one ZIP; never replaces assets")
    release.add_argument("--repo", type=repository, required=True)
    release.add_argument("--tag", required=True)
    release.add_argument("--commit", required=True, help="Full immutable 40-character source commit")
    release.add_argument("--title", required=True)
    release.add_argument("--asset", type=Path, required=True)
    release.add_argument("--notes-file", type=Path, required=True)
    issue = commands.add_parser("issue", help="Create a new issue using exact prepared text")
    issue.add_argument("--repo", type=repository, required=True)
    issue.add_argument("--title-file", type=Path, required=True)
    issue.add_argument("--body-file", type=Path, required=True)
    args = parser.parse_args()

    # Validate all local inputs before contacting GitHub or creating any resource.
    if args.command == "create-repo":
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", args.name):
            raise ValueError("Invalid new repository name")
    elif args.command == "release":
        if not re.fullmatch(r"[a-f0-9]{40}", args.commit):
            raise ValueError("Release target must be a full commit SHA")
        if not args.asset.is_file() or args.asset.suffix.lower() != ".zip":
            raise ValueError("Release asset must be an existing ZIP file")
        if args.asset.stat().st_size > 16 * 1024 * 1024:
            raise ValueError("Source ZIP exceeds the 16 MiB route budget")
        notes = args.notes_file.read_text(encoding="utf-8")
    else:
        title = args.title_file.read_text(encoding="utf-8").strip()
        body = args.body_file.read_text(encoding="utf-8")
        if not title or not body:
            raise ValueError("Issue title and body must be nonempty")

    api = GitHub(args.login)
    if args.command == "create-repo":
        result = api.request("POST", "/user/repos", {"name": args.name, "description": args.description,
                             "private": False, "auto_init": False, "has_issues": True})
        output = {"action": "created_repository", "url": result["html_url"], "full_name": result["full_name"]}
    elif args.command == "release":
        if args.repo.split("/")[0].casefold() != api.login.casefold():
            raise ValueError("Only releases in the authenticated user's repository are permitted")
        result = api.request("POST", f"/repos/{args.repo}/releases", {
            "tag_name": args.tag, "target_commitish": args.commit, "name": args.title,
            "body": notes, "draft": False, "prerelease": False, "generate_release_notes": False,
        })
        upload_url = result["upload_url"].split("{", 1)[0] + "?" + urllib.parse.urlencode({"name": args.asset.name})
        asset = api.request("POST", upload_url, upload=args.asset)
        output = {"action": "created_release", "url": result["html_url"], "id": result["id"],
                  "asset_url": asset["browser_download_url"], "asset_id": asset["id"]}
    else:
        result = api.request("POST", f"/repos/{args.repo}/issues", {"title": title, "body": body})
        output = {"action": "created_issue", "url": result["html_url"], "number": result["number"]}
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, ValueError, OSError, subprocess.TimeoutExpired) as exc:
        print(f"Publication stopped: {exc}", file=sys.stderr)
        raise SystemExit(1)
