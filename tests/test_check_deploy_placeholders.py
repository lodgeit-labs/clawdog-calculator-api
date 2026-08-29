"""Tests for scripts/check_deploy_placeholders.py.

Covers both branches of the gate:
  * Placeholder scan (mc16-2026-05-25 anchor)
  * Env-var-set completeness scan (mc39.1-2026-08-29 anchor)

Includes an integration test that fires the script against the live
`deploy/` + `.github/workflows/` and asserts it exits 0 (any repo state
that would fail the gate is caught in CI before merge).
"""
from __future__ import annotations

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
# Unit tests: _parse_set_env_vars_names
# ---------------------------------------------------------------------------


def test_parse_default_delimiter_comma():
    """Default gcloud CSV form: comma-delimited NAME=VALUE pairs."""
    payload = "A=1,B=2,C=3"
    assert guard._parse_set_env_vars_names(payload) == ["A", "B", "C"]


def test_parse_alt_delimiter_pipe():
    """`^|^` alt-delimiter form for embedding literal commas in values."""
    payload = "^|^A=https://a.example|B=b,with,commas|C=/app"
    assert guard._parse_set_env_vars_names(payload) == ["A", "B", "C"]


def test_parse_skips_malformed_entries():
    """Entries without `=` are silently skipped (not our failure to catch)."""
    payload = "A=1,MALFORMED,B=2"
    assert guard._parse_set_env_vars_names(payload) == ["A", "B"]


def test_parse_empty_payload_yields_empty_list():
    assert guard._parse_set_env_vars_names("") == []


# ---------------------------------------------------------------------------
# Unit tests: _extract_expected_names
# ---------------------------------------------------------------------------


def test_extract_expected_names_finds_bash_array():
    """Extract identifier list from a bash `expected=(...)` array literal."""
    text = """
      - name: Post-deploy env-var-set presence assertion
        run: |
          expected=(
            FBT_PROLOG_URL
            DIV7A_ENGINE_URL
            LANG
            LC_ALL
          )
          echo "$expected"
    """
    result = guard._extract_expected_names(text)
    assert result == ["FBT_PROLOG_URL", "DIV7A_ENGINE_URL", "LANG", "LC_ALL"]


def test_extract_expected_names_returns_none_when_absent():
    """No `expected=(...)` block → return None (workflow skips env-var-set scan)."""
    text = "no expected array here"
    assert guard._extract_expected_names(text) is None


def test_extract_expected_names_empty_array():
    """`expected=()` with no elements returns empty list (a real defect)."""
    text = "expected=()"
    assert guard._extract_expected_names(text) == []


# ---------------------------------------------------------------------------
# Unit tests: _scan_envvar_set_completeness (drift-detection matrix)
# ---------------------------------------------------------------------------


def _fixture(tmp_path: Path, content: str) -> Path:
    """Write a YAML fixture to tmp_path and return its Path."""
    p = tmp_path / "deploy.yml"
    p.write_text(content, encoding="utf-8")
    return p


def test_scan_no_set_env_vars_returns_empty(tmp_path: Path):
    """Workflow without --set-env-vars → not our concern; no findings."""
    p = _fixture(tmp_path, "name: no set-env-vars here\non: push")
    assert guard._scan_envvar_set_completeness(p) == []


def test_scan_set_env_vars_without_expected_flags_drift(tmp_path: Path):
    """A `--set-env-vars` without a co-located `expected=(...)` assertion
    is itself the drift class (no bidirectional coupling to catch missing
    names)."""
    p = _fixture(tmp_path, '''\
      - name: Deploy
        run: |
          gcloud run deploy foo --set-env-vars="A=1,B=2"
    ''')
    findings = guard._scan_envvar_set_completeness(p)
    assert len(findings) == 1
    assert "without co-located canonical expected=() assertion" in findings[0][1]


def test_scan_set_env_vars_matches_expected_passes(tmp_path: Path):
    """When --set-env-vars declaration matches expected=(...) exactly → no
    findings."""
    p = _fixture(tmp_path, '''\
      - name: Deploy
        run: |
          gcloud run deploy foo --set-env-vars="^|^A=1|B=2|C=3"
      - name: Assert
        run: |
          expected=(
            A
            B
            C
          )
    ''')
    assert guard._scan_envvar_set_completeness(p) == []


def test_scan_set_env_vars_omits_expected_flags_drift(tmp_path: Path):
    """When --set-env-vars omits a name that expected=() declares → drift.
    This is the exact Andrew wire-truth failure mode on mc39 PR #27
    (LANG + LC_ALL absent from --set-env-vars but present on live service)."""
    p = _fixture(tmp_path, '''\
      - name: Deploy
        run: |
          gcloud run deploy foo --set-env-vars="^|^A=1|B=2"
      - name: Assert
        run: |
          expected=(
            A
            B
            LANG
            LC_ALL
          )
    ''')
    findings = guard._scan_envvar_set_completeness(p)
    assert len(findings) == 1
    label = findings[0][1]
    assert "omits expected name(s)" in label
    assert "LANG" in label
    assert "LC_ALL" in label


def test_scan_set_env_vars_declares_extra_flags_drift(tmp_path: Path):
    """When --set-env-vars declares a name NOT in expected=(...) → drift
    on the reverse axis (someone added an env-var to deploy but forgot the
    assertion)."""
    p = _fixture(tmp_path, '''\
      - name: Deploy
        run: |
          gcloud run deploy foo --set-env-vars="^|^A=1|B=2|EXTRA=3"
      - name: Assert
        run: |
          expected=(
            A
            B
          )
    ''')
    findings = guard._scan_envvar_set_completeness(p)
    assert len(findings) == 1
    assert "declares name(s) not in the expected=() assertion" in findings[0][1]
    assert "EXTRA" in findings[0][1]


def test_scan_disable_env_via_env_var(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """CLAWDOG_ENVVAR_SET_GUARD_DISABLE=1 turns off env-var-set scan only.
    Placeholder scan still fires."""
    monkeypatch.setenv("CLAWDOG_ENVVAR_SET_GUARD_DISABLE", "1")
    p = _fixture(tmp_path, '''\
      - name: Deploy
        run: |
          gcloud run deploy foo --set-env-vars="A=1"
    ''')
    # No `expected=` co-located → would normally flag; disabled by env-var.
    assert guard._scan_envvar_set_completeness(p) == []


# ---------------------------------------------------------------------------
# Integration test: dogfood against the live repo
# ---------------------------------------------------------------------------


def test_integration_live_repo_passes():
    """The default scan (deploy/ + .github/workflows/) against the live repo
    state exits 0. This is the CI-side gate that mc39.1 wired the fix into
    — if a future PR breaks the coupling, this test fires locally before push."""
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
