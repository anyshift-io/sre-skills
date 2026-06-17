"""
Lift eval for the sg-deceptive-reachability-auditor skill (control + treatment arms).

This started as a SCREENING harness (control only); now that SKILL.md exists, it also runs a
TREATMENT arm (same fixture, the agent additionally given SKILL.md as the methodology to
follow) and reports the lift = treatment - control per fixture. The control cells from the
original screening run are reused as-is (resume by (fixture, condition, trial)), so a lift
run only pays for the treatment trials.

Before writing a SKILL.md, the screening wanted to know
whether a cold agent (no skill, just domain expertise) finds a DEEP, buried multi-hop
SG-to-SG lateral path in a HIGH-VOLUME fleet when asked a GENERIC question -- and whether it
correctly reports NOTHING on deceptive/segmented-clean fleets. The thing under test is the
VOLUME + GENERIC-PROMPT + LONG-NEEDLE / DECEPTIVE-CLEAN condition, scoped ENTIRELY to the
model's empirically-located weak region: ~10-14 security groups where most rules are
ordinary and fine, and the real issue (when there is one) is a LONG 4-6 hop quiet
SG-reference chain from an internet-facing (or compromised-host) tier to a crown-jewel DB.
There are NO short, obvious 2-3 hop direct paths here; earlier screening showed the base
model ACING those (7.0) but MISSING a 4-hop bastion chain (2.33) and OVER-FLAGGING clean
segmented fleets (2.33). This harness replicates only that hard region.

So this runner only runs the CONTROL condition: for each fixture, N trials of a cold agent
given the raw describe-security-groups + describe-instances JSON for the WHOLE fleet and a
GENERIC "review this for security/risk problems" prompt that does NOT name lateral movement,
chains, reachability, the SG-to-SG path, or the crown-jewel target. Each output is graded
against the 7-item rubric (rubric.md) by an LLM judge, anchored to the deterministic
reference result (_deep.py, via scenarios.py) as ground truth.

The treatment arm reads SKILL.md (repo root) and prepends it as the methodology. The judge
is condition-agnostic: it grades any output against the same deterministic ground truth, so
control and treatment are scored on identical terms. print_summary reports control mean,
treatment mean, and lift per fixture.

Requirements:
- ANTHROPIC_API_KEY environment variable.
- `pip install anthropic` (the only non-stdlib dependency in the repo; isolated to tests/eval/).

Usage:
    python tests/eval/run_eval.py --trials 3
    python tests/eval/run_eval.py --trials 1 --fixtures 05,06   # smoke test
    python tests/eval/run_eval.py --trials 3 --fresh            # ignore prior results

Resume: each completed trial is persisted immediately (atomic temp+rename), and a re-run
reloads what is already on disk and fills only the missing (fixture, trial) cells. A crash,
an interrupt, or an API overload mid-run therefore never throws away completed work -- just
re-run the same command to finish. Pass --fresh to start clean.

Cost note: 7 fixtures x 3 trials, plus a judge call per output, is ~21 agent calls +
~21 judge calls = ~42 LLM calls. Expect a few dollars on Sonnet.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from pathlib import Path

try:
    from anthropic import Anthropic
except ImportError:
    print("ERROR: anthropic SDK not installed. Run: pip install anthropic", file=sys.stderr)
    sys.exit(1)

sys.path.insert(0, str(Path(__file__).parent))
from scenarios import SCENARIOS, load_fixture_text, expected_deep  # noqa: E402

DEFAULT_AGENT_MODEL = os.environ.get("EVAL_AGENT_MODEL", "claude-sonnet-4-6")
DEFAULT_JUDGE_MODEL = os.environ.get("EVAL_JUDGE_MODEL", "claude-sonnet-4-6")
MAX_TOKENS = 4096

# SKILL.md lives at the skill root (three levels up from tests/eval/).
SKILL_MD = Path(__file__).resolve().parents[2] / "SKILL.md"


def build_control_prompt(scenario: dict) -> str:
    """A GENERIC cloud-security-engineer prompt: the raw full-fleet SG + instance JSON and
    a plain "review this for problems" ask. No skill.

    This is the whole point of the screening: the prompt deliberately does NOT name lateral
    movement, reachability, the SG-to-SG reference graph, the transitive closure, the
    crown-jewel path, multi-hop chains, or the depth of any path. It does not even tell the
    agent to look for a path. It asks the agent to review the configuration, rank issues by
    severity, give the single most important fix, and state what it cannot determine. Whether
    the cold agent composes the buried LONG (4-6 hop) SG-ref needle out of a 10-14 SG haystack
    -- rather than fixating on the obvious public-CIDR exposure and stopping -- and whether it
    correctly stays quiet on the deceptive/segmented-clean fleets, is exactly what we measure.
    """
    return f"""You are a cloud security engineer doing a review of an AWS account's network configuration.

Context: {scenario['context']}

Here is the configuration, exactly as returned by the EC2 API:

{load_fixture_text(scenario)}

Review this for security and risk problems. Rank what you find by severity, give the single
most important fix, and state clearly what you cannot determine from this configuration alone.
Be specific and concrete about anything you flag."""


def build_treatment_prompt(scenario: dict, skill_md_text: str) -> str:
    """The treatment arm: the SAME generic review ask and the SAME fixture JSON as control,
    plus SKILL.md prepended as the methodology to follow. The ask is left identical so the
    only variable between the arms is the skill; the lift attributable to SKILL.md is what we
    measure. The agent is told to apply the methodology, not merely to read it."""
    return f"""You are a cloud security engineer doing a review of an AWS account's network configuration. Apply the methodology below to the configuration that follows it.

==== METHODOLOGY (SKILL.md) ====
{skill_md_text}
==== END METHODOLOGY ====

Context: {scenario['context']}

Here is the configuration, exactly as returned by the EC2 API:

{load_fixture_text(scenario)}

Apply the methodology above. Rank what you find by severity, give the single most important
fix, and state clearly what you cannot determine from this configuration alone. Be specific
and concrete about anything you flag."""


JUDGE_SYSTEM ="""You are an expert AWS / cloud-security evaluator grading a fleet security review against a 7-item rubric. Each item is binary: 1 (pass) or 0 (fail). Be strict but fair; no partial credit.

You will be given a known-good answer from a deterministic reference audit, the agent's review output, and the 7 rubric items. The agent was given a GENERIC prompt ("review this for problems") that did NOT name lateral movement, reachability, multi-hop chains, or the crown-jewel path -- reward the agent only for what it surfaces on its own, and grade substance, not phrasing.

Return JSON only (no prose), with this exact schema:

{
  "scores": [<int>, <int>, <int>, <int>, <int>, <int>, <int>],
  "notes": ["<one sentence>", ...]
}"""


def build_judge_prompt(scenario: dict, agent_output: str) -> str:
    exp = expected_deep(scenario)
    path = " -> ".join(exp["shortest_path"]) if exp["shortest_path"] else "(no path to the crown jewel)"
    hops = len(exp["shortest_path"]) - 1 if exp["shortest_path"] else 0
    return f"""FIXTURE: {scenario['id']}
CONTEXT (what the agent saw): {scenario['context']}

KNOWN-GOOD ANSWER (from the deterministic reference reachability engine):
- Findings (ground truth): {exp['codes']}  (top severity: {exp['top_severity']}; clean: {exp['clean']}; SGs: {exp['sg_count']}; SG-to-SG edges: {exp['edge_count']})
- Shortest path entry -> crown jewel: {path}  ({hops} hops)
- Blast radius (reachable tiers from the entry): {exp['blast_radius']}
- What the defect actually is: {scenario['expected_headline']}
- Correct top fix: {scenario['expected_top_fix']}
- Boundary the audit cannot cross: {scenario['expected_boundary_join']}

AGENT REVIEW OUTPUT:
{agent_output}

RUBRIC (score each 1 = pass, 0 = fail):
1. Parse: recognises UserIdGroupPairs as SG-to-SG edges (B accepting A means A can reach B), reads 0.0.0.0/0 / ::/0 as the internet entry (or the named compromised host as the entry), reads instance->SG membership, and does not skip the SG-reference arrays in the volume.
2. Surfaces the buried non-obvious issue (LOAD-BEARING): on a needle fixture, surfaces the buried LONG (4-6 hop) SG-to-SG reachable path to the crown jewel as A (the) PRIMARY finding with the hops named end to end, rather than only listing the obvious surface items (a public 0.0.0.0/0, a broad port range, a single hop) and stopping; on a clean fixture, correctly reports no real reachable path to the crown jewel.
3. Does not over-flag the benign / neutralised bait (LOAD-BEARING): does not assert a path/exposure the ground truth lacks -- not the ORPHANED deep chain in 05 as reachable, not the intended public-ALB 0.0.0.0/0 in 06 as the lateral path or headline, not the disconnected data island in 07 spliced into an internet->db route, no manufactured route on any clean fleet; and does not drown the real finding (or the clean verdict) in nitpicks about correctly-scoped tiers (bastion, monitoring, ci, ssm).
4. Composition / multi-hop (LONG): traces the SG-to-SG edges into a transitive LONG (4-6 hop) path rather than clearing each rule/SG in isolation; assembles entry -> ... -> crown jewel across many SGs end to end, not "each SG is locally fine" and stop, and not just a single hop.
5. Criticality: ranks the long path that reaches the crown jewel as the headline (critical), the blast radius as high; does not headline the directly-internet-facing front-door tier or (in 06) the loud public-ALB rule over the quiet real long path; does not invent a critical on a clean fixture.
6. Boundary: names at least one thing it cannot determine from the SG graph + membership alone, matching the ground-truth join (reachability is not exploitability: live SG membership / running hosts, route tables, NACLs, app-layer auth).
7. Recommendation: top fix matches the ground-truth fix in substance (break the offending edge/hop on the long chain, interpose a broker, or no change on a clean fixture beyond confirming the boundary).

Return JSON only."""


RETRYABLE_STATUS = {408, 409, 429, 500, 502, 503, 529}
MAX_RETRIES = 6


def _with_retries(fn, *args, **kwargs):
    """Call fn with exponential backoff on transient API errors (429/5xx/529/overloaded).

    The Anthropic SDK already retries a couple of times; this widens the window so a
    multi-minute overload spell drops far fewer trials. Re-raises on non-retryable errors
    or once retries are exhausted.

    Returns (result, call_seconds) where call_seconds is the wall-time of the SUCCESSFUL
    attempt only -- backoff sleeps and failed attempts are excluded.
    """
    delay = 2.0
    last_exc = None
    for attempt in range(MAX_RETRIES):
        try:
            t_call = time.time()
            return fn(*args, **kwargs), time.time() - t_call
        except Exception as e:  # noqa: BLE001 - inspect, then decide retryable
            status = getattr(e, "status_code", None)
            msg = str(e).lower()
            retryable = status in RETRYABLE_STATUS or "overloaded" in msg or "rate" in msg or "timeout" in msg
            if not retryable:
                raise
            last_exc = e
            if attempt < MAX_RETRIES - 1:
                time.sleep(delay)
                delay = min(delay * 2, 60.0)
    raise last_exc


def run_agent(client: Anthropic, model: str, prompt: str) -> tuple[str, float]:
    """Returns (agent_output_text, review_seconds). Seconds excludes retry backoff."""
    def _call():
        return client.messages.create(
            model=model,
            max_tokens=MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}],
        )
    resp, call_s = _with_retries(_call)
    return "".join(block.text for block in resp.content if block.type == "text"), call_s


def run_judge(client: Anthropic, model: str, scenario: dict, agent_output: str) -> dict:
    def _call():
        return client.messages.create(
            model=model,
            max_tokens=1024,
            system=JUDGE_SYSTEM,
            messages=[{"role": "user", "content": build_judge_prompt(scenario, agent_output)}],
        )
    resp, _ = _with_retries(_call)
    raw = "".join(block.text for block in resp.content if block.type == "text").strip()
    if raw.startswith("```"):
        raw = raw.split("```", 2)[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.rsplit("```", 1)[0]
    return json.loads(raw.strip())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trials", type=int, default=3, help="Trials per fixture (control only)")
    parser.add_argument("--fixtures", default="", help="Comma-separated fixture IDs (prefix match); empty = all")
    parser.add_argument("--agent-model", default=DEFAULT_AGENT_MODEL)
    parser.add_argument("--judge-model", default=DEFAULT_JUDGE_MODEL)
    parser.add_argument("--output", default="eval_results.json", help="Where to write the raw results")
    parser.add_argument("--fresh", action="store_true", help="Ignore an existing results file and start clean (default: resume/fill gaps)")
    # Which arms to run. Default is treatment only, because the control cells are already on
    # disk from the screening run and are reused as-is -- a lift run should not re-pay for them.
    # Pass --conditions control,treatment to (re)run both.
    parser.add_argument("--conditions", default="treatment",
                        help="Comma-separated arms to run: control, treatment, or both (default: treatment)")
    args = parser.parse_args()

    conditions = [c.strip() for c in args.conditions.split(",") if c.strip()]
    bad = [c for c in conditions if c not in ("control", "treatment")]
    if bad:
        print(f"ERROR: unknown condition(s) {bad}; valid: control, treatment", file=sys.stderr)
        return 2

    if "ANTHROPIC_API_KEY" not in os.environ:
        print("ERROR: ANTHROPIC_API_KEY not set", file=sys.stderr)
        return 1

    skill_md_text = ""
    if "treatment" in conditions:
        if not SKILL_MD.exists():
            print(f"ERROR: treatment arm needs a SKILL.md at {SKILL_MD}", file=sys.stderr)
            return 1
        skill_md_text = SKILL_MD.read_text()

    client = Anthropic()

    to_run = SCENARIOS
    if args.fixtures:
        filters = [f.strip() for f in args.fixtures.split(",")]
        to_run = [s for s in SCENARIOS if any(s["id"].startswith(f) for f in filters)]

    n_cells = len(to_run) * len(conditions) * args.trials
    print(f"LIFT eval [{', '.join(conditions)}]: {len(to_run)} fixtures x {len(conditions)} conditions x {args.trials} trials = {n_cells} agent calls")
    print(f"Agent model: {args.agent_model}, Judge model: {args.judge_model}\n")

    # Resume: reload any completed trials from a prior run so a re-run fills ONLY the gaps
    # (e.g. trials dropped to a transient overload, or the control arm from screening),
    # never redoing finished work. Pass --fresh to ignore an existing results file.
    results: list[dict] = []
    completed: set[tuple[str, str, int]] = set()
    out_path = Path(args.output)
    if out_path.exists() and not args.fresh:
        try:
            results = json.loads(out_path.read_text())
            completed = {(r["fixture"], r.get("condition", "control"), r["trial"]) for r in results}
            print(f"Resuming from {args.output}: {len(completed)} trials already complete; filling gaps only.\n")
        except (json.JSONDecodeError, KeyError, OSError):
            results, completed = [], set()

    for scenario in to_run:
        for condition in conditions:
            for trial in range(args.trials):
                if (scenario["id"], condition, trial) in completed:
                    continue  # already have this cell from a prior run
                t_start = time.time()
                prompt = (build_treatment_prompt(scenario, skill_md_text) if condition == "treatment"
                          else build_control_prompt(scenario))
                try:
                    agent_output, agent_s = run_agent(client, args.agent_model, prompt)  # agent_s excludes retry backoff
                    judge_result = run_judge(client, args.judge_model, scenario, agent_output)
                    score = sum(judge_result["scores"])
                except Exception as e:
                    print(f"  ERROR on {scenario['id']} [{condition}] trial {trial}: {e}", file=sys.stderr)
                    continue
                elapsed = time.time() - t_start  # agent + judge, for cost/wall-clock accounting
                results.append({
                    "fixture": scenario["id"],
                    "condition": condition,
                    "trial": trial,
                    "score": score,
                    "scores_by_item": judge_result["scores"],
                    "notes": judge_result.get("notes", []),
                    "agent_output": agent_output,
                    "agent_chars": len(agent_output),
                    "agent_s": round(agent_s, 1),
                    "elapsed_s": round(elapsed, 1),
                })
                # Crash-safe: persist after every trial via atomic temp+rename so an
                # overload-induced death never throws away completed work.
                tmp = Path(str(args.output) + ".tmp")
                tmp.write_text(json.dumps(results, indent=2))
                tmp.replace(args.output)
                print(f"  {scenario['id']:<34} | {condition:<9} | trial {trial} | score {score}/7 | review {agent_s:.0f}s", flush=True)

    Path(args.output).write_text(json.dumps(results, indent=2))
    print(f"\nRaw results: {args.output}\n")
    print_summary(results, to_run)
    return 0


def print_summary(results: list[dict], to_run: list[dict]) -> None:
    ctrl: dict[str, list[int]] = {}
    treat: dict[str, list[int]] = {}
    for r in results:
        bucket = ctrl if r.get("condition") == "control" else treat
        bucket.setdefault(r["fixture"], []).append(r["score"])

    print(f"{'Fixture':<34} {'Control':>8} {'Treat':>8} {'Lift':>8} {'Nc':>4} {'Nt':>4}")
    print("-" * 74)
    c_means: list[float] = []
    t_means: list[float] = []
    lifts: list[float] = []
    for scenario in to_run:
        cs = ctrl.get(scenario["id"], [])
        ts = treat.get(scenario["id"], [])
        if not cs and not ts:
            continue
        c = statistics.mean(cs) if cs else float("nan")
        t = statistics.mean(ts) if ts else float("nan")
        c_str = f"{c:>8.2f}" if cs else f"{'n/a':>8}"
        t_str = f"{t:>8.2f}" if ts else f"{'n/a':>8}"
        if cs and ts:
            lift = t - c
            lifts.append(lift)
            c_means.append(c)
            t_means.append(t)
            l_str = f"{lift:>+8.2f}"
            flag = "  <- treat still <5" if t < 5.0 else ("  <- no lift" if lift <= 0 else "")
        else:
            l_str = f"{'-':>8}"
            flag = ""
        print(f"{scenario['id']:<34} {c_str} {t_str} {l_str} {len(cs):>4} {len(ts):>4}{flag}")
    print("-" * 74)

    if not lifts:
        print("\nNo paired control/treatment fixtures to summarize "
              f"(control: {sum(len(v) for v in ctrl.values())} cells, "
              f"treatment: {sum(len(v) for v in treat.values())} cells).")
        return

    c_agg = statistics.mean(c_means)
    t_agg = statistics.mean(t_means)
    print(f"\nAggregate: control {c_agg:.2f}/7  ->  treatment {t_agg:.2f}/7   (lift {t_agg - c_agg:+.2f})")
    print(f"  Fixtures improved: {sum(1 for l in lifts if l > 0)} / {len(lifts)};  "
          f"treatment >= 6/7: {sum(1 for t in t_means if t >= 6.0)} / {len(t_means)};  "
          f"treatment >= 5/7: {sum(1 for t in t_means if t >= 5.0)} / {len(t_means)}")
    weakest = min(zip(t_means, [s['id'] for s in to_run if ctrl.get(s['id']) and treat.get(s['id'])]))
    print(f"  Weakest treatment fixture: {weakest[1]} at {weakest[0]:.2f}/7 "
          "(the next one to close with a SKILL.md edit)")


if __name__ == "__main__":
    sys.exit(main())
