#!/usr/bin/env python3
"""
scripts/check_deploy_placeholders.py — deploy-YAML placeholder guard

Mechanical enforcement of the mc16-2026-05-25 watch-pattern:

    `gcloud run services replace` is declarative. A placeholder env value in
    `deploy/*.yaml` (e.g. "https://fbt-engine-XXXX-an.a.run.app") will
    SILENTLY CLOBBER any working out-of-band `--set-env-vars` override that
    has been keeping production alive, taking the route to HTTP 500 with no
    deploy-time warning.

This script scans `deploy/*.yaml` (configurable) for known placeholder
patterns and exits non-zero if any are present. Wired into `pre-push` and
intended to also fire in CI before any `services replace` step.

Mode-B exit-code contract (mirroring Standing Rule #8):

    0  🟢 CLEAN          — no placeholder patterns found.
    1  🔴 LOGIC DRIFT    — placeholder pattern detected; fix the value or
                          remove the env entry before push.
    2  🟡 INFRA BROKEN   — deploy dir/file unreadable, regex compile failed,
                          or argv malformed. Halt and alert a human.

Allowlist: a `<!-- deploy-placeholder-allow: <non-empty reason> -->` comment
on the same line OR the immediately preceding line exempts that specific
line. The reason must be non-empty (empty / whitespace-only fails the gate).
This mirrors the secret-scanner allowlist shape on the Brain side.

Usage:
    python3 scripts/check_deploy_placeholders.py           # default: deploy/
    python3 scripts/check_deploy_placeholders.py path/...  # override targets

The script is dependency-free (stdlib re + pathlib + sys + os) and POSIX-
shell-friendly for git hook invocation.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Placeholder patterns. Each entry is (compiled_regex, human_label).
#
# Keep this list TIGHT — false positives turn the gate into noise and Lesson
# #35 says noise begets drift. Each pattern must have a clear failure mode
# we can point at on the production-bundle smoke surface.
# ---------------------------------------------------------------------------
_PLACEHOLDER_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"-XXXX-"), "literal -XXXX- placeholder in URL"),
    (re.compile(r"<HASH>"), "<HASH> angle-bracket placeholder"),
    (re.compile(r"\bFILL_ME\b", re.IGNORECASE), "FILL_ME marker"),
    (re.compile(r"\bTODO_DEPLOY\b", re.IGNORECASE), "TODO_DEPLOY marker"),
    (re.compile(r"\bPLACEHOLDER_URL\b", re.IGNORECASE), "PLACEHOLDER_URL marker"),
    (re.compile(r"<your-[a-z0-9-]+>", re.IGNORECASE), "<your-...> placeholder"),
]

_ALLOW_RE = re.compile(
    r"<!--\s*deploy-placeholder-allow:\s*(?P<reason>[^>]*?)\s*-->"
)

_EXIT_CLEAN = 0
_EXIT_DRIFT = 1
_EXIT_INFRA = 2


def _is_allowed(line: str, prev_line: str) -> tuple[bool, str | None]:
    """Return (allowed, error_message_if_invalid).

    - If neither the line nor the preceding line carries a deploy-placeholder-
      allow marker, returns (False, None).
    - If a marker is present with an EMPTY reason, returns (False, error_msg)
      so we can fail the gate with a helpful message rather than silently
      pass.
    - If a marker is present with a non-empty reason, returns (True, None).
    """
    for candidate in (line, prev_line):
        if candidate is None:
            continue
        m = _ALLOW_RE.search(candidate)
        if m is None:
            continue
        reason = (m.group("reason") or "").strip()
        if not reason:
            return (
                False,
                "deploy-placeholder-allow marker with empty reason; "
                "supply a non-empty justification or remove the marker",
            )
        return True, None
    return False, None


def _scan_file(path: Path) -> list[tuple[int, str, str]]:
    """Return a list of (line_number, placeholder_label, raw_line) findings."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise SystemExit(
            f"🟡 INFRA BROKEN: cannot read {path}: {exc}"
        ) from exc

    findings: list[tuple[int, str, str]] = []
    lines = text.splitlines()
    for idx, line in enumerate(lines):
        prev_line = lines[idx - 1] if idx > 0 else ""
        for regex, label in _PLACEHOLDER_PATTERNS:
            if regex.search(line):
                allowed, allow_err = _is_allowed(line, prev_line)
                if allow_err is not None:
                    # Empty-reason marker → drift; surface and fail.
                    findings.append((idx + 1, allow_err, line))
                    continue
                if allowed:
                    continue
                findings.append((idx + 1, label, line.rstrip()))
    return findings


def _resolve_targets(argv: list[str]) -> list[Path]:
    """Resolve CLI args (or default `deploy/`) to a flat list of YAML files."""
    if argv:
        raw_targets = [Path(p) for p in argv]
    else:
        raw_targets = [Path("deploy")]

    yamls: list[Path] = []
    for target in raw_targets:
        if not target.exists():
            raise SystemExit(
                f"🟡 INFRA BROKEN: target does not exist: {target}"
            )
        if target.is_file():
            yamls.append(target)
            continue
        if target.is_dir():
            for ext in ("*.yaml", "*.yml"):
                yamls.extend(sorted(target.rglob(ext)))
            continue
        raise SystemExit(
            f"🟡 INFRA BROKEN: target is neither file nor directory: {target}"
        )
    return sorted(set(yamls))


def main(argv: list[str]) -> int:
    # Regex pre-compile is at module load; if Python imported, regexes are
    # already validated. Catch corrupt environments defensively.
    try:
        _ = [(p.pattern, lbl) for p, lbl in _PLACEHOLDER_PATTERNS]
    except Exception as exc:  # pragma: no cover — defensive guard
        print(f"🟡 INFRA BROKEN: placeholder regex pre-compile failed: {exc}",
              file=sys.stderr)
        return _EXIT_INFRA

    try:
        targets = _resolve_targets(argv)
    except SystemExit as exc:
        # _resolve_targets raises SystemExit with the 🟡 message already.
        print(exc, file=sys.stderr)
        return _EXIT_INFRA

    if not targets:
        # Nothing to scan = clean. Don't fail; the project may legitimately
        # have no deploy/ directory yet.
        print("🟢 CLEAN — no YAML files matched", file=sys.stderr)
        return _EXIT_CLEAN

    all_findings: list[tuple[Path, int, str, str]] = []
    for path in targets:
        for lineno, label, raw in _scan_file(path):
            all_findings.append((path, lineno, label, raw))

    if not all_findings:
        if os.environ.get("CLAWDOG_PLACEHOLDER_GUARD_VERBOSE"):
            print(f"🟢 CLEAN — scanned {len(targets)} file(s):", file=sys.stderr)
            for t in targets:
                print(f"  - {t}", file=sys.stderr)
        return _EXIT_CLEAN

    print("🔴 LOGIC DRIFT — deploy placeholder(s) detected:", file=sys.stderr)
    print("", file=sys.stderr)
    for path, lineno, label, raw in all_findings:
        print(f"  {path}:{lineno}  [{label}]", file=sys.stderr)
        print(f"      {raw.strip()}", file=sys.stderr)
    print("", file=sys.stderr)
    print(
        "Fix: replace the placeholder with the production value, OR add an\n"
        "explicit allow marker on (or above) the line:\n"
        "    <!-- deploy-placeholder-allow: <non-empty reason> -->\n"
        "Why this gate exists: see mc16-2026-05-25 — placeholder env values\n"
        "in `deploy/*.yaml` are silently honoured by `gcloud run services\n"
        "replace`, clobbering any working out-of-band --set-env-vars override.",
        file=sys.stderr,
    )
    return _EXIT_DRIFT


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
