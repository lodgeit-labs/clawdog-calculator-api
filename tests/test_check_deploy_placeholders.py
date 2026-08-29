"""Tests for scripts/check_deploy_placeholders.py.

Covers all three branches of the gate:
  * Placeholder scan (mc16-2026-05-25 anchor)
  * Env-var-set canonical-manifest coupling scan (mc40-2026-08-29 shape;
    replaces the mc39.1 expected=() cross-check per Andrew follow-up 1
    matched-drift blind-spot fix)
  * Canonical manifest structure check (deploy/env_vars.json parse + shape)

Includes an integration test that fires the script against the live
`deploy/` + `.github/workflows/` and asserts it exits 0 (any repo state
that would fail the gate is caught in CI before merge).
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = REPO_ROOT / "scripts" / "check_deploy_placeholders.py"

# Ensure the script's module directory is importable for the unit tests.
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import check_deploy_placeholders as guard  # noqa: E402

# ---------------------------------------------------------------------------
# Unit tests: hard-coded --set-env-vars detection (mc40 shape)
#
# mc40 Andrew follow-up 4: the mc39.1-era parse-contract tests
# (test_parse_default_delimiter_comma, test_parse_alt_delimiter_pipe,
# test_parse_skips_malformed_entries, test_parse_empty_payload_yields_empty_list)
# were deleted here alongside the helpers they exercised. The mc40
# canonical-manifest discipline reduces the workflow-YAML guard to a
# single check (no hard-coded --set-env-vars); the parsers had no live
# consumer after the mc40 rewrite.
# ---------------------------------------------------------------------------


def _fixture(tmp_path: Path, content: str, name: str = "deploy.yml") -> Path:
    """Write a fixture to tmp_path and return its Path."""
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return p


def test_scan_no_set_env_vars_returns_empty(tmp_path: Path):
    """Workflow without --set-env-vars → not our concern; no findings."""
    p = _fixture(tmp_path, "name: no set-env-vars here\non: push")
    assert guard._scan_envvar_set_completeness(p) == []


def test_scan_hardcoded_set_env_vars_string_flags_drift(tmp_path: Path):
    """A hard-coded --set-env-vars="NAME=value,..." string is banned per mc40
    canonical-manifest discipline: hard-coding re-introduces the two-document
    matched-drift blind spot Andrew identified in mc39.1."""
    p = _fixture(tmp_path, '''\
      - name: Deploy
        run: |
          gcloud run deploy foo --set-env-vars="A=1,B=2"
    ''')
    findings = guard._scan_envvar_set_completeness(p)
    assert len(findings) == 1
    assert "hard-coded --set-env-vars declaration in workflow YAML" in findings[0][1]


def test_scan_hardcoded_set_env_vars_alt_delim_flags_drift(tmp_path: Path):
    """`^|^`-delimited hard-coded form is also banned."""
    p = _fixture(tmp_path, '''\
      - name: Deploy
        run: |
          gcloud run deploy foo --set-env-vars="^|^A=1|B=2|C=3"
    ''')
    findings = guard._scan_envvar_set_completeness(p)
    assert len(findings) == 1


def test_scan_variable_expansion_form_passes(tmp_path: Path):
    """mc40 canonical shape: --set-env-vars="$var" where $var is built from
    deploy/env_vars.json. Passes the guard because there's no hard-coded
    literal to drift out of sync with the canonical manifest."""
    p = _fixture(tmp_path, '''\
      - name: Deploy
        run: |
          set_env_vars=$(python3 -c "import json; d=json.load(open('deploy/env_vars.json'))['env']; print('^|^' + '|'.join(f'{k}={v}' for k,v in d.items()))")
          gcloud run deploy foo --set-env-vars="$set_env_vars"
    ''')
    assert guard._scan_envvar_set_completeness(p) == []


def test_scan_brace_expansion_form_passes(tmp_path: Path):
    """`${var}` form also passes (bash brace expansion)."""
    p = _fixture(tmp_path, '''\
      - name: Deploy
        run: |
          gcloud run deploy foo --set-env-vars="${MY_VARS}"
    ''')
    assert guard._scan_envvar_set_completeness(p) == []


def test_scan_comment_lines_skipped(tmp_path: Path):
    """Hard-coded --set-env-vars in comment lines is informational, not
    policy; skip."""
    p = _fixture(tmp_path, '''\
      - name: Deploy
        run: |
          # example: --set-env-vars="A=1,B=2"
          gcloud run deploy foo
    ''')
    assert guard._scan_envvar_set_completeness(p) == []


def test_scan_disable_via_env_var(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """CLAWDOG_ENVVAR_SET_GUARD_DISABLE=1 turns off env-var-set scan only.
    Placeholder scan still fires."""
    monkeypatch.setenv("CLAWDOG_ENVVAR_SET_GUARD_DISABLE", "1")
    p = _fixture(tmp_path, '''\
      - name: Deploy
        run: |
          gcloud run deploy foo --set-env-vars="A=1"
    ''')
    # Hard-coded --set-env-vars → would normally flag; disabled by env-var.
    assert guard._scan_envvar_set_completeness(p) == []


# ---------------------------------------------------------------------------
# Unit tests: canonical manifest structure (deploy/env_vars.json)
# ---------------------------------------------------------------------------


def test_manifest_valid_shape(tmp_path: Path):
    """Well-formed manifest with non-empty `env` object → no findings."""
    p = _fixture(
        tmp_path,
        json.dumps({"env": {"A": "1", "B": "2"}}),
        name="env_vars.json",
    )
    assert guard._scan_env_vars_json(p) == []


def test_manifest_malformed_json_flags_drift(tmp_path: Path):
    p = _fixture(tmp_path, "{not valid json", name="env_vars.json")
    findings = guard._scan_env_vars_json(p)
    assert len(findings) == 1
    assert "malformed JSON" in findings[0][1]


def test_manifest_missing_env_key_flags_drift(tmp_path: Path):
    p = _fixture(tmp_path, json.dumps({"other": {}}), name="env_vars.json")
    findings = guard._scan_env_vars_json(p)
    assert len(findings) == 1
    assert "missing top-level `env` object" in findings[0][1]


def test_manifest_empty_env_flags_drift(tmp_path: Path):
    p = _fixture(tmp_path, json.dumps({"env": {}}), name="env_vars.json")
    findings = guard._scan_env_vars_json(p)
    assert len(findings) == 1
    assert "empty" in findings[0][1]


def test_manifest_env_not_object_flags_drift(tmp_path: Path):
    p = _fixture(tmp_path, json.dumps({"env": ["A", "B"]}), name="env_vars.json")
    findings = guard._scan_env_vars_json(p)
    assert len(findings) == 1
    assert "not a JSON object" in findings[0][1]


# ---------------------------------------------------------------------------
# Integration test: dogfood against the live repo
# ---------------------------------------------------------------------------


def test_integration_live_repo_passes():
    """The default scan (deploy/ + .github/workflows/) against the live repo
    state exits 0. Post-mc40: covers YAML placeholder scan +
    workflow-YAML hard-coded --set-env-vars ban + deploy/env_vars.json
    canonical manifest structure."""
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH)],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, (
        f"check_deploy_placeholders.py exited {result.returncode}; "
        f"stderr:\n{result.stderr}"
    )


def test_integration_bypass_warning_emitted_once(
    monkeypatch: pytest.MonkeyPatch,
):
    """When CLAWDOG_ENVVAR_SET_GUARD_DISABLE=1, exactly ONE ::warning::
    annotation is emitted to stderr (not one per file). mc40 Andrew
    follow-up 2 — silent bypass on a binary-failure gate is not binary;
    but warning-per-file spam obscures the audit trail."""
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH)],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=15,
        env={**dict(__import__("os").environ), "CLAWDOG_ENVVAR_SET_GUARD_DISABLE": "1"},
    )
    assert result.returncode == 0
    warning_lines = [
        ln
        for ln in result.stderr.splitlines()
        if ln.startswith("::warning title=🚨 env-var-set guard BYPASSED::")
    ]
    assert len(warning_lines) == 1, (
        f"expected exactly 1 bypass warning, got {len(warning_lines)}. "
        f"stderr:\n{result.stderr}"
    )
