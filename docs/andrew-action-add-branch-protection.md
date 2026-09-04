# Andrew-action: Add branch protection to `main` with required CI status check

**Priority:** highest structural change available in this repo (Fable ruling mc00-2026-09-04 05:41 UTC).
**Complexity:** settings change, not code.
**Time:** ~2 minutes via the GitHub web UI; ~30 seconds via REST if you'd rather.
**Blocker for:** every CI gate we've built this week — the collected-count floor, the smoke floor 22, the ruff lint, `make openapi-check`, `test_manifest_fidelity`, `test_advisory_boundary` — is enforced by CI failing red, but nothing prevents a red PR from being merged today.

---

## The wire-truth that motivated this brief

Fetched 2026-09-04 05:42 UTC as ClawDog with `lodgeit-labs-pat` (Contents+Actions read):

```
GET https://api.github.com/repos/lodgeit-labs/clawdog-calculator-api/branches/main/protection
HTTP: 404
{
  "message": "Branch not protected",
  "documentation_url": "https://docs.github.com/rest/branches/branch-protection#get-branch-protection",
  "status": "404"
}

GET https://api.github.com/repos/lodgeit-labs/clawdog-calculator-api/rulesets
HTTP: 200
[]

GET https://api.github.com/repos/lodgeit-labs/clawdog-calculator-api/rules/branches/main
HTTP: 200
[]
```

**No branch protection. No rulesets. No rules on `main`.** PR #33 sat with `CI — binary-failure gates` failing on two commits (ee01713 + 405cdb6) and GitHub still displayed "No conflicts with base branch — merging can be performed automatically." The only thing that stopped a red merge was the `[DRAFT]` flag on the PR and Andrew reading the check screenshot before clicking the button.

Fable's framing (verbatim):

> *"Everything we have built this week — the collected-count floor, the smoke floor, the mechanical lint gates — is a validator with no consumer at the moment that matters, because a human with the merge button can pass it by without being told they are doing so."*

## What to add

Require the CI status check on `main`:

- **Required status check name:** `lint + binary-failure gates`
  (This is the `jobs.<job-id>.name` value in `.github/workflows/ci.yml`. Confirmed at the repo root: workflow name `CI — binary-failure gates`, job name `lint + binary-failure gates`.)
- **Strict = ON** (require branches to be up-to-date before merging). Prevents the "stale PR passes CI on old base" defect the smoke-prod arc hit twice.
- **Do not allow bypass by administrators.** Andrew is the only human with write, so this is a one-line "you promise to always merge through the PR flow" self-covenant. In practice CI takes 20-60s to run on a push; the friction cost is trivial.

## Two paths — pick either

### Path A — GitHub web UI (2 minutes; explicit click-path)

1. Open **https://github.com/lodgeit-labs/clawdog-calculator-api** in a browser (logged in as the `lodgeit-labs` org admin, which is you).
2. Click the **Settings** tab (top-right of the repo nav bar, next to Insights).
3. In the left sidebar under **Code and automation**, click **Branches**.
4. Under **Branch protection rules**, click the green **Add branch protection rule** button.
5. In **Branch name pattern**, type: `main`
6. Tick **Require a pull request before merging**.
   - Under it, tick **Require approvals** and set the count to `1` (self-approval covers this since you're the sole reviewer today; when Anton/Renat join reviewer flow, this stays 1 without any config change).
   - Leave **Dismiss stale pull request approvals when new commits are pushed** UNticked (would force re-approval after every push; unnecessary given the reviewer is the same person).
7. Tick **Require status checks to pass before merging**.
   - Tick **Require branches to be up to date before merging** (strict mode).
   - In the **Search for status checks in the last week for this repository** box, type: `lint + binary-failure gates`
     - The check should appear in the dropdown (CI has run for it on both commits of PR #33 within the last hour, so GitHub knows the name).
     - Click it to add it to the required list.
   - **If the check does not appear in the dropdown**, that means CI has not registered a run against `main` recently; workaround: type the exact string `lint + binary-failure gates` and press Enter to add it as a required check pending — it will engage on the next run against `main`.
8. Leave everything else at defaults.
9. Scroll to the bottom, click the green **Create** button.
10. You will be prompted for your GitHub credential (usual OAuth flow); complete it.

Verify: re-open the same Branches page and confirm the rule appears with `main` as the pattern and `lint + binary-failure gates` in the "Required status checks" line.

### Path B — REST API (30 seconds; one curl)

Requires a PAT with `admin` scope on the repo. `lodgeit-labs-pat` currently has `metadata=read` + `contents=read` + `actions=read` (fetched mc00 05:34 UTC); it does NOT have `admin`. You (Andrew) can either grant `admin` to the PAT temporarily or use your web session — Path A is more auditable and only takes two minutes.

For reference (do NOT run under the current PAT scope):

```bash
# Replace <PAT_WITH_ADMIN> with a PAT that has admin:repo_hook + write:repo_admin.
curl -X PUT \
  -H "Authorization: token <PAT_WITH_ADMIN>" \
  -H "Accept: application/vnd.github.v3+json" \
  https://api.github.com/repos/lodgeit-labs/clawdog-calculator-api/branches/main/protection \
  -d '{
    "required_status_checks": {
      "strict": true,
      "checks": [
        {"context": "lint + binary-failure gates"}
      ]
    },
    "enforce_admins": false,
    "required_pull_request_reviews": {
      "required_approving_review_count": 1,
      "dismiss_stale_reviews": false
    },
    "restrictions": null
  }'
```

Note `enforce_admins: false` is deliberate — the ClawDog Git Protocol already routes all Andrew writes through PR + human sign-off; enforcing it via GitHub too would trigger the friction cost on legitimate emergency rollbacks. If you want that ratcheted up later, flip to `true` in a follow-up.

## Verify it engaged

After either path, this should return HTTP 200 with the protection ruleset body:

```bash
PAT=$(awk -F'[:@]' '/lodgeit-labs-pat/ {print $3}' ~/.git-credentials | head -1)
curl -sS -H "Authorization: token $PAT" \
  https://api.github.com/repos/lodgeit-labs/clawdog-calculator-api/branches/main/protection \
  | python3 -m json.tool
```

Expected: `required_status_checks.checks[]` includes `{"context": "lint + binary-failure gates", ...}` and `strict: true`.

Independent probe: open PR #33 in the browser and confirm the merge button says something like *"Required check — waiting for status checks to complete"* rather than the unconditional "merging can be performed automatically" that it says today.

## After this ships

The following gates immediately become enforced-at-merge rather than advisory:

- **Ruff import discipline** — the failure class that caught out mc00 (ee01713 + 405cdb6).
- **Deploy-placeholder guard** — the mc16-2026-05-25 arc.
- **OpenAPI drift** — Lesson #35 anchor.
- **Full pytest suite** — 247 tests as of mc00.
- **Collected-count floor 230** — Fable mc19 gate; catches stale-checkout / massive test-loss scenarios.

The pre-push hook Layer 3 becomes correctly labelled as what Fable ruled it should be: a feedback-loop shortener. Nothing to change on that side once this ships.

## Cross-repo pattern

Same wire-truth check for the sibling engines: `lodgeit-labs/depreciation-engine`, `lodgeit-labs/div7a-engine`, `lodgeit-labs/LodgeiT_FBT`. Each of them should carry an equivalent `main` protection with their own CI job name required. Not blocking this PR; noted as a follow-up sweep. When you have branch-protection admin on any of them, apply the same shape.

---

*Fable ruling banked mc00-2026-09-04 05:41 UTC. ClawDog authored 05:42 UTC. Waiting on Andrew action; not blocking defence-in-depth or the rest of PR #33's six-item batch.*
