---
name: incident-investigator
description: Investigate a live or recent incident. Anchor the window, bisect the change surface, classify against four reference failure paths (OOM, DNS, cascading-failure, deploy-correlator), confirm the hypothesis with three independent signals, quantify blast radius, and propose mitigation before root cause. Use whenever an agent is asked "what is breaking right now", "why did X just page", "did the Y deploy cause Z", or to triage an active incident. Vendor-neutral by default; an opt-in Anyshift integration is documented separately.
---

# incident-investigator

Methodology skill for investigating a live or recent incident. Produces a timeline, a ranked set of hypotheses, a blast-radius estimate, and a recommended mitigation. Hands off cleanly to `postmortem-author` once the incident is mitigated.

## When to invoke

- An alert just fired and the agent needs to triage before paging a human.
- A user asks "what is breaking right now" or "why did service X just page".
- A deploy went out in the last hour and a metric moved; need to know whether they are linked.
- Customer impact is reported but no alert has fired; need to find the failing surface.

## The methodology, in order

The order matters. Skipping a step produces confident wrong answers.

### 1. Anchor the window

Lock two timestamps before doing anything else:

- **T0**: the trigger timestamp. Apply this order:
  1. **If an alert is provided as the trigger, T0 = alert fire time.** Use this verbatim. Do not substitute an earlier "first error in logs" timestamp just because one exists; the alert fire time is the agreed-upon coordination point for the incident.
  2. **If a customer report is the trigger, T0 = report timestamp.**
  3. **If neither exists (operator-initiated investigation, "slow all morning"), T0 = earliest unambiguous signal in the available telemetry**, and mark T0 as ambiguous (see below).
- **Tnow**: current time, or the timestamp the investigation was triggered.

Every later signal is filtered to `[T0 - 15min, Tnow]`. The 15-minute lead-in catches changes that landed just before the symptom surfaced.

**If T0 is ambiguous** (operator-triggered with no alert, or "slow all morning"-class reports), the methodology's recommended mitigation in step 6 **must begin with "re-run the investigation with a widened window"** before any irreversible action. The change identified within the original narrow window is likely incomplete; the actual causal change may sit outside it. Do not silently round and do not skip the re-run step.

### 2. Bisect the change surface

Pull every change event that overlaps the window:

- Code deploys (CI/CD events, image tags, helm releases, lambda versions).
- Infrastructure changes (Terraform applies, manual console edits, scheduled scaling events).
- IAM / permission changes (role updates, policy attachments, key rotations).
- Config / feature-flag flips.
- Dependency upgrades (lockfile changes, base image updates).
- Scheduled jobs that ran in the window (cron, batch, data migrations).

If the window has **zero** change events, treat it as a strong signal in itself: the failure is likely external (upstream provider, certificate expiry, DNS, capacity drift) rather than a self-inflicted regression.

### 3. Classify against the four reference paths

Match the failure shape to one of these four canonical paths first. They cover the majority of incidents; only branch out once they are ruled out.

| Path | Tell-tale signals | Confirming evidence |
|---|---|---|
| **OOM** | Process restart count climbing, RSS / heap at limit, `OOMKilled` events in the orchestrator, retry storm from upstream | Container exit code 137, kernel OOM in dmesg, memory metric at or above limit at T0, recent deploy that increased memory footprint |
| **DNS** | Connection failures with `NXDOMAIN` / `SERVFAIL` in logs, `getaddrinfo` errors, sudden latency on outbound calls, regional asymmetry | Resolver error counts elevated, recent change to VPC / Route53 / CoreDNS / systemd-resolved, cert / endpoint rename in the window |
| **Cascading-failure** | One dependency degrades, retry counts spike across callers, thread pools / connection pools saturate, queue depth grows | Latency increases hop-by-hop toward the root dependency, retry budget metrics, circuit-breaker state changes, 2nd-order services start failing |
| **Deploy-correlator** | Metric breaks within 5 minutes of a deploy on the failing surface, only the new version shows the symptom | Canary / blue-green split shows asymmetry, rollback restores the metric, the deploy diff touches the failing code path |

If the failure does not match any of the four, classify as **"outside reference paths"** and document why. When the classification is outside reference paths, step 6 below has a hard constraint: the top recommended action **must be "escalate to a human"**. The methodology does not have a reference path for the failure shape, so its confidence in any specific mitigation is by definition low. Mitigation options are surfaced as alternatives for the human to choose from, not as agent-executable actions.

### 4. Confirm with three independent signals

Never declare a hypothesis on one signal. Require at least three of the following, drawn from independent sources:

- Logs (application, system, orchestrator).
- Metrics (request rate, error rate, latency, saturation).
- Traces (distributed traces showing the failing hop).
- Deploy / change events.
- IAM / config / feature-flag events.
- External signals (customer reports, status pages of dependencies).

Two signals from the same source (e.g. two log lines) count as one. The independence requirement is the guard against confirmation bias.

### 5. Quantify blast radius

Before recommending action, estimate:

- **Users affected** (count or percentage of traffic).
- **Surfaces affected** (which endpoints, which regions, which customer segments).
- **Business impact** (revenue, SLO burn, contractual obligations if known).

A wrong mitigation that touches more surface than the incident itself is worse than the incident.

### 6. Propose mitigation before root cause

Mitigation comes first. Root cause comes after the bleeding stops.

**Hard constraints, in order. Check these before ranking the standard actions below:**

- **If the classification from step 3 is "outside reference paths", the top recommended action is "escalate to a human".** Hypothesis-driven options (feature-flag off, traffic-shift to a healthy replica, contact an external provider) can be listed as alternatives, but the methodology does not unilaterally recommend executing them. The human is the approver for every action when classification confidence is low.
- **If T0 was flagged as ambiguous in step 1, the top recommended action is "re-run the investigation with a widened window".** Only after that re-run identifies a fuller change surface should any irreversible mitigation (revert, IAM change, infra rollback) be recommended.
- **If the implicated change has `bundle_size > 1` (multiple changes shipped together), revert remains the top recommendation but requires explicit human approval before execution.** Surface the asymmetry explicitly: "revert reverts N changes when the incident affects only K of them".

**Standard mitigation order (applies when the constraints above do not fire):**

1. **Revert** the change identified in step 2, if one is clearly implicated and reversible.
2. **Feature-flag off** the failing code path, if a flag exists.
3. **Scale** the saturated resource, if the path is capacity-bound and not regression-bound.
4. **Traffic-shift** away from the failing region / version / shard.
5. **Manual intervention** (restart, kill stuck job) as a last resort, with explicit acknowledgement that it does not address cause.

If no safe mitigation exists even after applying the above, surface that explicitly and escalate.

### 7. Hand off

Produce a structured handoff for `postmortem-author`:

- Timeline (T0, key events, mitigation timestamp, Tresolved).
- Ranked hypotheses with the evidence supporting each.
- Mitigation taken and observed effect.
- Open questions (gaps in signals, unverified assumptions).

## Output format

The agent's final message in any invocation must include:

1. **Anchored window**: `T0 = ..., Tnow = ...`.
2. **Change surface**: bulleted list of overlapping changes, or "no changes in window".
3. **Classified path**: one of the four, or "outside reference paths" with justification.
4. **Confirming signals**: three or more, each cited with source.
5. **Blast radius**: users + surfaces + business impact.
6. **Recommended mitigation**: ordered, with explicit "do not address cause" notes where applicable.
7. **Handoff payload**: structured for `postmortem-author`.

## Worked examples

Eleven end-to-end examples are committed under `examples/`, each with fixtures and a runnable replay test.

**Reference paths** (one canonical example per path):

- [`examples/01-oom-cascade.md`](./examples/01-oom-cascade.md): OOM in a payment service triggering a retry storm from the API gateway.
- [`examples/02-dns-resolution-failure.md`](./examples/02-dns-resolution-failure.md): CoreDNS misconfiguration causing intermittent `SERVFAIL` for an internal service.
- [`examples/03-cascading-failure-retry-storm.md`](./examples/03-cascading-failure-retry-storm.md): pure cascade from an upstream DB query-plan slowdown; no code change in window.
- [`examples/04-deploy-correlator-serialization.md`](./examples/04-deploy-correlator-serialization.md): pure deploy-correlator regression (serialization change breaks downstream parsers).

**Escalation cases** (exercise the FAILURE_MODES.md rules):

- [`examples/05-outside-reference-paths-third-party-rate-limit.md`](./examples/05-outside-reference-paths-third-party-rate-limit.md): third-party API rate limit; the methodology escalates rather than force-fitting one of the four paths (M1).
- [`examples/06-ambiguous-t0-slow-burn.md`](./examples/06-ambiguous-t0-slow-burn.md): slow-burn memory leak where T0 is genuinely ambiguous; escalation (M2) recommends re-running with a widened window.
- [`examples/07-blast-radius-asymmetric-revert.md`](./examples/07-blast-radius-asymmetric-revert.md): deploy bundle of six unrelated changes; revert is the top mitigation but escalates (M3) because the revert blast radius exceeds the incident.
- [`examples/08-deploy-correlator-confirmation-bias.md`](./examples/08-deploy-correlator-confirmation-bias.md): deploy and an IAM change collide in time; the methodology rejects the deploy-correlator classification (M4 guard) because the deploy diff does not touch the failing surface.

**Edge / boundary cases**:

- [`examples/09-zero-changes-external-cert-expiry.md`](./examples/09-zero-changes-external-cert-expiry.md): zero changes in window, failure is an external TLS certificate expiry.
- [`examples/10-multi-region-asymmetry.md`](./examples/10-multi-region-asymmetry.md): same code, two regions, one fails; the methodology surfaces the per-region asymmetry as a first-class signal.
- [`examples/11-capacity-bound-organic-growth.md`](./examples/11-capacity-bound-organic-growth.md): organic traffic growth saturates capacity; the methodology recommends scaling instead of revert.

The examples mirror the seven methodology steps so contributors can see the methodology in motion, not just described.

## Replay tests

Every example has a replay test in `tests/` that runs the methodology against committed fixtures, with no external credentials. Run from the skill directory:

```bash
for t in tests/replay_*.py; do python "$t" || exit 1; done
```

The 11 tests cover the four reference paths, the FAILURE_MODES.md escalation rules (M1, M2, M3, M4), and the edge cases (zero changes, multi-region asymmetry, capacity saturation). Tests exit non-zero if the methodology produces the wrong classification, mitigation, or escalation against known-good fixtures. See [`tests/README.md`](./tests/README.md) for the fixture schema and how to add a new replay test.

## Failure modes

This skill is wrong in predictable ways. Read [`FAILURE_MODES.md`](./FAILURE_MODES.md) before relying on it for production triage. Highlights:

- The four reference paths cover most but not all incidents; novel failure shapes get force-fit if the agent does not check step 4 carefully.
- Anchoring on the wrong T0 produces a confidently wrong change-surface bisection.
- The mitigation recommendation is not a substitute for a human approver on changes with broad blast radius.

## Anyshift integration (opt-in)

The methodology above runs end-to-end with whatever telemetry, deploy event source, and IAM audit log the user already has. No Anyshift dependency.

The Anyshift MCP can act as a context primer for step 2 (change surface) by exposing a versioned resource graph that links deploys, IAM changes, and infrastructure changes to the specific resources implicated in the incident. See the per-skill README for the measured "with vs without" delta on the OOM and DNS examples (published once the integration has been exercised against the replay tests).
