# Andrew-action: Branch protection / rulesets on `main`

**Status:** ✅ **SHIPPED 2026-09-04 mc00 by Andrew.** This document evolves into the runbook + audit log for the ruleset configuration; the "Andrew-action" framing above is retained for the git-log context in which it was created.

---

## Wire-verified current state (2026-09-04 06:57 UTC)

Fetched with `lodgeit-labs-pat` (metadata=read + contents=read + actions=read).

### `lodgeit-labs/clawdog-calculator-api` (visibility: PUBLIC)

`GET /repos/lodgeit-labs/clawdog-calculator-api/rules/branches/main` → HTTP 200; ruleset id 22251624 active with:

- `deletion` — refuse `main` deletion
- `non_fast_forward` — refuse force-push to `main`
- `required_status_checks`:
  - `strict_required_status_checks_policy: false` ⚠️
  - required contexts:
    - `lint + binary-failure gates` (integration_id 15368 = GitHub Actions)

### `lodgeit-labs/depreciation-engine` (visibility: PRIVATE)

`GET /repos/lodgeit-labs/depreciation-engine/rules/branches/main` → HTTP 200; ruleset id 22252039 active with:

- `deletion`
- `non_fast_forward`
- `required_status_checks`:
  - `strict_required_status_checks_policy: false` ⚠️
  - required contexts:
    - `4 mechanical lint gates (D1 active; L#65 operation-probe on gate 4)`
    - `pytest + hypothesis (D1 populates substrate)`

### Legacy branch-protection API surface

`GET /repos/{repo}/branches/main/protection` → HTTP 404 `"Branch not protected"` on both. This is expected. Rulesets and legacy branch protection are two DIFFERENT enforcement surfaces on GitHub; a ruleset does not populate the legacy branch-protection response. Do not treat the 404 as evidence of "no protection" — check the rulesets endpoint alongside it.

## Prerequisite that was omitted from the original brief

Fable ruling 2026-09-04 06:55 UTC (verbatim):

> *"Rulesets and branch protection do not enforce on private repos under a Free org plan. Andrew hit the warning banner mid-configuration. The brief would have led a future reader to configure a ruleset, see 'Active', and believe the branch was protected while nothing was enforced — a gate that reports success without doing anything, which is the exact artefact class this whole tranche exists to eliminate. Amend it: plan prerequisite first, then the click-path."*

**Correct plan matrix (as of 2026-09):**

| Org plan | Public repos: rulesets enforce | Private repos: rulesets enforce |
|---|---|---|
| Free | ✅ Yes | ❌ **No — silently ignored, banner shown mid-config** |
| Team | ✅ Yes | ✅ Yes |
| Enterprise | ✅ Yes | ✅ Yes |

**Prerequisite check-path (do this BEFORE clicking "Create ruleset" on any private repo):**

1. Open `https://github.com/organizations/lodgeit-labs/settings/billing` (or the org's Billing page).
2. Confirm plan is Team or Enterprise. If it says Free, upgrade first — the ruleset UI will let you configure and mark it "Active" but the rules will NOT enforce on private repos until the upgrade lands.

Andrew shipped this on 2026-09-04 by upgrading `lodgeit-labs` → Team **before** configuring the two rulesets, so both are wire-verified enforcing today. Anyone applying this pattern to a sibling repo in a different org MUST re-check the plan first.

## Known non-strict gap (surfaced by wire-verification; not yet closed)

Both current rulesets have `strict_required_status_checks_policy: false`. This means:

- ✅ A PR whose head SHA has a red required check CANNOT merge.
- ❌ A PR whose head SHA has a green check can merge even if `main` has moved since — the CI green was against an older base, and the merged result has NEVER been tested.

This is the exact defect class the "smoke-prod stale-truncated-checkout" arc surfaced (n=3 on this repo through mc-arc). If a merge-order dependency exists across two PRs, PR-B can merge green against a PR-A base state that PR-A itself just superseded, and the merged `main` state has never run CI.

**To close: turn strict mode ON on both rulesets.**

Web UI path:
1. Settings → Rules → Rulesets → click the `Protect_Main` ruleset.
2. Under "Require status checks to pass" → tick "Require branches to be up to date before merging".
3. Save.

REST path (needs admin scope which `lodgeit-labs-pat` currently lacks — Andrew action):

```bash
# Fetch the current ruleset payload, flip strict to true, PUT it back.
PAT=<admin_scoped_pat>
for repo in clawdog-calculator-api depreciation-engine; do
  # Get the ruleset id from the branches/main enumeration:
  RULESET_ID=$(curl -sS -H "Authorization: token $PAT" \
    "https://api.github.com/repos/lodgeit-labs/$repo/rules/branches/main" \
    | python3 -c "import json,sys; d=json.load(sys.stdin); \
      print(next(r['ruleset_id'] for r in d if r['type']=='required_status_checks'))")
  # Fetch the ruleset:
  curl -sS -H "Authorization: token $PAT" \
    "https://api.github.com/repos/lodgeit-labs/$repo/rulesets/$RULESET_ID" \
    > /tmp/ruleset.json
  # Edit strict to true in the required_status_checks rule; PUT back.
  # (Manual edit required; the payload is nested. Web UI is faster.)
done
```

The cost of leaving strict off is a class-of-defect (stale-base merge) that ClawDog has already hit n=3 times this arc. The cost of turning it on is one extra CI run per merge when `main` has moved, which is 20-60s on either repo. Recommendation: turn it on.

## Check-name parity discipline (going forward)

Fable ruling 2026-09-04 06:55 UTC (verbatim):

> *"A ruleset that requires a check name nothing reports blocks every merge forever, and a ruleset requiring only lint leaves the test suite ungated. Report specifically which check names appear in the required list."*

**Wire-verified parity as of 2026-09-04 06:57 UTC:**

`clawdog-calculator-api`:
- Ruleset required: `lint + binary-failure gates` ✅
- CI job name emitted: `lint + binary-failure gates` (grep `.github/workflows/ci.yml`: `jobs.lint-and-test.name`)
- Match: exact.

`depreciation-engine`:
- Ruleset required: `4 mechanical lint gates (D1 active; L#65 operation-probe on gate 4)` ✅
- Ruleset required: `pytest + hypothesis (D1 populates substrate)` ✅
- CI jobs emitted (per `.github/workflows/ci.yml`): four total — `Scaffold verification`, `pytest + hypothesis`, `ruff + mypy`, `4 mechanical lint gates`.
- Match: two of four required. Two jobs (`Scaffold verification`, `ruff + mypy`) run on every push but are NOT gating merge — they are advisory-only. This is a design choice, not a defect, but it's the class Fable flagged: someone reading the ruleset can not tell without cross-checking the workflow.

**Discipline for future ruleset changes:**

Whenever adding a new CI job that should be merge-gating:
1. Add the job to `.github/workflows/ci.yml` with an EXACT job name (no drift-prone commit refs / dates in the name).
2. Wait for at least one run against the target branch so GitHub knows the name exists.
3. Add the exact string to the ruleset's required-checks list.
4. Wire-verify via `GET /repos/{repo}/rules/branches/main` that the required list now contains it, spelt identically to the workflow job name.

If step 4 shows a mismatch (typo, casing, punctuation drift), the ruleset will block every future PR merge until the check reports — which for a nonexistent name is forever. Fable-named artefact class: "a gate that requires a check name nothing reports."

## Cross-repo TODO (sweep queued, not blocking)

Other repos in the constellation that would benefit from the same shape when reached:

- `lodgeit-labs/LodgeiT_FBT` (FBT engine)
- `lodgeit-labs/Div7A_Calculator` (Div7A engine)
- `lodgeit-labs/HP_Calculator` (hire-purchase, not-yet-built)
- Any new engine spun up post-mc00.

Each should carry the same three rules (`deletion`, `non_fast_forward`, `required_status_checks`) with strict-on and every gating CI job's name in the required list.

---

## Original brief (retained for audit trail; superseded by state above)

*Original context: authored 2026-09-04 05:42 UTC when neither ruleset existed. The web-UI click-path and REST reference below are still valid; the prerequisite section above (Team plan check) is what was missing.*

### The wire-truth that motivated the original brief

```
GET https://api.github.com/repos/lodgeit-labs/clawdog-calculator-api/branches/main/protection
HTTP: 404 "Branch not protected"

GET https://api.github.com/repos/lodgeit-labs/clawdog-calculator-api/rulesets
HTTP: 200 []

GET https://api.github.com/repos/lodgeit-labs/clawdog-calculator-api/rules/branches/main
HTTP: 200 []
```

No branch protection. No rulesets. No rules on main. PR #33 sat with `CI — binary-failure gates` failing on two commits (ee01713 + 405cdb6) and GitHub still displayed "No conflicts with base branch — merging can be performed automatically." The only thing that stopped a red merge was the `[DRAFT]` flag on the PR and Andrew reading the check screenshot before clicking the button.

Fable's original framing (verbatim):

> *"Everything we have built this week — the collected-count floor, the smoke floor, the mechanical lint gates — is a validator with no consumer at the moment that matters, because a human with the merge button can pass it by without being told they are doing so."*

### Path A — GitHub web UI

1. Open the repo Settings → **Rules** → **Rulesets** → **New ruleset** → **New branch ruleset**.
2. Name: `Protect_Main`.
3. Enforcement status: **Active**.
4. Bypass list: leave empty.
5. Target branches → **Include default branch**.
6. Rules to enable:
   - **Restrict deletions**
   - **Block force pushes**
   - **Require status checks to pass**
     - Tick **Require branches to be up to date before merging** (strict) — see "Known non-strict gap" above; original brief had this as required, current shipped state has it as false.
     - Add each gating CI job name verbatim to the required-checks list.
7. Save.

### Path B — REST API

Requires a PAT with `admin:repo_hook` or `admin` scope on the repo. `lodgeit-labs-pat` today has `metadata=read` + `contents=read` + `actions=read`; not admin. Andrew shipped via Path A.

---

*Ruling banked mc00-2026-09-04 05:41 UTC (original) + 06:55 UTC (Fable amendment: plan prerequisite). ClawDog wire-verified 06:57 UTC. Runbook status: ACTIVE.*
