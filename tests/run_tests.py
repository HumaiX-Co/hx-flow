#!/usr/bin/env python3
"""Regression tests for the hx-flow scripts.

Sets up a temporary git repository, writes artifact fixtures, runs each script and asserts the
EXPECTED exit code. A validator that merely "passes" proves nothing; it must also be shown to
catch bad input — which is why half of these scenarios expect FAIL.

Usage: python tests/run_tests.py
Exit:  0 = every scenario behaved as expected, 1 = at least one deviation
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "plugins" / "hx" / "scripts"
HOOKS = ROOT / "plugins" / "hx" / "hooks"
TEMPLATES = ROOT / "plugins" / "hx" / "templates"


def template_slice_status() -> str:
    """Whatever `templates/state.md` ships under 'Slice status'.

    This is the value a freshly discussed feature carries: `discuss` runs before `plan`, so no
    slice exists yet, and `discuss` refuses to finish until hx-lint passes. Reading it from the
    real template rather than restating it is the point - a placeholder added here must fail the
    suite, not the developer.
    """
    body = TEMPLATES.joinpath("state.md").read_text(encoding="utf-8").split("## Slice status", 1)[1]
    lines = [ln for ln in body.splitlines() if ln.strip() and "<!--" not in ln and "-->" not in ln]
    return lines[0] if lines else ""

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    except (AttributeError, ValueError, OSError):
        pass

REPO_MAP = """# repo-map
produced: 2026-08-17
last delta: 2026-08-17

## Scopes
| scope | what | entry point |
|-------|------|-------------|
| backend/ | API | backend/main.py |

## Layers
| layer | location | responsibility |
|-------|----------|----------------|
| router | backend/<domain>/router.py | HTTP |

## Placement rules (allowed patterns) — CONTRACT
| rule name | new what | allowed pattern | extra requirement |
|-----------|----------|-----------------|-------------------|
| router | endpoint | backend/<domain>/router.py | - |
| model | data model | backend/<domain>/models.py | requires:backend/migrations/** |
| migration | migration | backend/migrations/** | - |

## Naming
| what | rule | example |
|------|------|---------|
| test | test_<domain>_*.py | test_billing_split.py |

## Test placement
| scope | location | naming | how to run |
|-------|----------|--------|------------|
| backend/ | backend/tests | test_*.py | <runner> |
"""

CHECKS = """platform: linux-ci
runner: none
verified: 2026-08-17

scope backend/
  lint:        echo lint-ok
  test-unit:   echo test {pattern}

security
  audit-block: %(audit_block)s
  audit-count: %(audit_count)s
  secret-scan: %(secret_scan)s
"""

STATE_OK = """# invoice-split

phase: plan
trello: aB3xYz9
branch: feature/aB3xYz9-invoice-split
updated: 2026-08-17

## Intent
Split an invoice line with proportional VAT distribution.

## Scope
IN:  line splitting, proportional VAT
OUT: multi-currency, refund flow

## Module decision
type: general
feature-flag: invoice_split
default: off

## Dependency decision
%(dep)s

## Acceptance criteria
- [ ] AC1 Split line VAT totals match the original within 0.01
- [ ] AC2 `POST /invoices/{id}/split` returns HTTP 200 and produces 2 lines

## Decisions
- D1 Use decimal arithmetic — rationale: float rounding error is unacceptable

## Open questions
- Q1 Is a three-way split required → owner: user

## Slice status
S1 done | S2 todo
"""

PLAN_OK = """# invoice-split — plan

## Slice table
| id | goal | scope | touches | verification | depends |
|----|------|-------|---------|--------------|---------|
| S1 | split domain method | backend/ | backend/billing/models.py | test-unit:split | - |
| S2 | endpoint | backend/ | backend/billing/router.py | test-unit:router | S1 |

## Placement check
| slice | rule satisfied |
|-------|----------------|
| S1 | model |
| S2 | router |

## Slices requiring migration
S1

## Acceptance mapping
| AC | covered by |
|----|------------|
| AC1 | S1 |
| AC2 | S2 |

## Pre-ship one-time checks
- test-all

## Risks
- Rounding drift → mitigation: decimal arithmetic plus the AC1 test
"""

STATE_BAD = """# bad-example

phase: coding
updated: 2026-08-17

## Intent
We will build some things.

## Scope
IN:  everything
OUT:

## Module decision
type: <general|customer-specific>
feature-flag: <flag name|none>
default: off

## Dependency decision
no new dependencies

## Acceptance criteria
- [ ] AC1 The system works properly
- [ ] AC2 It will be performant

## Decisions
- D1 a decision — rationale: a reason

## Open questions
- Q1 a question → owner: user

## Slice status
S1 todo
"""

PLAN_BAD = """# bad-example — plan

## Slice table
| id | goal | scope | touches | verification | depends |
|----|------|-------|---------|--------------|---------|
| S1 | full stack | backend/ | backend/a/router.py frontend/components/x/Y.tsx | test-unit:a | - |
| S1 | duplicate | backend/ | backend/b/router.py |  | - |

## Placement check
| slice | rule satisfied |
|-------|----------------|
| S1 | router |

## Slices requiring migration
none

## Acceptance mapping
| AC | covered by |
|----|------------|
| AC1 | S1 |

## Pre-ship one-time checks
- test-all

## Risks
- a risk → mitigation: something
"""

PASS_CMD, FAIL_CMD = "exit 0", "exit 1"

# An EFFECTIVE scanner looks at the working tree: it fails when a planted secret exists.
# The pattern is written so it does not match its own declaration inside checks.md:
# as a regex PRIVAT[E] matches "PRIVATE", but the literal text "PRIVAT[E]" does not.
EFFECTIVE_SCAN = "! grep -rqIE 'PRIVAT[E] KEY' . 2>/dev/null"
# An INEFFECTIVE scanner is the dangerous case: it exits 0 without looking. A PreToolUse hook
# handed no stdin envelope behaves exactly like this, and the ship gate then passes forever.
INEFFECTIVE_SCAN = "cat > /dev/null; exit 0"   # reads stdin like a hook, then passes blindly


class Fixture:
    def __init__(self, base: Path):
        self.repo = base
        self.flow = base / ".flow"
        (self.flow / "features" / "demo").mkdir(parents=True)
        (self.flow / "features" / "bad").mkdir(parents=True)
        (base / "backend" / "billing").mkdir(parents=True)
        (base / "backend" / "migrations").mkdir(parents=True)
        (self.flow / "repo-map.md").write_text(REPO_MAP, encoding="utf-8")
        self.write_checks()
        self.write_state()
        (self.flow / "features" / "demo" / "plan.md").write_text(PLAN_OK, encoding="utf-8")
        (self.flow / "features" / "bad" / "state.md").write_text(STATE_BAD, encoding="utf-8")
        (self.flow / "features" / "bad" / "plan.md").write_text(PLAN_BAD, encoding="utf-8")
        self.set_ratchet(5)
        for args in (["init", "-q"], ["config", "user.email", "t@t.t"],
                     ["config", "user.name", "t"]):
            subprocess.run(["git", *args], cwd=base, capture_output=True)

    def write_checks(self, audit_block=PASS_CMD, audit_count="echo 3",
                     secret_scan=EFFECTIVE_SCAN, security=True) -> None:
        text = CHECKS % {"audit_block": audit_block, "audit_count": audit_count,
                         "secret_scan": secret_scan}
        if not security:
            text = text.split("security")[0]
        (self.flow / "checks.md").write_text(text, encoding="utf-8")

    def write_state(self, dep="no new dependencies") -> None:
        (self.flow / "features" / "demo" / "state.md").write_text(
            STATE_OK % {"dep": dep}, encoding="utf-8")

    def set_ratchet(self, baseline) -> None:
        (self.flow / "ratchet.json").write_text(
            json.dumps({"metrics": {"vuln-total": {"baseline": baseline,
                                                   "rule": "no-increase"}}}),
            encoding="utf-8")

    def add_checks_line(self, after: str, line: str) -> None:
        p = self.flow / "checks.md"
        text = p.read_text(encoding="utf-8")
        p.write_text(text.replace(after, after + "\n" + line, 1), encoding="utf-8")

    def set_ratchet_metrics(self, metrics: dict) -> None:
        (self.flow / "ratchet.json").write_text(
            json.dumps({"metrics": metrics}, ensure_ascii=False), encoding="utf-8")

    def patch_repo_map(self, old: str, new: str) -> None:
        p = self.flow / "repo-map.md"
        p.write_text(p.read_text(encoding="utf-8").replace(old, new, 1), encoding="utf-8")

    def patch_state(self, old: str, new: str) -> None:
        p = self.flow / "features" / "demo" / "state.md"
        p.write_text(p.read_text(encoding="utf-8").replace(old, new, 1), encoding="utf-8")

    def set_slice_status(self, value: str) -> None:
        p = self.flow / "features" / "demo" / "state.md"
        text = p.read_text(encoding="utf-8")
        head, _, _ = text.partition("## Slice status")
        p.write_text(head + "## Slice status\n" + value + "\n", encoding="utf-8")

    def set_phase(self, phase: str, rework: int | None = None) -> None:
        p = self.flow / "features" / "demo" / "state.md"
        text = p.read_text(encoding="utf-8")
        text = re.sub(r"^phase: .*$", f"phase: {phase}", text, count=1, flags=re.M)
        text = re.sub(r"^rework: .*\n", "", text, flags=re.M)
        if rework is not None:
            text = text.replace(f"phase: {phase}", f"phase: {phase}\nrework: {rework}", 1)
        p.write_text(text, encoding="utf-8")

    def touch(self, rel: str) -> None:
        p = self.repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("x", encoding="utf-8")

    def append(self, rel: str, text: str) -> None:
        p = self.repo / rel
        p.write_text(p.read_text(encoding="utf-8") + text, encoding="utf-8")

    def rm(self, rel: str) -> None:
        p = self.repo / rel
        if p.is_file():
            p.unlink()

    def set_current(self, slug: str | None) -> None:
        p = self.flow / "current"
        if slug is None:
            if p.is_file():
                p.unlink()
        else:
            p.write_text(slug + "\n", encoding="utf-8")

    def commit(self, message: str) -> None:
        subprocess.run(["git", "add", "-A"], cwd=self.repo, capture_output=True)
        subprocess.run(["git", "commit", "-q", "--no-gpg-sign", "-m", message],
                       cwd=self.repo, capture_output=True)

    def hook(self, command: str, tool: str = "Bash") -> int:
        """Run the PreToolUse hook exactly as the harness would: a JSON envelope on stdin."""
        envelope = json.dumps({"tool_name": tool, "tool_input": {"command": command},
                               "cwd": str(self.repo)})
        r = subprocess.run([sys.executable, str(HOOKS / "hx_push_guard.py")],
                           input=envelope, capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        return r.returncode

    def hook_raw(self, payload: str) -> int:
        r = subprocess.run([sys.executable, str(HOOKS / "hx_push_guard.py")],
                           input=payload, capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        return r.returncode

    def run_text(self, script: str, *args: str) -> str:
        """Stdout of a script run. For asserting on ONE check inside a report whose overall
        exit code is dominated by the deliberately-bad fixture feature."""
        cmd = [sys.executable, str(SCRIPTS / script), "--flow", str(self.flow)]
        if script != "hx_lint.py":
            cmd += ["--repo", str(self.repo)]
        r = subprocess.run(cmd + list(args), capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        return (r.stdout or "") + (r.stderr or "")

    def run(self, script: str, *args: str) -> int:
        cmd = [sys.executable, str(SCRIPTS / script), "--flow", str(self.flow)]
        if script != "hx_lint.py":  # hx-lint does not inspect git, takes no --repo
            cmd += ["--repo", str(self.repo)]
        r = subprocess.run(cmd + list(args), capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        if r.returncode == 2:  # a usage/environment error must not pass silently
            print(f"[{script}] exit 2:\n{(r.stderr or r.stdout).strip()[:400]}")
        return r.returncode


def main() -> int:
    results: list[tuple[bool, str, str]] = []

    def check(name: str, got: int, want: int) -> None:
        results.append((got == want, name, f"expected={want} got={got}"))

    base = Path(tempfile.mkdtemp(prefix="hxflow-test-"))
    try:
        f = Fixture(base)

        # --- hx-lint: artifact schema ---
        check("lint: valid artifacts pass", f.run("hx_lint.py", "--feature", "demo"), 0)
        check("lint: broken artifacts are caught", f.run("hx_lint.py", "--feature", "bad"), 1)

        # --- hx-lint: the checks.md contract ---
        f.write_checks(security=False)
        check("lint: missing audit-block in checks.md is caught",
              f.run("hx_lint.py", "--feature", "demo"), 1)
        (f.flow / "checks.md").write_text(
            "platform: linux-ci\nrunner: none\nverified: 2026-08-17\n\n"
            "scope backend/\n  lint: echo ok\n  unknown-capability: echo x\n\n"
            "security\n  audit-block: exit 0\n", encoding="utf-8")
        check("lint: an unknown capability name is caught",
              f.run("hx_lint.py", "--feature", "demo"), 1)
        (f.flow / "checks.md").write_text(
            "platform: linux-ci\nrunner: none\nverified: 2026-08-17\n\n"
            "scope imaginary-scope/\n  lint: echo ok\n\n"
            "security\n  audit-block: exit 0\n", encoding="utf-8")
        check("lint: a scope absent from repo-map is caught",
              f.run("hx_lint.py", "--feature", "demo"), 1)
        f.write_checks()
        check("lint: a valid checks.md passes", f.run("hx_lint.py", "--feature", "demo"), 0)

        # --- structure-check ---
        f.touch("backend/billing/router.py")
        check("structure: a conforming new file passes", f.run("hx_structure.py"), 0)
        f.touch("backend/util/helpers.py")
        check("structure: illegal placement is caught", f.run("hx_structure.py"), 1)
        f.rm("backend/util/helpers.py")
        f.touch("backend/billing/models.py")
        check("structure: a model change without a migration is caught",
              f.run("hx_structure.py"), 1)
        f.touch("backend/migrations/003_split.py")
        check("structure: adding the migration makes it pass", f.run("hx_structure.py"), 0)

        # --- hx-security ---
        check("security: no manifest change, slice passes",
              f.run("hx_security.py", "--mode", "slice", "--feature", "demo"), 0)
        f.touch("package.json")
        # The blind spot this closes, found by driving a second feature through the phases: every
        # state.md starts from a template that already says "no new dependencies", so the section
        # is never empty. Asserting only "non-empty" let a manifest change through under a claim
        # that nothing was added - the exact event the gate exists to catch. This scenario used to
        # pass a manifest change carrying that untouched default and expect success.
        check("security: a manifest change under the template's default decision BLOCKS ship",
              f.run("hx_security.py", "--mode", "ship", "--feature", "demo"), 1)
        f.write_state(dep="- left-pad - why: padding; license: MIT; maintained: active")
        check("security: manifest changed with a real decision, ship passes",
              f.run("hx_security.py", "--mode", "ship", "--feature", "demo"), 0)
        f.write_state()
        f.rm("package.json")   # back to "no manifest changed" for the scenarios below

        f.write_checks(audit_block=FAIL_CMD)
        check("security: a vulnerability blocks ship",
              f.run("hx_security.py", "--mode", "ship", "--feature", "demo"), 1)

        f.write_checks(audit_count="echo 9")
        check("security: a rising vulnerability count blocks ship",
              f.run("hx_security.py", "--mode", "ship", "--feature", "demo"), 1)

        f.write_checks()
        f.touch("package.json")
        f.write_state(dep="")
        check("security: a missing dependency decision blocks ship",
              f.run("hx_security.py", "--mode", "ship", "--feature", "demo"), 1)
        f.rm("package.json")

        f.write_state()
        f.write_checks(secret_scan=FAIL_CMD)
        check("security: a secret-scan finding blocks ship",
              f.run("hx_security.py", "--mode", "ship", "--feature", "demo"), 1)

        f.write_checks(security=False)
        check("security: missing config BLOCKS ship (missing != safe)",
              f.run("hx_security.py", "--mode", "ship", "--feature", "demo"), 1)
        check("security: missing config does not block a developer mid-slice",
              f.run("hx_security.py", "--mode", "slice"), 0)
        f.write_checks()

        # --- hx-ratchet ---
        f.set_ratchet_metrics({
            "dummy-debt": {"measure": "echo 7", "baseline": None, "rule": "no-increase"},
            "must-zero": {"measure": "echo 0", "baseline": 0, "rule": "must-be-zero"},
        })
        check("ratchet: baselines are measured and written", f.run("hx_ratchet.py", "--baseline"), 0)
        check("ratchet: equal to baseline passes", f.run("hx_ratchet.py", "--check"), 0)
        f.set_ratchet_metrics({
            "dummy-debt": {"measure": "echo 9", "baseline": 7, "rule": "no-increase"},
        })
        check("ratchet: an increase is caught", f.run("hx_ratchet.py", "--check"), 1)
        f.set_ratchet_metrics({
            "must-zero": {"measure": "echo 3", "baseline": 0, "rule": "must-be-zero"},
        })
        check("ratchet: a must-be-zero violation is caught", f.run("hx_ratchet.py", "--check"), 1)
        f.set_ratchet_metrics({
            "dummy-debt": {"measure": "echo 4", "baseline": 7, "rule": "no-increase"},
        })
        check("ratchet: a decrease tightens with --tighten",
              f.run("hx_ratchet.py", "--check", "--tighten"), 0)
        tightened = json.loads((f.flow / "ratchet.json").read_text(encoding="utf-8"))
        results.append((tightened["metrics"]["dummy-debt"]["baseline"] == 4,
                        "ratchet: the tightened baseline is persisted",
                        f"baseline={tightened['metrics']['dummy-debt']['baseline']} expected=4"))
        f.set_ratchet_metrics({
            "unconfigured": {"measure": None, "baseline": None, "rule": "no-increase"},
        })
        check("ratchet: an unmeasured metric does not break --check",
              f.run("hx_ratchet.py", "--check"), 0)

        # --- POSIX shell selection ---
        # Regression for a real defect: subprocess shell=True runs cmd.exe on Windows, where
        # /dev/null does not exist, so a good POSIX command produced a FAIL that was not real.
        f.set_ratchet_metrics({
            "posix-syntax": {"measure": "echo 5 > /dev/null 2>&1 && echo 3 || echo 9",
                             "baseline": 3, "rule": "no-increase"},
        })
        check("ratchet: POSIX syntax in a measure command works",
              f.run("hx_ratchet.py", "--check"), 0)

        # --- ratchet.json validation ---
        (f.flow / "ratchet.json").write_text('{"metrics": {"x": {"measure": "echo 1"',
                                             encoding="utf-8")
        check("lint: malformed ratchet.json is caught", f.run("hx_lint.py", "--all"), 1)
        f.set_ratchet_metrics({
            "bad": {"measure": "echo 1", "baseline": 1, "rule": "no-such-rule"},
        })
        check("lint: an unknown ratchet rule is caught", f.run("hx_lint.py", "--all"), 1)
        f.set_ratchet_metrics({
            "nobase": {"measure": "echo 1", "baseline": None, "rule": "no-increase"},
        })
        check("lint: no-increase without a baseline is caught", f.run("hx_lint.py", "--all"), 1)
        f.set_ratchet(5)

        # --- hx-doctor ---
        check("doctor: a satisfiable environment passes", f.run("hx_doctor.py"), 0)
        f.write_checks(security=False)
        check("doctor: a missing security gate FAILS", f.run("hx_doctor.py"), 1)
        f.write_checks()
        f.add_checks_line("scope backend/", "  doctor:      test -d definitely-not-here")
        check("doctor: an unmet readiness probe FAILS", f.run("hx_doctor.py"), 1)
        f.write_checks()

        # --- secret gate effectiveness ---
        # The dangerous failure is not "a secret was missed", it is "the scanner never looked".
        f.write_checks(secret_scan=EFFECTIVE_SCAN)
        check("security: an effective secret scanner passes the ship canary",
              f.run("hx_security.py", "--mode", "ship", "--feature", "demo"), 0)
        f.write_checks(secret_scan=INEFFECTIVE_SCAN)
        check("security: a scanner that never looks FAILS the ship canary",
              f.run("hx_security.py", "--mode", "ship", "--feature", "demo"), 1)
        check("doctor: a scanner that never looks is reported as ineffective",
              f.run("hx_doctor.py"), 1)
        f.write_checks(secret_scan=EFFECTIVE_SCAN)
        check("doctor: an effective scanner passes", f.run("hx_doctor.py"), 0)
        results.append((not (base / "HX_CANARY_DELETE_ME.txt").exists(),
                        "canary: the planted file is always removed",
                        "absent" if not (base / "HX_CANARY_DELETE_ME.txt").exists() else "LEFT BEHIND"))
        f.write_checks()

        # --- hx-analyze ---
        check("analyze: a coherent feature passes",
              f.run("hx_analyze.py", "--feature", "demo"), 0)
        # The collision case: a sibling feature plans the same file. Nothing else detects this.
        sib = f.flow / "features" / "sibling"
        sib.mkdir(exist_ok=True)
        (sib / "state.md").write_text(STATE_OK % {"dep": "no new dependencies"}, encoding="utf-8")
        (sib / "plan.md").write_text(PLAN_OK, encoding="utf-8")
        check("analyze: a file collision with a sibling is caught",
              f.run("hx_analyze.py", "--feature", "demo"), 1)
        shutil.rmtree(sib)
        # IN and OUT claiming the same subject.
        f.patch_state("OUT: multi-currency, refund flow", "OUT: proportional VAT, refund flow")
        check("analyze: IN/OUT scope clash is caught",
              f.run("hx_analyze.py", "--feature", "demo"), 1)
        f.write_state()

        # --- hx-gate ---
        f.set_phase("discuss")
        check("gate: discuss->analyze is legal",
              f.run("hx_gate.py", "--feature", "demo", "--to", "analyze"), 0)
        check("gate: discuss->research skips analyze and is FORBIDDEN",
              f.run("hx_gate.py", "--feature", "demo", "--to", "research"), 1)
        f.set_phase("analyze")
        check("gate: analyze->research is legal",
              f.run("hx_gate.py", "--feature", "demo", "--to", "research"), 0)
        f.set_phase("plan")
        check("gate: legal transition plan->execute",
              f.run("hx_gate.py", "--feature", "demo", "--to", "execute"), 0)
        check("gate: FORBIDDEN transition plan->ship",
              f.run("hx_gate.py", "--feature", "demo", "--to", "ship"), 1)
        f.set_phase("discuss")
        check("gate: discuss->plan cannot be skipped to",
              f.run("hx_gate.py", "--feature", "demo", "--to", "plan"), 1)
        f.set_phase("verify")
        check("gate: ship blocked with no verification record",
              f.run("hx_gate.py", "--feature", "demo", "--to", "ship"), 1)
        f.run("hx_gate.py", "--feature", "demo", "--record-verify", "--result", "fail")
        check("gate: a failed verification blocks ship",
              f.run("hx_gate.py", "--feature", "demo", "--to", "ship"), 1)
        f.run("hx_gate.py", "--feature", "demo", "--record-verify", "--result", "pass")
        check("gate: a fresh passing verification allows ship",
              f.run("hx_gate.py", "--feature", "demo", "--to", "ship"), 0)
        f.touch("backend/billing/late_change.py")
        check("gate: a NEW file after verification -> STALE, ship blocked",
              f.run("hx_gate.py", "--feature", "demo", "--to", "ship"), 1)
        # The case the file-list fingerprint could not see, found by driving the phases end to
        # end: during execute the files are modified but not committed, so editing one AGAIN
        # after verify leaves `git status --porcelain` byte-identical. Ship accepted unverified
        # code, which is the one thing this gate exists to prevent.
        f.rm("backend/billing/late_change.py")
        f.touch("backend/billing/already_modified.py")
        f.run("hx_gate.py", "--feature", "demo", "--record-verify", "--result", "pass")
        check("gate: an untouched worktree is not stale",
              f.run("hx_gate.py", "--feature", "demo", "--to", "ship"), 0)
        f.append("backend/billing/already_modified.py", "\n# one more line\n")
        check("gate: editing an ALREADY-modified file after verification -> STALE",
              f.run("hx_gate.py", "--feature", "demo", "--to", "ship"), 1)
        f.rm("backend/billing/already_modified.py")
        f.run("hx_gate.py", "--feature", "demo", "--record-verify", "--result", "pass")
        f.set_phase("verify", rework=2)
        check("gate: exceeding the rework limit blocks",
              f.run("hx_gate.py", "--feature", "demo", "--to", "execute"), 1)

        # --- repo-map self-consistency ---
        # A requires: target that is not itself an allowed pattern makes the contract impossible
        # to satisfy: the file written to meet the requirement is an illegal placement. Found by
        # driving the phases end to end, where structure-check only WARNed about it in the middle
        # of execute - long after map had accepted the repo-map.
        f.patch_repo_map("requires:backend/migrations/**", "requires:backend/nowhere/**")
        check("lint: a requires: target that is not an allowed pattern FAILS",
              f.run("hx_lint.py", "--all"), 1)
        f.patch_repo_map("requires:backend/nowhere/**", "requires:backend/migrations/**")
        # --all also lints the deliberately-bad fixture feature, so its exit code can never be 0.
        # Assert on the one check this scenario is about.
        out = f.run_text("hx_lint.py", "--all")
        results.append(("PASS    repo-map: requires targets" in out,
                        "lint: a self-consistent repo-map reports its contract intact",
                        "PASS line present" if "PASS    repo-map: requires targets" in out
                        else "the contract check did not pass or did not run"))

        # --- the discuss -> lint handshake ---
        # Found by driving the phases end to end: the template shipped "<no plan yet>" under
        # Slice status, hx-lint read the angle brackets as an unfilled placeholder, and a feature
        # that had only been discussed could therefore never pass the lint that discuss requires.
        # Every fixture above fills Slice status with real slices, so nothing caught it.
        f.set_phase("discuss")
        f.set_slice_status(template_slice_status())
        check("lint: a discussed feature carrying the template's own Slice status passes",
              f.run("hx_lint.py", "--feature", "demo"), 0)
        f.set_slice_status("<no plan yet>")
        check("lint: a real placeholder under Slice status is still caught",
              f.run("hx_lint.py", "--feature", "demo"), 1)
        f.write_state()

        # --- hx-push-guard (PreToolUse hook) ---
        # Exit 2 = the tool call is blocked. Every other exit code lets the push through, so the
        # scenarios that expect 0 matter as much as the ones that expect 2: a guard that blocks
        # a legitimate push gets switched off, and a switched-off guard protects nothing.
        f.set_current(None)
        f.set_phase("execute")
        check("push-guard: no active feature -> push allowed",
              f.hook("git push -u origin feature/x"), 0)
        f.set_current("demo")
        check("push-guard: phase execute -> push BLOCKED",
              f.hook("git push -u origin feature/x"), 2)
        check("push-guard: --force-with-lease is still a push -> BLOCKED",
              f.hook("git push --force-with-lease"), 2)
        f.set_phase("verify")
        check("push-guard: phase verify -> push BLOCKED", f.hook("git push"), 2)
        check("push-guard: branch deletion carries no code -> allowed",
              f.hook("git push origin --delete feature/x"), 0)
        check("push-guard: git pull is not a push -> allowed",
              f.hook("git pull --rebase"), 0)
        check("push-guard: a non-Bash tool call is ignored",
              f.hook("git push", tool="Write"), 0)
        check("push-guard: a malformed envelope must not block",
              f.hook_raw("not json at all"), 0)
        f.set_phase("plan")
        check("push-guard: an unguarded phase -> push allowed", f.hook("git push"), 0)
        f.set_phase("execute")
        check("push-guard: still blocked before the waiver", f.hook("git push"), 2)
        f.commit("wip\n\nHX-Verify-Override: hotfix branch, verified out of band")
        check("push-guard: an auditable override trailer releases the push",
              f.hook("git push"), 0)
        f.set_current(None)

        # --- porcelain column parsing ---
        # Every scenario above runs on a repository with no commit, so `git status --porcelain`
        # emits only `?? path` lines. An UNSTAGED change emits ` M path`, with a leading space,
        # and stripping the whole output ate that space on the FIRST line only - `package.json`
        # was read as `ackage.json`, matched no manifest, and the dependency gate was skipped
        # without a word. Found by driving a second feature through the phases in a repository
        # that had actually been committed.
        f.touch("package.json")
        f.commit("baseline so that later edits are tracked modifications")
        f.append("package.json", "{}\n")
        check("security: an unstaged manifest edit is seen even as the first status line",
              f.run("hx_security.py", "--mode", "ship", "--feature", "demo"), 1)
        f.write_state(dep="- left-pad - why: padding; license: MIT; maintained: active")
        check("security: the same edit passes once the decision names the dependency",
              f.run("hx_security.py", "--mode", "ship", "--feature", "demo"), 0)
    finally:
        shutil.rmtree(base, ignore_errors=True)

    print()
    print("hx-flow regression tests")
    print(f"{'status':<6}  {'scenario':<56}  detail")
    print("-" * 100)
    for ok, name, detail in results:
        print(f"{'OK' if ok else 'FAIL':<6}  {name:<56}  {detail}")
    print("-" * 100)
    bad = [r for r in results if not r[0]]
    print(f"{'ALL SCENARIOS AS EXPECTED' if not bad else f'{len(bad)} SCENARIO(S) DEVIATED'}"
          f"   ({len(results)} scenarios)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
