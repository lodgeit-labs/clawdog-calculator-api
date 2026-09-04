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

**Live fact worth naming** (Fable ruling mc00-2026-09-04 07:07 UTC): the workflow `.github/workflows/ci.yml` on this repo defines four jobs. Two are required for merge (the pair above). Two run on every push but do **NOT** block merge:

- `Scaffold verification (mc02 — pre-operational)` — advisory-only
- `ruff + mypy (D1 populates substrate)` — advisory-only

Someone reading "CI is required on `main`" will otherwise believe *all* CI runs are gating. They are not. Anyone adding a `ruff` or `mypy` finding on this repo has to notice the red check on their own; the ruleset will not stop them. Fable framing: *"someone will otherwise read 'CI is required' and believe all of it is."*

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

## Fable ruling mc00-2026-09-04 07:07 UTC: FLIP strict mode ON, both repos

**Ruled.** Both rulesets carry `strict_required_status_checks_policy: false` today. Fable's earlier framing (skip strict; single committer; forces rebases) held only for a one-PR-at-a-time workflow, which is exactly when the setting costs nothing. The moment it costs something is the moment two branches are open, and that is the moment it starts earning.

Fable ruling verbatim (mc00 07:07 UTC):

> *"The defect it prevents is this arc's signature: green measured against a substrate that has since moved. We have now caught that shape at the engine/gateway boundary, at the merge/deploy boundary, at the local/CI boundary and at the branch/main boundary. Arm the gate before the incident, not after it. Flip it, and note in the brief that a rebase prompt on merge is the gate working rather than friction."*

**What flipping strict changes** at the merge button:

- ❌ *Before* (current state): a PR green on an old base can merge into a moved `main`; the merged result has never run CI.
- ✅ *After* (ruled state): if `main` moves after a PR's last green run, GitHub prompts a rebase / update from base before allowing merge. CI re-runs against the merged shape. That prompt is the gate working, not friction.

### Web UI path (2 minutes per repo; Andrew action)

1. Open `https://github.com/lodgeit-labs/clawdog-calculator-api/settings/rules` (or the equivalent for `depreciation-engine`).
2. Click the `Protect_Main` ruleset.
3. Under **Rules → Require status checks to pass**, tick **Require branches to be up to date before merging**.
4. Save.
5. Repeat on the sibling repo.

Verify via wire:

```bash
PAT=$(awk -F'[:@]' '/lodgeit-labs-pat/ {print $3}' ~/.git-credentials | head -1)
for repo in clawdog-calculator-api depreciation-engine; do
  echo "=== $repo ==="
  curl -sS -H "Authorization: token $PAT" \
    "https://api.github.com/repos/lodgeit-labs/$repo/rules/branches/main" \
    | python3 -c "import json,sys; \
      d=json.load(sys.stdin); \
      r=next(x for x in d if x['type']=='required_status_checks'); \
      print('strict:', r['parameters']['strict_required_status_checks_policy'])"
done
```

Expected after flip: `strict: True` on both.

### REST path (needs admin scope; deferred)

Would require a PAT with `repository_administration:write` or classic admin scope. `lodgeit-labs-pat` today has `metadata=read + contents=read + actions=read` — wire-confirmed at mc00 07:12 UTC by attempting a PATCH on the ruleset and receiving `HTTP 404 "Not Found"` (GitHub's 404 signal for unauthorised scope). Web UI is the faster path either way.

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
