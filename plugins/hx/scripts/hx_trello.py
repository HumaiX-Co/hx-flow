#!/usr/bin/env python3
"""hx-trello — a thin Trello REST wrapper. Deterministic subcommands that spend no model tokens.

Why this exists next to the official MCP: `mcp.trello.com/v1` cannot write comments, attachments
or custom fields ("coming soon"), and linking a card to its PR in the `ship` phase depends on
exactly those. Declaring that server in the plugin would also put its tool schemas into every
session's always-on context, including sessions that never touch Trello. So this script is the
floor and MCP is the upgrade. Routing rule: `playbooks/trello.md`.

Credentials: HX_TRELLO_KEY + HX_TRELLO_TOKEN environment variables.
To obtain a key you must first create a Power-Up at trello.com/apps/admin.

Authority rule: writes are ONE-WAY (flow -> Trello). Reads happen only through `card get`, at
/hx:pull time. Two-way sync would require conflict handling and eat the whole point.

Usage:
    hx_trello.py card get <shortLink>
    hx_trello.py card move <shortLink> <list-name>
    hx_trello.py card comment <shortLink> (<text> | @file)
    hx_trello.py card attach <shortLink> <url> [name]
    hx_trello.py checklist sync <shortLink> <plan.md>
    hx_trello.py checklist check <shortLink> <slice-id>
    hx_trello.py field set <shortLink> <field-name> <value>
    hx_trello.py board lists <shortLink>        # caches the list-name -> id map
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from hx_common import find_section, flow_root, sections, table_rows

API = "https://api.trello.com/1"
CHECKLIST_NAME = "Slices"


def creds() -> tuple[str, str]:
    key, token = os.environ.get("HX_TRELLO_KEY"), os.environ.get("HX_TRELLO_TOKEN")
    if not key or not token:
        sys.exit("error: HX_TRELLO_KEY and HX_TRELLO_TOKEN are not set.\n"
                 "Create a Power-Up at trello.com/apps/admin and use its API Key tab.")
    return key, token


def call(method: str, path: str, params: dict | None = None) -> object:
    key, token = creds()
    q = {**(params or {}), "key": key, "token": token}
    url = f"{API}{path}?" + urllib.parse.urlencode(q, doseq=True)
    req = urllib.request.Request(url, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read().decode("utf-8")
            return json.loads(body) if body.strip() else {}
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:300]
        sys.exit(f"error: Trello {e.code} {method} {path}\n{detail}")
    except urllib.error.URLError as e:
        sys.exit(f"error: could not reach Trello: {e.reason}")


def card(short: str) -> dict:
    return call("GET", f"/cards/{short}", {
        "fields": "name,desc,idList,idBoard,shortUrl,shortLink",
        "checklists": "all",
    })  # type: ignore[return-value]


def list_map(short: str, refresh: bool = False) -> dict[str, str]:
    """List name -> id, cached in .flow/trello.json so phase transitions cost no API round trip."""
    root = flow_root()
    cache_path = (root / "trello.json") if root else None
    if cache_path and cache_path.is_file() and not refresh:
        try:
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            if cached.get("lists"):
                return cached["lists"]
        except (json.JSONDecodeError, OSError):
            pass
    board = card(short)["idBoard"]
    lists = call("GET", f"/boards/{board}/lists", {"fields": "name"})
    mapping = {item["name"]: item["id"] for item in lists}  # type: ignore[union-attr]
    if cache_path:
        cache_path.write_text(
            json.dumps({"idBoard": board, "lists": mapping}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8")
    return mapping


def slices_from_plan(plan: Path) -> list[tuple[str, str]]:
    _, body = find_section(sections(plan.read_text(encoding="utf-8")), "Slice table")
    out = []
    for row in table_rows(body or ""):
        if len(row) >= 2 and row[0].strip():
            out.append((row[0].strip(), row[1].strip()))
    return out


def find_checklist(c: dict, name: str = CHECKLIST_NAME) -> dict | None:
    for cl in c.get("checklists", []):
        if cl.get("name") == name:
            return cl
    return None


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="hx-flow Trello wrapper")
    sub = ap.add_subparsers(dest="group", required=True)

    c = sub.add_parser("card").add_subparsers(dest="op", required=True)
    c.add_parser("get").add_argument("short")
    m = c.add_parser("move"); m.add_argument("short"); m.add_argument("list_name")
    cm = c.add_parser("comment"); cm.add_argument("short"); cm.add_argument("text")
    at = c.add_parser("attach"); at.add_argument("short"); at.add_argument("url")
    at.add_argument("name", nargs="?")

    cl = sub.add_parser("checklist").add_subparsers(dest="op", required=True)
    s = cl.add_parser("sync"); s.add_argument("short"); s.add_argument("plan")
    ck = cl.add_parser("check"); ck.add_argument("short"); ck.add_argument("slice_id")

    f = sub.add_parser("field").add_subparsers(dest="op", required=True)
    fs = f.add_parser("set"); fs.add_argument("short"); fs.add_argument("field")
    fs.add_argument("value")

    b = sub.add_parser("board").add_subparsers(dest="op", required=True)
    bl = b.add_parser("lists"); bl.add_argument("short")
    bl.add_argument("--refresh", action="store_true")
    return ap


def main() -> int:
    a = build_parser().parse_args()

    if a.group == "card" and a.op == "get":
        c0 = card(a.short)
        print(json.dumps({
            "shortLink": c0.get("shortLink"), "name": c0.get("name"),
            "desc": c0.get("desc"), "shortUrl": c0.get("shortUrl"),
            "checklists": [{"name": x["name"],
                            "items": [{"name": i["name"], "state": i["state"]}
                                      for i in x.get("checkItems", [])]}
                           for x in c0.get("checklists", [])],
        }, ensure_ascii=False, indent=2))
        return 0

    if a.group == "card" and a.op == "move":
        lists = list_map(a.short)
        if a.list_name not in lists:
            sys.exit(f"error: no list named '{a.list_name}'. "
                     f"Available: {', '.join(sorted(lists))}")
        call("PUT", f"/cards/{a.short}", {"idList": lists[a.list_name]})
        print(f"card {a.short} -> {a.list_name}")
        return 0

    if a.group == "card" and a.op == "comment":
        text = a.text
        if text.startswith("@"):
            text = Path(text[1:]).read_text(encoding="utf-8")
        call("POST", f"/cards/{a.short}/actions/comments", {"text": text[:16000]})
        print(f"comment added ({len(text)} chars)")
        return 0

    if a.group == "card" and a.op == "attach":
        params = {"url": a.url}
        if a.name:
            params["name"] = a.name
        call("POST", f"/cards/{a.short}/attachments", params)
        print(f"attachment added: {a.url}")
        return 0

    if a.group == "checklist" and a.op == "sync":
        items = slices_from_plan(Path(a.plan))
        if not items:
            sys.exit("error: no slices found in plan.md")
        c0 = card(a.short)
        existing = find_checklist(c0)
        if existing:
            have = {i["name"] for i in existing.get("checkItems", [])}
            cid = existing["id"]
        else:
            cid = call("POST", f"/cards/{a.short}/checklists",
                       {"name": CHECKLIST_NAME})["id"]  # type: ignore[index]
            have = set()
        added = 0
        for sid, goal in items:
            label = f"{sid} {goal}"[:16000]
            if label not in have:
                call("POST", f"/checklists/{cid}/checkItems",
                     {"name": label, "checked": "false"})
                added += 1
        print(f"checklist '{CHECKLIST_NAME}': {added} new item(s), {len(items)} slice(s)")
        return 0

    if a.group == "checklist" and a.op == "check":
        c0 = card(a.short)
        cl0 = find_checklist(c0)
        if not cl0:
            sys.exit(f"error: no '{CHECKLIST_NAME}' checklist. Run `checklist sync` first.")
        for item in cl0.get("checkItems", []):
            if item["name"].split()[0] == a.slice_id:
                call("PUT", f"/cards/{c0['shortLink']}/checkItem/{item['id']}",
                     {"state": "complete"})
                print(f"{a.slice_id} marked complete")
                return 0
        sys.exit(f"error: {a.slice_id} not found in the checklist")

    if a.group == "field" and a.op == "set":
        c0 = card(a.short)
        fields = call("GET", f"/boards/{c0['idBoard']}/customFields")
        target = next((x for x in fields if x.get("name") == a.field), None)  # type: ignore[union-attr]
        if not target:
            names = ", ".join(sorted(x.get("name", "") for x in fields))  # type: ignore[union-attr]
            sys.exit(f"error: no custom field named '{a.field}'. Available: {names or 'none'}")
        call("PUT", f"/cards/{c0.get('id', a.short)}/customField/{target['id']}/item",
             {"value": json.dumps({"text": a.value})})
        print(f"{a.field} = {a.value}")
        return 0

    if a.group == "board" and a.op == "lists":
        for name in sorted(list_map(a.short, refresh=a.refresh)):
            print(name)
        return 0

    return 2


if __name__ == "__main__":
    sys.exit(main())
