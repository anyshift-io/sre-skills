# Worked example 8: deploy-correlator confirmation bias (M4)

A Deployment rollout and an RBAC change land in the same window. The rollout is innocent. The RBAC change is the actual cause. **The methodology must NOT classify as `deploy-correlator` from timing alone**: the rollout diff does not touch the failing surface, so it should not satisfy the M4 guard, and the classification falls through to `outside-reference-paths` with escalation. Exercises FAILURE_MODES.md rule M4. Fixtures and replay test under `../fixtures/08-deploy-correlator-confirmation-bias/` and `../tests/replay_08_confirmation_bias.py`.

## Scenario

- **Service**: `users-api`, a Kubernetes Deployment in namespace `users`. Handles authentication via `/login` and profile management via `/profile`.
- **Change 1, rollout**: `users-api@v9.1.0` at 2026-07-11 14:22 UTC. Diff: refactors the `/profile` page's avatar rendering to use a new CDN URL format. **Does not touch authentication or secret-retrieval code.**
- **Change 2, RBAC**: at 2026-07-11 14:25 UTC, a platform-team change deleted the RoleBinding `users-api-secrets-reader`, which granted the `users-api` ServiceAccount `get` on Secrets in namespace `users`. The change was intended for a sibling cluster (operator error). Deleting the RoleBinding broke `users-api`'s ability to read its DB-password Secret from the Kubernetes API at startup.
- **Failure surface**: `/login` (auth requires DB lookups which require the Secret) starts failing with `auth_failed: cannot read Secret` errors as pods cycle and the new pods can't read the Secret from the API.
- **Alert at 14:33 UTC**: `users_api_error_rate > 2%`.
- **Methodology must produce**: classification **NOT** `deploy-correlator` (the rollout diff doesn't touch the auth surface). Either `outside-reference-paths` with M1 escalation, surfacing the RBAC change as a high-confidence hypothesis.

## Step 1: anchor the window

- **T0**: `2026-07-11T14:33:00Z`.
- **Tnow**: `2026-07-11T14:38:00Z`.
- **Window**: `[14:18:00Z, 14:38:00Z]`.

## Step 2: bisect the change surface

| Source | Event | Time | Detail |
|---|---|---|---|
| Rollout | Deploy `users-api@v9.1.0` | `14:22:14Z` | Commit `4e2c891`. Diff: `internal/profile/avatar.go` switches avatar CDN URL format. **No auth or secret code touched.** |
| RBAC | RoleBinding deletion | `14:25:42Z` | Deleted RoleBinding `users-api-secrets-reader` granting the `users-api` ServiceAccount `get` on Secrets in namespace `users`. Operator note in audit log: "intended for sibling cluster". |
| Cluster / HPA | (none) | | |
| ConfigMap / flags | (none) | | |
| CronJob | (none) | | |

**Two changes in window.** The rollout is closer to T0 in time, so an agent classifying on timing alone would over-weight it. The RBAC change is further from T0 but explicitly touches Secret access, which is in the auth path.

## Step 3: classify against the four reference paths

The failing surface is authentication (`/login`). Failing-surface hints for this investigation: `secret`, `auth`, `rbac`.

- **OOM**: RSS p95 flat. No `OOMKilled` events. No match.
- **DNS**: no `SERVFAIL` errors. No match.
- **Cascading-failure**: no cascade signature. No match.
- **Deploy-correlator**: the rollout diff (`internal/profile/avatar.go`) does NOT match the failing-surface hints (`secret`, `auth`, `rbac`). The diff touches `/profile` rendering, not the failing surface. **M4 guard: classification fails despite timing correlation, because the methodology requires diff-touches-failing-surface evidence, not just temporal coincidence.**

Classification: **outside-reference-paths**. The four reference paths do not cover RBAC-change-induced auth failures directly. The methodology surfaces the RBAC change as a high-confidence hypothesis but escalates rather than auto-recommending an RBAC revert.

## Step 4: confirm with three independent signals

1. **Logs**: `auth_failed: cannot read Secret: secrets "users-api-db-password" is forbidden: User "system:serviceaccount:users:users-api" cannot get resource "secrets" in API group "" in the namespace "users" (403 Forbidden)` errors starting 14:26:08Z, immediately after the RBAC change.
2. **Change audit**: the RBAC change at 14:25:42Z explicitly deleted the RoleBinding `users-api-secrets-reader` granting the `users-api` ServiceAccount `get` on Secrets; the audit log note "intended for sibling cluster" indicates operator error.
3. **Traces**: failing spans terminate at the `kube-apiserver` hop with `http.status_code=403` / `error=Forbidden` when reading the Secret. `/profile` traces complete successfully (the rollout is healthy).
4. **Metrics**: `error_rate_pct` jumps from baseline to ~3.4%; `auth_failure_count_rps` spikes from 0 to ~7 rps.

Four independent signals. The hypothesis (the RBAC change broke Secret access) is high-confidence. The classification is outside-paths because the methodology does not have a dedicated RBAC-correlator reference path.

## Step 5: quantify blast radius

- **Users affected**: every new login attempt fails. Existing sessions continue working until pods cycle.
- **Surfaces affected**: `/login` and any path requiring fresh DB credentials. `/profile` (the surface the rollout touched) is healthy.
- **Business impact**: new logins blocked. Customer-facing impact grows as existing sessions expire.

## Step 6: propose mitigation before root cause

Because the classification is outside-paths, the methodology surfaces hypothesis-driven mitigation candidates but does not auto-recommend any of them:

1. **Likely action** (requires human approval per M1): restore the deleted RoleBinding `users-api-secrets-reader` to grant the `users-api` ServiceAccount `get` on Secrets again. The audit log note ("intended for sibling cluster") confirms the change was misapplied; restoring it in this cluster is safe.
2. **`kubectl rollout undo`**: NOT recommended. The rollout diff does not match the failing surface. Reverting it would be the deploy-correlator confirmation bias the M4 guard exists to prevent.
3. **Feature-flag off**: not applicable (no flag).
4. **Traffic-shift**: not applicable (namespace-wide RBAC scope).
5. **Manual intervention**: not applicable.

Recommended next action: **escalate to a human with the RBAC-restore hypothesis and the explicit note that the v9.1.0 rollout is NOT implicated despite the timing**.

## Step 7: hand off

```json
{
  "timeline": [
    {"t": "2026-07-11T14:22:14Z", "event": "Deploy users-api@v9.1.0 (commit 4e2c891, /profile avatar render change)"},
    {"t": "2026-07-11T14:25:42Z", "event": "RBAC change: RoleBinding users-api-secrets-reader deleted (get on Secrets in ns users; operator note: 'intended for sibling cluster')"},
    {"t": "2026-07-11T14:26:08Z", "event": "First 'auth_failed: cannot read Secret ... is forbidden (403 Forbidden)' error"},
    {"t": "2026-07-11T14:33:00Z", "event": "T0: alert users_api_error_rate > 2% fires"},
    {"t": "2026-07-11T14:38:00Z", "event": "Tnow: investigation triggered"}
  ],
  "ranked_hypotheses": [
    {
      "path": "RBAC-change-induced auth failure (outside reference paths)",
      "confidence": "high (on hypothesis), classified as outside-reference-paths",
      "evidence": ["RBAC change explicitly deleted RoleBinding users-api-secrets-reader (get on Secrets)", "auth_failed '403 Forbidden' Secret-read errors in logs", "/profile (rollout surface) traces healthy", "audit log note flags operator error"]
    },
    {
      "path": "Deploy-correlator (v9.1.0) - RULED OUT",
      "confidence": "low - rejected on M4 guard",
      "evidence_against": ["rollout diff touches /profile avatar rendering, not auth or Secret access", "/profile traces complete successfully", "failing surface is /login, not /profile"]
    }
  ],
  "mitigation_taken": null,
  "mitigation_recommended": "Escalate. Likely action: restore the deleted RoleBinding users-api-secrets-reader (per audit log note, the change was misapplied). Do NOT run kubectl rollout undo: the rollout is not implicated.",
  "escalate_to_human": true,
  "escalation_reasons": ["M1: failure classified outside the four reference paths"],
  "open_questions": [
    "Why did the RBAC change land in this cluster instead of the sibling cluster? Process gap in the change-management tooling?",
    "Should the agent get a dedicated 'rbac-correlator' reference path? It is recurring enough to be reference-quality.",
    "Are there other workloads using the same RoleBinding that are about to fail when their pods cycle?"
  ]
}
```

## Why this is the confirmation-bias reference example

- It exercises M4 structurally: the agent has a rollout in window AND a failure to explain, but the rollout diff does not touch the failing surface. The methodology must resist the obvious-but-wrong classification.
- It models the *ruled-out hypothesis* slot in the handoff: not just what the methodology recommends, but what it explicitly considered and rejected. This is what protects against an operator accidentally running `kubectl rollout undo` in haste.
- It surfaces a gap the methodology has on purpose: there is no dedicated `rbac-correlator` reference path. The methodology is honest about this by classifying as outside-paths rather than force-fitting one of the four. Adding `rbac-correlator` is a methodology evolution question, not a bug.
