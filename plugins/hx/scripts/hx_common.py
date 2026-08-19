"""Shared helpers for hx-flow scripts.

Python 3.9+, stdlib ONLY. No dependency will ever be added — these scripts must run in every
target repo without an install step.

This file contains no language- or framework-specific knowledge. Stack knowledge lives in
`.flow/checks.md` and in `plugins/hx-flow/data/`.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

# The Windows console defaults to cp1252 and crashes on non-ASCII output. These scripts also
# run in CI, so pin the output streams to UTF-8. Every entrypoint needs this.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    except (AttributeError, ValueError, OSError):
        pass

COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
PLACEHOLDER_RE = re.compile(r"<[^<>\n]{1,60}>")
HEADING_RE = re.compile(r"^##\s+(.+?)\s*$")
TABLE_SEP_RE = re.compile(r"^\|[\s:|-]+\|$")
FIELD_RE = re.compile(r"^([A-Za-z][A-Za-z0-9\-]*):\s*(.*)$")


def strip_comments(text: str) -> str:
    return COMMENT_RE.sub("", text)


def effective_lines(text: str) -> list[str]:
    """Meaningful lines, excluding comments and blanks. Line budgets are measured on these."""
    return [ln for ln in strip_comments(text).splitlines() if ln.strip()]


def sections(text: str) -> dict[str, str]:
    """'## Heading' -> body. Order preserved."""
    out: dict[str, str] = {}
    cur, buf = None, []
    for line in strip_comments(text).splitlines():
        m = HEADING_RE.match(line)
        if m:
            if cur is not None:
                out[cur] = "\n".join(buf).strip()
            cur, buf = m.group(1), []
        elif cur is not None:
            buf.append(line)
    if cur is not None:
        out[cur] = "\n".join(buf).strip()
    return out


def find_section(secs: dict[str, str], prefix: str):
    """First section whose heading starts with `prefix`, as (name, body). (None, None) if absent."""
    low = prefix.lower()
    for name, body in secs.items():
        if name.lower().startswith(low):
            return name, body
    return None, None


def front_fields(text: str) -> dict[str, str]:
    """'key: value' lines appearing BEFORE the first '## ' heading."""
    fields: dict[str, str] = {}
    for line in strip_comments(text).splitlines():
        if line.startswith("## "):
            break
        m = FIELD_RE.match(line.strip())
        if m:
            fields[m.group(1).lower()] = m.group(2).strip()
    return fields


def table_rows(body: str, drop_header: bool = True) -> list[list[str]]:
    """Markdown table rows as cell lists; the separator row is skipped."""
    rows: list[list[str]] = []
    for line in body.splitlines():
        s = line.strip()
        if not s.startswith("|") or TABLE_SEP_RE.match(s):
            continue
        rows.append([c.strip() for c in s.strip("|").split("|")])
    if drop_header and rows:
        return rows[1:]
    return rows


def has_placeholder(value: str) -> bool:
    """True when a template <placeholder> or an unfilled marker is still present."""
    if not value or not value.strip():
        return True
    v = value.strip()
    if PLACEHOLDER_RE.search(v):
        return True
    return v.upper() in {"TODO", "TBD", "?", "-", "N/A"}


def pattern_to_regex(pat: str) -> re.Pattern:
    """Translate a repo-map allowed pattern into a regex.

    <name>    -> a single path segment
    **/       -> zero or more directories
    *         -> within-segment wildcard
    {a,b,c}   -> alternatives
    """
    pat = pat.strip().strip("`").replace("\\", "/")
    out: list[str] = []
    i = 0
    while i < len(pat):
        if pat[i] == "<":
            j = pat.find(">", i)
            if j == -1:
                out.append(re.escape(pat[i]))
                i += 1
                continue
            out.append(r"[^/]+")
            i = j + 1
        elif pat.startswith("**/", i):
            out.append(r"(?:[^/]+/)*")
            i += 3
        elif pat.startswith("**", i):
            out.append(r".*")
            i += 2
        elif pat[i] == "*":
            out.append(r"[^/]*")
            i += 1
        elif pat[i] == "{":
            j = pat.find("}", i)
            if j == -1:
                out.append(re.escape(pat[i]))
                i += 1
                continue
            alts = [re.escape(a.strip()) for a in pat[i + 1:j].split(",")]
            out.append("(?:" + "|".join(alts) + ")")
            i = j + 1
        else:
            out.append(re.escape(pat[i]))
            i += 1
    return re.compile("^" + "".join(out) + "$")


def parse_checks(text: str) -> dict[str, dict[str, str]]:
    """checks.md -> {scope_name: {capability: command}}. Ungrouped lines go under '_global'."""
    out: dict[str, dict[str, str]] = {"_global": {}}
    cur = "_global"
    for raw in strip_comments(text).splitlines():
        line = raw.rstrip()
        if not line.strip():
            continue
        m = re.match(r"^(?:scope\s+(\S+)|(security))\s*$", line.strip(), re.I)
        if m:
            cur = (m.group(1) or m.group(2)).lower()
            out.setdefault(cur, {})
            continue
        m = FIELD_RE.match(line.strip())
        if m:
            key, val = m.group(1).lower(), m.group(2).strip()
            val = re.sub(r"\s+#\s.*$", "", val).strip()  # drop trailing comment
            if val and not has_placeholder(val):
                out[cur][key] = val
    return out


def git(*args: str, cwd: Path | None = None, strip: bool = True) -> tuple[str, int]:
    """Run git. `strip=False` when the output is COLUMN-SENSITIVE.

    `git status --porcelain` emits `XY<space>PATH`, and X is a space for a change that is not
    staged. Stripping the whole output removes that leading space from the FIRST line only, which
    shifts its path by one character - `requirements.txt` is read as `equirements.txt`. The file
    then matches no manifest and no placement rule, so the dependency gate is silently skipped and
    the placement contract is checked against a path that does not exist. Only the first line is
    affected and only when it is an unstaged change, which is why this survived every test: the
    fixtures never commit, so every file is untracked and every line starts with `??`.
    """
    try:
        r = subprocess.run(
            ["git", *args], cwd=str(cwd) if cwd else None,
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        out = r.stdout or ""
        return (out.strip() if strip else out.rstrip("\n")), r.returncode
    except FileNotFoundError:
        return "", 127


def changed_files(repo: Path, base: str | None = None) -> tuple[list[str], list[str]]:
    """(added, modified) paths. When `base` is given, also diff from that ref."""
    added, modified = [], []
    # -uall is required: by default git summarises untracked DIRECTORIES on one line,
    # which makes per-file inspection of new files impossible.
    out, _ = git("status", "--porcelain", "-uall", cwd=repo, strip=False)
    for line in out.splitlines():
        if len(line) < 4:
            continue
        code, path = line[:2], line[3:].strip().strip('"')
        if "->" in path:  # rename
            path = path.split("->")[-1].strip()
        if code.strip() in {"A", "??", "AM"} or code.startswith("A"):
            added.append(path)
        else:
            modified.append(path)
    if base:
        out, rc = git("diff", "--name-status", f"{base}...HEAD", cwd=repo)
        if rc == 0:
            for line in out.splitlines():
                parts = line.split("\t")
                if len(parts) < 2:
                    continue
                st, path = parts[0], parts[-1]
                (added if st.startswith("A") else modified).append(path)
    dedup = lambda xs: sorted(dict.fromkeys(xs))
    return dedup(added), dedup(modified)


def bash_path() -> str | None:
    """Locate a POSIX shell. On Windows this is usually Git Bash."""
    found = shutil.which("bash")
    if found:
        return found
    for candidate in (r"C:\Program Files\Git\bin\bash.exe",
                      r"C:\Program Files (x86)\Git\bin\bash.exe"):
        if Path(candidate).is_file():
            return candidate
    return None


def run_cmd(cmd: str, cwd: Path, timeout: int = 600,
            shell: str = "auto") -> tuple[int, str]:
    """Run a declared command. Returns (exit code, combined output).

    SHELL SELECTION MATTERS AND IS NOT COSMETIC. Declared commands in `.flow/checks.md` are
    written in POSIX syntax (`&&`, `||`, pipes, `/dev/null`). Python's `shell=True` runs cmd.exe
    on Windows, where `/dev/null` does not exist — so a perfectly good command SILENTLY FAILS and
    the caller records a FAIL that is not real. A wrong result is worse than a crash, so the
    default prefers a POSIX shell and only falls back to the platform shell when none exists.

    shell: "bash" (require POSIX), "platform" (cmd.exe / sh), or "auto" (POSIX if available).
    """
    argv: list[str] | str
    if shell in ("auto", "bash"):
        bash = bash_path()
        if bash:
            argv = [bash, "-c", cmd]
        elif shell == "bash":
            return 127, ("no POSIX shell found but checks.md requests shell: bash "
                         "(install Git Bash, or set shell: platform)")
        else:
            argv = cmd
    else:
        argv = cmd
    try:
        r = subprocess.run(
            argv, cwd=str(cwd), shell=isinstance(argv, str), capture_output=True,
            # stdin MUST be closed. A declared command that reads stdin - a PreToolUse hook
            # wrapped as a check is the common case - otherwise blocks forever waiting for input
            # that will never arrive, and the phase hangs instead of failing.
            stdin=subprocess.DEVNULL,
            text=True, encoding="utf-8", errors="replace", timeout=timeout,
        )
        return r.returncode, ((r.stdout or "") + (r.stderr or "")).strip()
    except subprocess.TimeoutExpired:
        return 124, f"timed out after {timeout}s"
    except OSError as e:
        return 126, str(e)


def checks_shell(flow_root_dir: Path) -> str:
    """Read the `shell:` preference from checks.md. Defaults to 'auto'."""
    path = flow_root_dir / "checks.md"
    if not path.is_file():
        return "auto"
    raw = front_fields(path.read_text(encoding="utf-8")).get("shell", "auto")
    value = re.sub(r"\s*#.*$", "", raw).strip().lower()  # strip a trailing comment
    return value if value in {"auto", "bash", "platform"} else "auto"


def tail(text: str, n: int = 1, width: int = 110) -> str:
    lines = [ln for ln in text.splitlines() if ln.strip()]
    return " / ".join(lines[-n:])[:width] if lines else ""


def last_int(text: str) -> int | None:
    """The LAST integer in a command's output. Measure commands must print a number."""
    nums = re.findall(r"-?\d+", text)
    return int(nums[-1]) if nums else None


def canary_secret_scan(cmd: str, repo: Path, shell: str) -> tuple[str, str]:
    """Prove the declared secret scanner can actually catch a secret.

    WHY. `exit 0` from a secret scanner means one of two very different things: "nothing found" or
    "I did not look". A PreToolUse hook that expects a JSON envelope on stdin exits 0 when handed
    nothing; a scanner whose dependency is missing often exits 0 too. Either way the ship gate
    passes forever while protecting nothing - the worst possible failure for a security control.

    So: plant an obviously fake, high-signal secret in the working tree, run the declared command,
    and require it to fail. Anything else means the gate is not effective as configured.

    The planted file is always removed.
    """
    canary = repo / "HX_CANARY_DELETE_ME.txt"
    planted = (
        "# hx-flow canary, written and deleted immediately. Not a real credential.\n"
        "AWS_SECRET_ACCESS_KEY = \"wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY\"\n"
        "-----BEGIN RSA PRIVATE KEY-----\n"
        "MIIEowIBAAKCAQEA7Vx9cQnFakeKeyMaterialForCanaryPurposesOnly0000\n"
        "-----END RSA PRIVATE KEY-----\n"
    )
    try:
        canary.write_text(planted, encoding="utf-8")
    except OSError as e:
        return "SKIP", f"could not plant a canary ({e})"
    try:
        rc, _ = run_cmd(cmd, repo, timeout=120, shell=shell)
    finally:
        try:
            canary.unlink()
        except OSError:
            pass
    if rc != 0:
        return "PASS", "a planted secret was detected"
    return "FAIL", ("a planted secret was NOT detected - not an effective gate as configured. "
                    "A hook reading a JSON envelope on stdin, or a scanner with a missing "
                    "dependency, exits 0 without looking. Declare a real working-tree scan.")


def flow_root(start: Path | None = None) -> Path | None:
    """Find the nearest `.flow/` directory by walking upwards."""
    p = (start or Path.cwd()).resolve()
    for d in [p, *p.parents]:
        if (d / ".flow").is_dir():
            return d / ".flow"
    return None


def plugin_data(name: str) -> dict:
    """Read plugins/hx-flow/data/<name>."""
    path = Path(__file__).resolve().parent.parent / "data" / name
    return json.loads(path.read_text(encoding="utf-8"))


class Report:
    """A PASS/FAIL table. The determinism claim itself should be a table, not prose."""

    def __init__(self, title: str):
        self.title = title
        self.items: list[tuple[str, str, str]] = []  # (status, check, detail)

    def add(self, status: str, check: str, detail: str = "") -> None:
        self.items.append((status, check, detail))

    def ok(self, check: str, detail: str = "") -> None:
        self.add("PASS", check, detail)

    def fail(self, check: str, detail: str = "") -> None:
        self.add("FAIL", check, detail)

    def skip(self, check: str, detail: str = "") -> None:
        self.add("SKIP", check, detail)

    @property
    def failures(self) -> list[tuple[str, str, str]]:
        return [i for i in self.items if i[0] == "FAIL"]

    def emit(self, as_json: bool = False) -> int:
        if as_json:
            print(json.dumps({
                "title": self.title,
                "pass": not self.failures,
                "items": [{"status": s, "check": c, "detail": d} for s, c, d in self.items],
            }, ensure_ascii=False, indent=2))
        else:
            print()
            print(self.title)
            print(f"{'status':<6}  {'check':<38}  detail")
            print("-" * 100)
            for s, c, d in self.items:
                print(f"{s:<6}  {c[:38]:<38}  {d}")
            print("-" * 100)
            n = len(self.failures)
            verdict = "ALL PASSED" if n == 0 else f"{n} CHECK(S) FAILED"
            print(f"{verdict}   ({len(self.items)} checks)")
        return 1 if self.failures else 0
