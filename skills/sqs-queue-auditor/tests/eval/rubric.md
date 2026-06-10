# Eval rubric: `sqs-queue-auditor`

Seven binary items (1 = pass, 0 = fail). No partial credit. The judge is given the deterministic reference audit (from `_audit.py`) as ground truth.

1. **Parse.** The agent correctly reads the queue configuration: it parses the embedded `RedrivePolicy` JSON string (identifying whether a DLQ exists and the `maxReceiveCount`), and treats the string-typed second values (`VisibilityTimeout`, `MessageRetentionPeriod`) as numbers. An agent that never opens the embedded JSON, or that misreads "no RedrivePolicy" vs "DLQ present", fails.

2. **Findings.** The agent identifies the misconfiguration(s) the ground truth lists for this fixture (by substance, not by rule code: it need not say "R4", but it must describe the same defect). For the clean control, the agent reports no defect.

3. **No false positives.** The agent does not assert a material misconfiguration that the ground truth does not contain. On the clean control this is the whole game (a wildcard principal narrowed by `aws:SourceArn` must NOT be called public). On other fixtures, inventing extra critical/high defects fails this item.

4. **Criticality.** The agent ranks severity correctly: it identifies the silent-message-loss defects (DLQ-retention-ordering, poison-ages-out) as the most serious, and does not present a low-severity flag as if it were the headline. For fixtures whose only findings are soft flags, the agent correctly treats them as lower-severity.

5. **Boundary.** The agent names at least one thing it cannot determine from the queue configuration alone, matching the ground-truth join (consumer processing time, live metrics over time, the IAM identity-policy union, or producer behaviour). An agent that presents its config audit as a complete health verdict fails.

6. **Honesty on soft flags.** Where the fixture involves a flag that depends on something outside the queue (default visibility timeout, encryption-vs-data-classification, FIFO dedup-vs-producers), the agent presents it as a flag to verify rather than asserting a confirmed bug. For fixtures with no soft flag, this item passes as long as the agent does not overclaim certainty elsewhere.

7. **Recommendation.** The agent's top recommended fix matches the ground-truth fix in substance (e.g. "raise DLQ retention to the maximum", "add an aws:SourceArn condition", "raise maxReceiveCount into a sane band").

A perfect audit scores 7. The control condition (no skill) typically loses points on items 4, 5, and 6: a cold agent finds the obvious defects but tends to present a configuration read as a full health check, misses the silent-loss arithmetic, and states soft flags with unearned certainty.
