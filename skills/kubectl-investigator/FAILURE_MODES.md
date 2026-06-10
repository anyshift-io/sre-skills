# Failure modes: `kubectl-investigator`

This skill is wrong in predictable ways. The list below is the reason it ships with a quality bar that mandates fixture-based replay tests: every failure mode here is a regression vector and gets a test once it shows up in the wild.

## Methodology-level failure modes

### M1. Force-fitting a novel failure into the four reference paths

The skill classifies against four canonical paths in step 3 (OOM, DNS, cascading-failure, deploy-correlator). When the real failure is none of these, the agent will sometimes pick the closest path and proceed, producing a confident-looking but wrong hypothesis.

**Mitigation in the methodology**: step 4 (three independent signals) is the guard. If signals do not converge on the chosen path, the agent must explicitly mark "outside reference paths" rather than picking the closest.

**Where it breaks anyway**: when the agent has only one or two strong signals and silently treats a weak third signal as confirming. Watch for this pattern in test failures.

**Escalation rule**: if the agent has classified outside the four paths, escalate to a human before any mitigation beyond traffic-shift or feature-flag.

### M2. Wrong T0 anchors the entire investigation

Step 1 picks T0 as the first user-visible symptom. When T0 is set 20 minutes late, the change-surface bisection in step 2 misses the actual triggering change, and the agent confidently exonerates a rollout that did in fact cause the incident.

**Mitigation in the methodology**: the 15-minute lead-in in step 2 catches most cases. When the symptom built up slowly (e.g. memory leak with a slow OOM), the agent must widen the window deliberately and document the ambiguity.

**Escalation rule**: if T0 is documented as "ambiguous" in the timeline, the recommended mitigation must include a re-check after the window is widened.

### M3. Mitigation recommended past safe blast radius

Step 5 (quantify blast radius) and step 6 (propose mitigation) are deliberately ordered, but the agent can still recommend a revert that affects more surface than the incident itself if the change identified in step 2 was bundled with unrelated changes.

**Escalation rule**: any mitigation whose blast radius exceeds the incident's blast radius requires a human approver. The agent must surface the asymmetry explicitly rather than recommending the revert.

### M4. Confirmation bias on the deploy-correlator path

Temporal coincidence with a rollout is the easiest path for the agent to find and the easiest to over-trust. The rollout is often correlated but not causal (e.g. the rollout and the failure both follow from a third event like an HPA/capacity event or a ConfigMap/RBAC change applied minutes earlier).

**Mitigation in the methodology**: step 4 requires three independent signals. For the deploy-correlator path specifically, two of those signals must be drawn from the rollout diff itself (e.g. the diff touches the failing code path, the new ReplicaSet / canary shows asymmetry) rather than just from timing.

## Operational failure modes

### O1. Stale or missing change-event sources

Step 2 assumes the agent can query rollout events, RBAC audit logs, and config-change (ConfigMap/Secret) history. When one of these sources is missing or stale by more than the window, the bisection silently omits a category of changes.

**Mitigation**: the agent must enumerate which sources it queried and call out any it could not reach.

**Escalation rule**: if more than one change-event source is unavailable, escalate before recommending mitigation other than feature-flag-off.

### O2. Telemetry blackout during the incident

A serious outage can take observability with it (the metrics pipeline is itself the affected dependency). Step 4 (three independent signals) cannot be satisfied when the signal source is the thing that broke.

**Escalation rule**: telemetry blackout is an immediate escalation to a human. The skill returns the partial timeline and the hypothesis but does not recommend mitigation.

### O3. Multi-incident interleaving

When two unrelated incidents overlap in time, the change-surface bisection in step 2 returns changes for both, and the classification in step 3 may produce a hybrid hypothesis that explains neither cleanly.

**Mitigation in the methodology**: when steps 3 and 4 produce two competing hypotheses that each have strong signals, treat them as parallel incidents and run the methodology separately on each.

**Escalation rule**: if the agent identifies two parallel incidents, escalate. Humans coordinate multi-incident response better than agents.

## When to escalate to a human (summary)

Escalate immediately when **any** of the following is true:

- The failure is classified outside the four reference paths.
- T0 is documented as ambiguous.
- The recommended mitigation has broader blast radius than the incident.
- More than one change-event source is unavailable.
- Telemetry blackout prevents satisfying the three-independent-signals requirement.
- Two parallel incidents are detected.

Escalation does not mean the agent stops working. It means: surface the timeline, the partial hypothesis, the gaps, and the recommended next step. Then wait for the human.

## Implementation status

The reference implementation in `tests/_methodology.py` currently enforces:

- **M1** (outside reference paths) and the three-independent-signals guard. Covered by tests `replay_01` through `replay_11`.
- **M2** (ambiguous T0). Caller flags ambiguity via the `t0_ambiguous` parameter; the methodology escalates accordingly. Covered by `replay_06_ambiguous_t0.py`.
- **M3** (revert blast-radius asymmetry). Detected via the `bundle_size` field on deploys. Covered by `replay_07_blast_radius.py`.
- **M4** (deploy-correlator confirmation bias). Handled structurally: the classifier requires diff-touches-failing-surface evidence before classifying as deploy-correlator. Covered by `replay_08_confirmation_bias.py`.
- **Regional asymmetry**. Detected from per-region samples in metrics fixtures. Covered by `replay_10_multi_region.py`.

The operational rules (**O1** missing change-event sources, **O2** telemetry blackout, **O3** multi-incident interleaving) require richer fixture schemas to detect deterministically and are not yet enforced by the reference implementation. Contributions welcome.

## How to add a new failure mode here

When a replay test catches a misclassification, or a real-world use surfaces a new failure pattern, add it under "Methodology-level" or "Operational" with:

1. A short name (`M5`, `O4`, ...).
2. The failure shape, in one sentence.
3. Whatever the methodology already does about it (mitigation in the methodology).
4. The escalation rule for it.

Then add a regression test under `tests/` that asserts the methodology produces the correct response in the failure-mode scenario, even if the response is "escalate, do not recommend mitigation".
