# Worked example 7: blast-radius asymmetric revert (deploy bundle)

A deploy bundle that shipped six unrelated changes in one release train. Only one of them is causing the incident, but reverting the bundle reverts all six. The methodology must **classify the path correctly and rank revert as the top mitigation**, but then **escalate with M3** because the revert's blast radius exceeds the incident's blast radius. Exercises FAILURE_MODES.md rule M3. Fixtures and replay test under `../fixtures/07-blast-radius-asymmetric-revert/` and `../tests/replay_07_blast_radius.py`.

## Scenario

- **Service**: `notifications-svc`. Sends transactional emails, SMS, and push notifications.
- **Deploy at 2026-06-02 09:48 UTC**: a weekly release train shipped six unrelated PRs in one bundle (commit `8b3f4d1`, version `v8.12.0`):
  1. SMS provider integration update (Twilio API v2 migration).
  2. Email template refactor.
  3. Push notification batching optimization.
  4. Removal of deprecated SES region fallback.
  5. New /healthz endpoint.
  6. Dependency upgrades (express 4.x → 5.x).
- **The actual failure**: the SMS integration update (PR 1 of 6) shipped with an invalid sender ID format that the new Twilio API rejects. SMS delivery is now failing 100% of the time. The other five changes are fine.
- **Alert at 10:03 UTC**: `notifications_sms_error_rate > 50%`.
- **Methodology must produce**: classification deploy-correlator (or close), revert as the top mitigation, **escalation with M3** because reverting `v8.12.0` rolls back the other five working changes too.

## Step 1: anchor the window

- **T0**: `2026-06-02T10:03:00Z`.
- **Tnow**: `2026-06-02T10:10:00Z`.
- **Window**: `[09:48:00Z, 10:10:00Z]`.

## Step 2: bisect the change surface

| Source | Event | Time | Detail |
|---|---|---|---|
| CI/CD | Deploy `notifications-svc@v8.12.0` | `09:48:23Z` | Commit `8b3f4d1`. **Bundle of 6 PRs.** Diff summary lists Twilio v2 migration, email template refactor, push batching, SES fallback removal, /healthz, express 5.x upgrade. |
| Terraform | (none) | | |
| IAM | (none) | | |
| Feature flags | (none) | | |
| Cron / batch | (none) | | |

One change in window, but the change is a bundle of six. This is the M3 trigger.

## Step 3: classify against the four reference paths

- **OOM**: RSS p95 flat at ~210 MB against 512 MB limit. No `OOMKilled` events. No match.
- **DNS**: no `SERVFAIL` / `getaddrinfo` errors. Outbound to Twilio resolves fine. No match.
- **Cascading-failure**: no retry storm, no upstream-latency growth. The failure is at the SMS provider hop with HTTP 400, not slowness. No match.
- **Deploy-correlator**: deploy in window; diff explicitly touches the SMS path (Twilio API v2 migration line in the bundle); SMS error rate jumped from 0 to 100% within 90 seconds of the deploy. **Match.**

Classification: **deploy-correlator**, specifically the Twilio API v2 migration PR within the bundle. The other five PRs are not implicated by any signal.

## Step 4: confirm with three independent signals

1. **Logs** (`fixtures/07-blast-radius-asymmetric-revert/logs.jsonl`): `Twilio API rejected request: 400 invalid 'from' field, expected E.164 format` errors starting 09:49:51Z.
2. **Metrics** (`fixtures/07-blast-radius-asymmetric-revert/metrics.json`): `sms_error_rate_pct` jumps from 0.0% baseline to 100% at 09:50; `email_error_rate_pct` and `push_error_rate_pct` flat (proving the failure is SMS-scoped, not service-wide).
3. **Deploy diff** (`fixtures/07-blast-radius-asymmetric-revert/deploys.json`): bundle includes Twilio v2 migration line that matches the failing surface.
4. **Traces** (`fixtures/07-blast-radius-asymmetric-revert/traces.jsonl`): SMS-sending spans terminate at the `twilio` hop with `http.status_code=400`; email-sending and push-sending spans complete successfully.

Four independent signal sources. Confidence high.

## Step 5: quantify blast radius

- **Users affected**: every user who would receive an SMS notification. Email and push channels are unaffected.
- **Surfaces affected**: SMS sending only. Other notification channels healthy.
- **Business impact**: SMS-dependent flows broken (2FA SMS, OTP, delivery alerts). Email and push fallbacks compensate partially for some flows but not for 2FA.

**Revert blast radius**: reverting `v8.12.0` would also roll back five working changes (email template refactor, push batching, SES fallback removal, /healthz, express 5.x). Two of those (the SES removal and express 5.x upgrade) have downstream consumers already depending on the new state. Revert is asymmetric: it removes a 100%-broken feature (SMS) at the cost of regressing five healthy features.

## Step 6: propose mitigation before root cause

1. **Revert** `notifications-svc` to `v8.11.4`. This is the methodology's top recommendation, BUT it carries the M3 caveat: blast radius exceeds the incident's blast radius. **Requires a human approver.**
2. **Feature-flag off**: not applicable; the Twilio v2 migration shipped without a flag.
3. **Scale**: not applicable.
4. **Traffic-shift**: not applicable.
5. **Manual intervention**: not applicable.

A human-approved alternative the methodology surfaces but does not unilaterally recommend: **forward-fix** by shipping a targeted patch to the SMS sender ID format (a one-line fix), rather than reverting the bundle. Forward-fix avoids the regression of the five healthy changes but introduces deployment-pipeline risk (the bundle's other changes have been live for ~15 min; reverting and re-shipping the five working changes is operationally noisier).

Recommended action: **revert + escalate to human for blast-radius approval, with forward-fix surfaced as the cleaner alternative**.

## Step 7: hand off

```json
{
  "timeline": [
    {"t": "2026-06-02T09:48:23Z", "event": "Deploy notifications-svc@v8.12.0 (bundle of 6 PRs, commit 8b3f4d1)"},
    {"t": "2026-06-02T09:49:51Z", "event": "First Twilio 400 invalid 'from' field error"},
    {"t": "2026-06-02T10:03:00Z", "event": "T0: alert notifications_sms_error_rate > 50% fires"},
    {"t": "2026-06-02T10:10:00Z", "event": "Tnow: investigation triggered"}
  ],
  "ranked_hypotheses": [
    {
      "path": "Deploy-correlator (Twilio v2 migration within bundle)",
      "confidence": "high",
      "evidence": ["bundle diff includes Twilio v2 migration line", "sms-only error pattern, email/push unaffected", "Twilio 400 invalid 'from' field errors in logs", "traces fail at twilio hop"]
    }
  ],
  "mitigation_taken": null,
  "mitigation_recommended": "Revert notifications-svc to v8.11.4 (M3 escalation flagged: bundle of 6 changes, revert reverts all six)",
  "alternative_mitigation": "Forward-fix: ship a targeted patch to the SMS sender ID format. Preserves the five healthy changes in the bundle but takes longer than revert.",
  "escalate_to_human": true,
  "escalation_reasons": ["M3: recommended revert affects 6 bundled changes, broader blast radius than the incident; requires a human approver before executing"],
  "open_questions": [
    "Why did the SMS sender ID format change land without a contract test against the Twilio v2 sandbox?",
    "Should the release train be split into one-PR-per-deploy for high-risk integration changes like SMS provider migrations?",
    "Is there a way to revert a single commit out of a bundle, or does the deploy pipeline require atomic version rollback?"
  ]
}
```

## Why this is the asymmetric-revert reference example

- It models a real-world operational tension: revert is often correct *at the methodology level* but unsafe *at the operational level* when the change being reverted is bundled. The methodology must surface this conflict, not gloss it.
- It exercises M3 explicitly, with `bundle_size = 6` in the deploy fixture and a methodology that escalates when bundle size > 1 on a revert recommendation.
- It models the *alternative-mitigation* slot in the handoff: when the top recommendation is conflicted, the methodology should surface a cleaner alternative (forward-fix) rather than only flagging the conflict and stopping.
