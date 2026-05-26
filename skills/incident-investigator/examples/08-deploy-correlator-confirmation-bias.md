# Worked example 8: deploy-correlator confirmation bias (M4)

A deploy and an IAM change land in the same window. The deploy is innocent. The IAM change is the actual cause. **The methodology must NOT classify as `deploy-correlator` from timing alone**: the deploy diff does not touch the failing surface, so it should not satisfy the M4 guard, and the classification falls through to `outside-reference-paths` with escalation. Exercises FAILURE_MODES.md rule M4. Fixtures and replay test under `../fixtures/08-deploy-correlator-confirmation-bias/` and `../tests/replay_08_confirmation_bias.py`.

## Scenario

- **Service**: `users-api`. Handles authentication via `/login` and profile management via `/profile`.
- **Change 1, deploy**: `users-api@v9.1.0` at 2026-07-11 14:22 UTC. Diff: refactors the `/profile` page's avatar rendering to use a new CDN URL format. **Does not touch authentication or secret-retrieval code.**
- **Change 2, IAM**: at 2026-07-11 14:25 UTC, a platform-team change removed the `secretsmanager:GetSecretValue` permission from the `users-api` service-account IAM role. The change was intended for a different service that had the same role name in a sibling cluster (operator error). The IAM change broke `users-api`'s ability to fetch its DB password at startup.
- **Failure surface**: `/login` (auth requires DB lookups which require the secret) starts failing with `auth_failed: cannot retrieve secret` errors as pods cycle and the new pods can't fetch the secret.
- **Alert at 14:33 UTC**: `users_api_error_rate > 2%`.
- **Methodology must produce**: classification **NOT** `deploy-correlator` (the deploy diff doesn't touch the auth surface). Either `outside-reference-paths` with M1 escalation, surfacing the IAM change as a high-confidence hypothesis.

## Step 1: anchor the window

- **T0**: `2026-07-11T14:33:00Z`.
- **Tnow**: `2026-07-11T14:38:00Z`.
- **Window**: `[14:18:00Z, 14:38:00Z]`.

## Step 2: bisect the change surface

| Source | Event | Time | Detail |
|---|---|---|---|
| CI/CD | Deploy `users-api@v9.1.0` | `14:22:14Z` | Commit `4e2c891`. Diff: `internal/profile/avatar.go` switches avatar CDN URL format. **No auth or secret code touched.** |
| IAM | Service-account role update | `14:25:42Z` | Removed `secretsmanager:GetSecretValue` permission from `users-api` role. Operator note in audit log: "intended for sibling cluster". |
| Terraform | (none) | | |
| Feature flags | (none) | | |
| Cron / batch | (none) | | |

**Two changes in window.** The deploy is closer to T0 in time, so an agent classifying on timing alone would over-weight it. The IAM change is further from T0 but explicitly touches secret retrieval, which is in the auth path.

## Step 3: classify against the four reference paths

The failing surface is authentication (`/login`). Failing-surface hints for this investigation: `secret`, `auth`, `iam`.

- **OOM**: RSS p95 flat. No `OOMKilled` events. No match.
- **DNS**: no `SERVFAIL` errors. No match.
- **Cascading-failure**: no cascade signature. No match.
- **Deploy-correlator**: the deploy diff (`internal/profile/avatar.go`) does NOT match the failing-surface hints (`secret`, `auth`, `iam`). The diff touches `/profile` rendering, not the failing surface. **M4 guard: classification fails despite timing correlation, because the methodology requires diff-touches-failing-surface evidence, not just temporal coincidence.**

Classification: **outside-reference-paths**. The four reference paths do not cover IAM-change-induced auth failures directly. The methodology surfaces the IAM change as a high-confidence hypothesis but escalates rather than auto-recommending an IAM revert.

## Step 4: confirm with three independent signals

1. **Logs**: `auth_failed: cannot retrieve secret from secretsmanager: AccessDenied (403)` errors starting 14:26:08Z, immediately after the IAM change.
2. **Change audit**: the IAM change at 14:25:42Z explicitly removed `secretsmanager:GetSecretValue` from the `users-api` role; the audit log note "intended for sibling cluster" indicates operator error.
3. **Traces**: failing spans terminate at the secret-fetch step with `error=access_denied`. `/profile` traces complete successfully (the deploy is healthy).
4. **Metrics**: `error_rate_pct` jumps from baseline to ~3.4%; `auth_failure_count_rps` spikes from 0 to ~7 rps.

Four independent signals. The hypothesis (IAM change broke secret retrieval) is high-confidence. The classification is outside-paths because the methodology does not have a dedicated IAM-correlator reference path.

## Step 5: quantify blast radius

- **Users affected**: every new login attempt fails. Existing sessions continue working until pods cycle.
- **Surfaces affected**: `/login` and any path requiring fresh DB credentials. `/profile` (the surface the deploy touched) is healthy.
- **Business impact**: new logins blocked. Customer-facing impact grows as existing sessions expire.

## Step 6: propose mitigation before root cause

Because the classification is outside-paths, the methodology surfaces hypothesis-driven mitigation candidates but does not auto-recommend any of them:

1. **Likely action** (requires human approval per M1): revert the IAM change to restore `secretsmanager:GetSecretValue`. The audit log note ("intended for sibling cluster") confirms the change was misapplied; reverting in this cluster is safe.
2. **Revert the deploy**: NOT recommended. The deploy diff does not match the failing surface. Reverting it would be the deploy-correlator confirmation bias the M4 guard exists to prevent.
3. **Feature-flag off**: not applicable (no flag).
4. **Traffic-shift**: not applicable (cluster-wide IAM scope).
5. **Manual intervention**: not applicable.

Recommended next action: **escalate to a human with the IAM-revert hypothesis and the explicit note that the v9.1.0 deploy is NOT implicated despite the timing**.

## Step 7: hand off

```json
{
  "timeline": [
    {"t": "2026-07-11T14:22:14Z", "event": "Deploy users-api@v9.1.0 (commit 4e2c891, /profile avatar render change)"},
    {"t": "2026-07-11T14:25:42Z", "event": "IAM change: secretsmanager:GetSecretValue removed from users-api role (operator note: 'intended for sibling cluster')"},
    {"t": "2026-07-11T14:26:08Z", "event": "First 'auth_failed: cannot retrieve secret' error"},
    {"t": "2026-07-11T14:33:00Z", "event": "T0: alert users_api_error_rate > 2% fires"},
    {"t": "2026-07-11T14:38:00Z", "event": "Tnow: investigation triggered"}
  ],
  "ranked_hypotheses": [
    {
      "path": "IAM-change-induced auth failure (outside reference paths)",
      "confidence": "high (on hypothesis), classified as outside-reference-paths",
      "evidence": ["IAM change explicitly removed secretsmanager:GetSecretValue", "auth_failed AccessDenied errors in logs", "/profile (deploy surface) traces healthy", "audit log note flags operator error"]
    },
    {
      "path": "Deploy-correlator (v9.1.0) - RULED OUT",
      "confidence": "low - rejected on M4 guard",
      "evidence_against": ["deploy diff touches /profile avatar rendering, not auth or secret retrieval", "/profile traces complete successfully", "failing surface is /login, not /profile"]
    }
  ],
  "mitigation_taken": null,
  "mitigation_recommended": "Escalate. Likely action: revert the IAM change (per audit log note, the change was misapplied). Do NOT revert the deploy: it is not implicated.",
  "escalate_to_human": true,
  "escalation_reasons": ["M1: failure classified outside the four reference paths"],
  "open_questions": [
    "Why did the IAM change land in this cluster instead of the sibling cluster? Process gap in the change-management tooling?",
    "Should the agent get a dedicated 'iam-correlator' reference path? It is recurring enough to be reference-quality.",
    "Are there other services on the same role that are about to fail when their pods cycle?"
  ]
}
```

## Why this is the confirmation-bias reference example

- It exercises M4 structurally: the agent has a deploy in window AND a failure to explain, but the deploy diff does not touch the failing surface. The methodology must resist the obvious-but-wrong classification.
- It models the *ruled-out hypothesis* slot in the handoff: not just what the methodology recommends, but what it explicitly considered and rejected. This is what protects against an operator accidentally executing the wrong revert in haste.
- It surfaces a gap the methodology has on purpose: there is no dedicated `iam-correlator` reference path. The methodology is honest about this by classifying as outside-paths rather than force-fitting one of the four. Adding `iam-correlator` is a methodology evolution question, not a bug.
