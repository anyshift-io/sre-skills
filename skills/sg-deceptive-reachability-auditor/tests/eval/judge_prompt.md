# Judge prompt (reference)

This file documents the judge contract. The runner (`run_eval.py`) builds the live judge
prompt programmatically from this template + the deterministic ground truth from
`scenarios.expected_deep()`. Kept here so the rubric anchoring is reviewable without
reading Python.

## System

> You are an expert AWS / cloud-security evaluator grading a fleet security review against
> a 7-item rubric. Each item is binary: 1 (pass) or 0 (fail). Be strict but fair; no partial
> credit. You will be given a known-good answer from a deterministic reference audit, the
> agent's review output, and the 7 rubric items. Return JSON only (no prose):
>
> ```json
> {"scores": [int, int, int, int, int, int, int], "notes": ["one sentence", ...]}
> ```

## User (per trial)

Provides:

- **FIXTURE** id and **CONTEXT** (the generic fleet description the agent saw).
- **KNOWN-GOOD ANSWER** from the reused deterministic engine:
  - ground-truth finding codes (P1 path / B1 blast radius / H1 hub), top severity, clean flag,
    SG count, SG-to-SG edge count;
  - the shortest path entry -> crown jewel (or "(no path)"), with its hop count;
  - the blast radius (reachable tiers from the entry);
  - the expected headline (what the buried defect actually is, or that it is clean);
  - the correct top fix; and
  - the boundary the audit cannot cross.
- **AGENT REVIEW OUTPUT** (verbatim).
- The **7 RUBRIC ITEMS** (see `rubric.md`), with the two load-bearing items called out:
  item 2 (surfaces the buried LONG 4-6 hop needle as a primary finding, hops named end to
  end, not only the obvious surface items) and item 3 (does not over-flag the benign /
  neutralised bait, esp. the orphaned deep chain in `01`, the intended public ALB in `02`,
  the disconnected data island in `03`, and the broken chain in `04`).

## Anchoring rules for the judge

- The agent prompt was GENERIC ("review this for problems"); it did NOT name lateral
  movement, reachability, multi-hop depth, or the crown-jewel path. Reward the agent only
  for what it surfaces on its own. Do not penalize phrasing; grade substance.
- The needle is the composed LONG (4-6 hop) SG-to-SG path. Reading each rule as locally
  fine and stopping, or stopping at a single hop, is an item-2 and item-4 fail even if every
  individual observation is true. Naming only some hops but not assembling the full chain to
  the crown jewel does not satisfy item 2.
- On the deceptive-clean fixtures (`01`, `02`, `03`, `04`), the correct answer is "no
  reachable path to the crown jewel." Inventing a path from an orphaned deep chain (`01`),
  headlining the intended public-ALB `0.0.0.0/0` as the lateral exposure (`02`), splicing two
  disconnected islands into one route (`03`), or treating the broken chain as reachable across
  the cut (`04`), fails items 2/3/5. The agent must reason about reachability — note that the
  front tier accepts an internal CIDR rather than the ALB SG, or that nothing references the
  ALB SG, or that the islands have no joining edge — not just list the rules.
- Match the top fix and the boundary by substance, not wording. On a clean fixture, the
  correct top fix is "no change beyond confirming the boundary," NOT a fix for a path that
  does not exist.

Return JSON only.
