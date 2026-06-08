# Worked example 6: ambiguous T0 (slow-burn memory leak)

A failure where T0 is genuinely unclear: the operator says "the service has been slow all morning", error rate has been creeping up for hours, no single alert fire-time pinpoints the start. The methodology must **flag T0 as ambiguous, classify with reduced confidence, and escalate with M2** so a human re-runs the investigation against a widened window. Exercises FAILURE_MODES.md rule M2. Fixtures and replay test under `../fixtures/06-ambiguous-t0-slow-burn/` and `../tests/replay_06_ambiguous_t0.py`.

## Scenario

- **Service**: `recommendations-api`. Operator reports at 12:15 that "recs have been slow all morning, finally got around to looking".
- **Underlying issue**: a memory leak introduced by a deploy three days ago. RSS has been climbing steadily for ~72 hours, finally crossing the threshold where GC pauses started showing up around 09:30 today. Error rate ticked up from 0.3% to 1.4% over the morning, well below the 2% alert threshold.
- **No alert fired**. The investigation was triggered manually by the operator.
- **Methodology must produce**: classification (likely OOM, given the signature), but with the **t0_ambiguous flag set**, escalation reasons including **M2**, and the recommended mitigation must include a "re-check after widening window" step before any irreversible action.

## Step 1: anchor the window

The operator-reported symptom ("slow all morning") does not pinpoint a single T0. Per SKILL.md step 1:

> If T0 is ambiguous (e.g. "slow all morning"), pick the earliest unambiguous signal and note the ambiguity in the timeline. Do not silently round.

Earliest unambiguous signal: the first GC pause warning at `2026-04-19T09:32:14Z`. T0 set there with `t0_ambiguous = true`.

- **T0**: `2026-04-19T09:32:14Z` (earliest unambiguous signal, ambiguity flagged).
- **Tnow**: `2026-04-19T12:15:00Z`.
- **Window**: `[09:17:14Z, 12:15:00Z]`.

The window is nearly 3 hours wide instead of the typical 20 to 30 minutes. The 15-minute lead-in is structurally insufficient: the actual triggering deploy is 3 days outside the window. The methodology must flag this.

## Step 2: bisect the change surface

| Source | Event | Time | Detail |
|---|---|---|---|
| CI/CD | (none in window) | | Most recent `recommendations-api` deploy: `v3.8.0` at `2026-04-16T15:22:00Z`, ~70 hours before T0. **Outside the window.** |
| Terraform | (none) | | |
| IAM | (none) | | |
| Feature flags | (none) | | |
| Cron / batch | (none in window) | | |

Zero changes in the window. **This is a misleading "zero changes" signal**: it suggests an environmental cause when the actual cause is a 3-day-old deploy whose effect built up slowly. The methodology's standard "no changes → external cause" pivot would be wrong here, which is exactly why M2 escalation matters.

## Step 3: classify against the four reference paths

- **OOM**: RSS p95 climbs from baseline ~120 MB to ~485 MB over the window (limit 512 MB). GC pause durations grow from ~20 ms to ~180 ms. No `OOMKilled` events yet, but the trajectory points there within an hour. **Strong match for OOM signature** (RSS >= 90% of limit).
- **DNS**: no `SERVFAIL` / `getaddrinfo` errors. No match.
- **Cascading-failure**: no cascade signature. Upstream latency flat. No match.
- **Deploy-correlator**: no deploy in window. No match against the windowed surface (but the actual cause is a deploy 3 days outside the window).

Classification: **OOM**. The signature is strong even with the ambiguous T0.

## Step 4: confirm with three independent signals

1. **Metrics**: `rss_bytes_p95` 119 MB at 09:17 climbs to 485 MB at 12:15 (95% of 512 MB limit). GC pause p99 from 22 ms to 184 ms across the same window.
2. **Logs**: `GC pause exceeded soft threshold` warnings starting 09:32:14Z, increasing in frequency through the window.
3. **Traces**: latency tail on `recommendations-api` spans grows from p99 ~80 ms at 09:30 to p99 ~310 ms at 12:00, consistent with GC pauses stealing serving time.

Three signals, three sources. But all of them are consistent with a *slow* OOM trajectory, not a sudden one. The M2 escalation matters because the change that *caused* the leak is invisible to this investigation.

## Step 5: quantify blast radius

- **Users affected**: error rate 1.4% at Tnow, slowly climbing. Latency degradation visible to all users of `recommendations-api`.
- **Surfaces affected**: every endpoint on `recommendations-api`. Recommendation cards on home page, related items on product pages, email recommendations pipeline.
- **Business impact**: degraded recommendations quality, lower click-through rate. No hard outage yet but trajectory points to OOMKills within the hour.

## Step 6: propose mitigation before root cause

Because T0 is ambiguous and the actual triggering change is outside the window, the methodology's mitigation list has a critical addition: **re-check with a widened window before executing**.

1. **Re-check with a widened window first.** Re-run the investigation with `T0 = T0 - 4h` or wider, until the change-surface bisection returns a meaningful candidate. The 3-day-old deploy will appear. *This must precede any irreversible mitigation.*
2. **Revert the implicated change** once the widened-window investigation identifies it. The current investigation has no change to revert.
3. **Scale up** memory limit from 512 MB to 1 GB as a short-term stopgap to delay the OOMKill trajectory while step 1 runs. Acknowledged this does not address cause.
4. **Manual intervention** (rolling restart of `recommendations-api` pods to reset RSS): only if step 3 is blocked. The leak will resume; this is bridge time, not mitigation.

Recommended action: **re-run with widened window, then revert the identified change**.

## Step 7: hand off

```json
{
  "timeline": [
    {"t": "2026-04-19T09:17:14Z", "event": "Window start (15 min before earliest unambiguous signal)"},
    {"t": "2026-04-19T09:32:14Z", "event": "T0 (ambiguous): first GC pause exceeded soft threshold"},
    {"t": "2026-04-19T10:45:00Z", "event": "Error rate crosses 1%"},
    {"t": "2026-04-19T12:15:00Z", "event": "Tnow: operator-triggered investigation"}
  ],
  "ranked_hypotheses": [
    {
      "path": "OOM (slow trajectory, cause outside window)",
      "confidence": "medium (T0 ambiguous; widened-window investigation required to identify causal change)",
      "evidence": ["RSS p95 reached 95% of limit", "GC pause p99 8x baseline", "latency tail growing"]
    }
  ],
  "t0_ambiguous": true,
  "escalate_to_human": true,
  "escalation_reasons": ["M2: T0 is ambiguous; re-run with a widened window before acting on the recommended mitigation"],
  "mitigation_taken": null,
  "mitigation_recommended": "Re-run investigation with widened window (T0 - 4h or more) to identify the causal change, then revert that change.",
  "open_questions": [
    "When did the leak actually start? Likely deploy v3.8.0 at 2026-04-16T15:22:00Z, but confirm with widened-window run.",
    "Is there a per-request memory allocation chart that would distinguish a leak from organic growth?",
    "Why did no alert fire in the 3-day climb? Is the alert threshold (2% error rate) the wrong shape for a slow leak?"
  ]
}
```

## Why this is the ambiguous-T0 reference example

- It's the case where the methodology's *default* T0-picking heuristic ("first user-visible symptom") produces a window that misses the actual cause. Without M2 escalation, the methodology would confidently recommend "no change to revert, must be environmental" and be wrong.
- It exercises the slow-trajectory vs. sudden-failure distinction. The OOM signature is present but evolving over hours, not minutes; the standard 15-minute lead-in is insufficient.
- It models the gap between *what the operator can see* and *what the agent can act on*. Escalation is the safety net: the agent surfaces the partial picture, flags the gap, recommends a re-run.
