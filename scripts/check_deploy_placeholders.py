#!/usr/bin/env python3
"""
scripts/check_deploy_placeholders.py — deploy-YAML placeholder + env-var-set
canonical-manifest coupling guard

**Class-of-failure the gate defends against: SILENT ENV-VAR REPLACEMENT.**

Two instances of the class today:

1. `gcloud run services replace` (mc16-2026-05-25 anchor):
    A placeholder env value in `deploy/*.yaml` (e.g. "https://fbt-engine-XXXX-
    an.a.run.app") will SILENTLY CLOBBER any working out-of-band `--set-env-
    vars` override that has been keeping production alive, taking the route
    to HTTP 500 with no deploy-time warning.

2. `gcloud run deploy --set-env-vars=...` (mc39.1-2026-08-29 anchor;
    matched-drift blind-spot fix at mc40-2026-08-29 Andrew follow-up 1):
    `--set-env-vars` REPLACES the entire env-var set on the new revision.
    A partial declaration silently drops missing names with no wire-
    observable failure until a caller trips over the absent locale /
    URL / helper var.

    mc39.1 tried to catch this by cross-checking the workflow's
    `--set-env-vars=` string against a co-located `expected=(...)` bash
    array. Andrew caught the blind spot: *both* lists live in the same
    document, both authored by the same hand at the same time; if both are
    wrong the same way, both gates go green.

    mc40 fix: promote a single canonical env-var manifest
    (`deploy/env_vars.json`) as the sole source of truth. The deploy
    workflow's three env-var-related steps (pre-deploy live-set delta
    check, Deploy `--set-env-vars`, post-deploy presence assertion) all
    derive from this ONE file. This script's role reduces to two mechanical
    checks:

    (a) The workflow YAML MUST NOT contain any hard-coded `--set-env-vars`
        declarations (would re-introduce the two-document drift class).

    (b) `deploy/env_vars.json` MUST parse and MUST contain a non-empty
        `env` object.

    The load-bearing runtime check now lives in deploy.yml itself as the
    pre-deploy live-env-var-set delta step, which reads the LIVE service
    (a state independent of any repo document, so matched-drift cannot
    exist).

On the placeholder path (deploy/*.yaml + deploy/*.json scan): finds
placeholder literals in declared env values and exits non-zero.

Wired into `pre-push` and CI before any deploy step.

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
    python3 scripts/check_deploy_placeholders.py           # default: deploy/ + .github/workflows/
    python3 scripts/check_deploy_placeholders.py path/...  # override targets

Environment:
    CLAWDOG_PLACEHOLDER_GUARD_VERBOSE=1    emit 🟢 CLEAN detail on pass
    CLAWDOG_ENVVAR_SET_GUARD_DISABLE=1     disable the env-var-set check only
                                           (placeholder check still fires).
                                           When bypass fires, script emits
                                           a loud ::warning:: annotation to
                                           stderr for the CI log audit trail
                                           (mc40 Andrew follow-up 2).

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
    """Resolve CLI args (or default `deploy/` + `.github/workflows/`) to a
    flat list of YAML files."""
    if argv:
        raw_targets = [Path(p) for p in argv]
    else:
        # Default: deploy/ (placeholder scan) + .github/workflows/ (env-var-set
        # completeness scan). Both live behind the same class-of-failure gate.
        raw_targets = [Path("deploy"), Path(".github/workflows")]

    yamls: list[Path] = []
    for target in raw_targets:
        if not target.exists():
            # Missing target is not fatal at the default-scan level (repo may
            # legitimately have no deploy/ yet at Phase 0). Only raise if the
            # user explicitly listed it.
            if argv:
                raise SystemExit(
                    f"🟡 INFRA BROKEN: target does not exist: {target}"
                )
            continue
        if target.is_file():
            yamls.append(target)
            continue
        if target.is_dir():
            # YAML for workflow + deploy manifest placeholder scan.
            for ext in ("*.yaml", "*.yml"):
                yamls.extend(sorted(target.rglob(ext)))
            # JSON for mc40 canonical env-var manifest check
            # (deploy/env_vars.json). Only scan JSON under deploy/, not
            # under .github/workflows/.
            if target.name == "deploy" or target.parts[-1:] == ("deploy",):
                yamls.extend(sorted(target.rglob("*.json")))
            continue
        raise SystemExit(
            f"🟡 INFRA BROKEN: target is neither file nor directory: {target}"
        )
    return sorted(set(yamls))


# ---------------------------------------------------------------------------
# env-var-set completeness scan (mc39.1-2026-08-29 addition)
# ---------------------------------------------------------------------------
# The scan looks for `--set-env-vars=` occurrences in workflow YAML and
# cross-checks the declared name set against a canonical required-set. The
# required-set is DERIVED from the same workflow file's `expected=(...)`
# bash array in the post-deploy env-var-set presence assertion step. Both
# lists live in the same file precisely so dropping a name from either
# fires the gate.

# Match `--set-env-vars="..."` with an optional `^delimiter^` prefix per
# gcloud CSV-list escape syntax. Group 1 captures the payload between the
# double-quotes.
_SET_ENV_VARS_RE = re.compile(r'--set-env-vars="([^"]+)"')

# Match `expected=(` block (bash array literal) and capture through the
# closing `)`. Non-greedy across newlines.
_EXPECTED_ARRAY_RE = re.compile(
    r"expected=\(\s*([\s\S]*?)\s*\)", re.MULTILINE
)

# Match bash array elements (whitespace-separated identifiers on their own
# lines within the array literal). Excludes commented-out lines.
_EXPECTED_ELEMENT_RE = re.compile(r"^\s*([A-Z_][A-Z0-9_]*)\s*$", re.MULTILINE)


def _parse_set_env_vars_names(payload: str) -> list[str]:
    """Extract env-var NAMEs from a `--set-env-vars=` payload string.

    Supports both `^delimiter^` and default `,` delimiter forms per gcloud
    CSV-list escape syntax. Payload shape:

        default:      "NAME1=VALUE1,NAME2=VALUE2"
        alt-delim:    "^|^NAME1=VALUE1|NAME2=VALUE2"  (delim `|` here)
    """
    payload = payload.strip()
    if payload.startswith("^") and payload[2:3] == "^":
        delim = payload[1]
        payload = payload[3:]
    else:
        delim = ","
    names: list[str] = []
    for pair in payload.split(delim):
        pair = pair.strip()
        if not pair or "=" not in pair:
            continue
        name = pair.split("=", 1)[0].strip()
        if name:
            names.append(name)
    return names


def _extract_expected_names(text: str) -> list[str] | None:
    """Extract the canonical env-var-set names from the workflow's
    `expected=(...)` bash array.

    Returns None if no expected-array is present (workflow doesn't declare
    the assertion; env-var-set scan skips the file).
    Returns [] if array is present but empty (a real defect).
    """
    m = _EXPECTED_ARRAY_RE.search(text)
    if m is None:
        return None
    array_body = m.group(1)
    return _EXPECTED_ELEMENT_RE.findall(array_body)


# Match `--set-env-vars="NAME=value,..."` where the value is a hard-coded
# literal (not `"$var"` templating). The pattern deliberately excludes bash
# variable substitution forms so mc40's `--set-env-vars="$set_env_vars"`
# construction (reading from deploy/env_vars.json) does NOT trip the gate.
_HARDCODED_SET_ENV_VARS_RE = re.compile(
    r'--set-env-vars="(?!\$)(?![^"]*\$\{)([^"]*=[^"]*)"'
)


def _scan_envvar_set_completeness(
    path: Path,
) -> list[tuple[int, str, str]]:
    """Return env-var-set canonical-manifest coupling findings for a
    single file.

    Each finding is (line_number, label, raw_line_or_diagnostic).
    Empty list = file is clean.

    Post-mc40 (Andrew follow-up 1 blind-spot fix): the ONLY workflow YAML
    check is *no hard-coded `--set-env-vars` declarations*. All env-var
    declaration must derive from deploy/env_vars.json to avoid the
    matched-drift blind spot where two co-authored documents can be wrong
    the same way and both pass a cross-check.

    The env-var-set completeness check itself runs at deploy time (pre-
    deploy live-set delta + post-deploy presence assertion in deploy.yml),
    reading the LIVE service state — a state independent of any document
    in this repo.
    """
    if os.environ.get("CLAWDOG_ENVVAR_SET_GUARD_DISABLE"):
        # Andrew follow-up 2: a binary-failure gate with a silent bypass is
        # not binary. Warning is emitted ONCE at module-load time (see
        # `_maybe_emit_bypass_warning`); this branch returns silently to
        # avoid warning-per-file spam.
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        # Placeholder scan will already have raised on the same file.
        return []
    if "--set-env-vars" not in text:
        return []  # File doesn't participate in env-var-set replacement.

    findings: list[tuple[int, str, str]] = []
    lines = text.splitlines()
    for idx, line in enumerate(lines):
        # Comments are informational, not policy. Skip.
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        # Templated form `--set-env-vars="$var"` is the correct mc40 shape
        # (bash variable expansion of a value derived from deploy/env_vars.json).
        # Hard-coded literal form is what we ban.
        if _HARDCODED_SET_ENV_VARS_RE.search(line):
            findings.append((
                idx + 1,
                (
                    "hard-coded --set-env-vars declaration in workflow YAML "
                    "(mc40 discipline: derive from deploy/env_vars.json "
                    "canonical manifest instead)"
                ),
                line.strip(),
            ))
    return findings


_BYPASS_WARNED = False


def _maybe_emit_bypass_warning() -> None:
    """Emit the loud bypass warning to stderr exactly once per script run.

    Called from main() before the per-file loop; ensures one audit-trail
    entry per CLAWDOG_ENVVAR_SET_GUARD_DISABLE bypass, not one per file.
    """
    global _BYPASS_WARNED
    if _BYPASS_WARNED:
        return
    if not os.environ.get("CLAWDOG_ENVVAR_SET_GUARD_DISABLE"):
        return
    print(
        "::warning title=🚨 env-var-set guard BYPASSED::"
        "CLAWDOG_ENVVAR_SET_GUARD_DISABLE=1 is set; "
        "check_deploy_placeholders.py env-var-set canonical-manifest "
        "coupling check SKIPPED across all files this run. A silent bypass "
        "on a binary-failure gate is not binary — the script emits this "
        "::warning:: for the CI log audit trail per mc40-2026-08-29 "
        "Andrew follow-up 2. Placeholder scan still fires.",
        file=sys.stderr,
    )
    _BYPASS_WARNED = True


def _scan_env_vars_json(path: Path) -> list[tuple[int, str, str]]:
    """Return findings for the deploy/env_vars.json canonical manifest.

    Post-mc40: the file must parse as JSON and have a non-empty `env` object.
    A missing or malformed manifest is drift; the deploy workflow's pre-
    deploy check would fail at runtime, so surfacing this at pre-push /
    CI is defence-in-depth.
    """
    import json  # local import; keep the module import list dependency-free

    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return [(0, f"cannot read canonical manifest: {exc}", str(path))]
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        return [(exc.lineno, f"malformed JSON in canonical manifest: {exc.msg}", "")]
    if not isinstance(data, dict):
        return [(1, "canonical manifest root is not a JSON object", "")]
    env = data.get("env")
    if env is None:
        return [(1, "canonical manifest missing top-level `env` object", "")]
    if not isinstance(env, dict):
        return [(1, "canonical manifest `env` is not a JSON object", "")]
    if not env:
        return [(1, "canonical manifest `env` is empty (would deploy with no env-vars)", "")]
    return []


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
        print("🟢 CLEAN — no target files matched", file=sys.stderr)
        return _EXIT_CLEAN

    _maybe_emit_bypass_warning()

    all_findings: list[tuple[Path, int, str, str]] = []
    for path in targets:
        # YAML-shaped placeholder + workflow-YAML env-var-set scans apply
        # only to YAML files.
        if path.suffix in (".yaml", ".yml"):
            for lineno, label, raw in _scan_file(path):
                all_findings.append((path, lineno, label, raw))
            for lineno, label, raw in _scan_envvar_set_completeness(path):
                all_findings.append((path, lineno, label, raw))
        # mc40 canonical manifest check applies only to env_vars.json.
        if path.name == "env_vars.json":
            for lineno, label, raw in _scan_env_vars_json(path):
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
        "Fix (placeholder path): replace the placeholder with the production\n"
        "value, OR add an explicit allow marker on (or above) the line:\n"
        "    <!-- deploy-placeholder-allow: <non-empty reason> -->\n"
        "Why this gate exists: see mc16-2026-05-25 — placeholder env values\n"
        "in `deploy/*.yaml` are silently honoured by `gcloud run services\n"
        "replace`, clobbering any working out-of-band --set-env-vars override.\n"
        "\n"
        "Fix (env-var-set path, mc40 canonical-manifest discipline): remove\n"
        "any hard-coded `--set-env-vars=\"NAME=value,...\"` string from workflow\n"
        "YAML and replace it with a bash-variable form that derives from\n"
        "`deploy/env_vars.json`, e.g.:\n"
        "    set_env_vars=$(python3 -c \"import json; d = json.load(open('deploy/env_vars.json'))['env']; print('^|^' + '|'.join(f'{k}={v}' for k, v in d.items()))\")\n"
        "    gcloud run deploy ... --set-env-vars=\"$set_env_vars\"\n"
        "To temporarily disable the env-var-set check only, set\n"
        "CLAWDOG_ENVVAR_SET_GUARD_DISABLE=1; the placeholder check still\n"
        "fires. A ::warning:: annotation is emitted to stderr when bypass\n"
        "triggers (mc40 Andrew follow-up 2: silent bypass is not binary).\n"
        "Why this gate exists: see mc39.1-2026-08-29 (partial --set-env-vars\n"
        "declarations silently drop unlisted names) + mc40-2026-08-29 blind-\n"
        "spot fix (matched-drift between two co-authored documents passes\n"
        "cross-checks; one canonical source doesn't).",
        file=sys.stderr,
    )
    return _EXIT_DRIFT


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
