# sre-skills

[![License](https://img.shields.io/badge/license-Apache_2.0-blue.svg)](./LICENSE)

SRE methodology skills for AI agents. Each skill packages one reliability workflow (investigating a live incident, handing over oncall, writing a postmortem) as a self-contained module your agent loads and runs.

Built and maintained by [Anyshift](https://www.anyshift.io).

## Why use these

Your agent already writes code and runs commands. It does not know how a seasoned SRE actually works an incident: which signals to correlate first, when a deploy is the prime suspect, when to stop digging and page a human. These skills encode that methodology so the agent follows a real playbook instead of improvising.

Every skill runs end-to-end with no Anyshift account and no external credentials. The methodology, the worked examples, and the replay tests all work offline against fixtures.

## Skills

Each skill targets one real product and one job over it: audit an IAM policy, triage a Terraform plan, resolve an S3 bucket's effective access. It does that job end-to-end, offline, against fixtures. Not a wrapper that dumps the API response back: each one carries the judgment a senior engineer applies to that one source, the thresholds and known-bad combinations that separate signal from a clean-looking config.

Then it stops. A single source only knows itself. The moment a question needs a *join* (this role to everything it can actually reach, this queue to its producers and consumers, this plan to the running infrastructure it will move) the data runs out. Each skill names exactly where that happens and what's missing, so the boundary is explicit instead of a silent wrong answer. That boundary is the same one every time: the join across resources, across sources, or across time.

| Skill | Domain | What it does |
|---|---|---|
| [`sqs-queue-auditor`](./skills/sqs-queue-auditor/) | AWS | Audits redrive/DLQ wiring, `maxReceiveCount`, retention ordering against the DLQ, and a visibility timeout left at the risky default: the queue-side config that silently drops or re-delivers messages while every attribute reads as fine. |
| [`iam-policy-auditor`](./skills/iam-policy-auditor/) | AWS | Expands wildcards to concrete permissions and flags known privilege-escalation combos (`PassRole`+`RunInstances`, `CreatePolicyVersion`, `UpdateFunctionCode`+`PassRole`) that no single statement looks guilty of. |
| `security-group-exposure-auditor` | AWS | Collapses overlapping and redundant rules into the effective allow-set, flags wide CIDRs and egress-to-anywhere, and surfaces SG-to-SG references as the lateral-movement primitive a per-rule read misses. |
| `s3-access-auditor` | AWS | Resolves *effective* public and cross-account access across Block Public Access, bucket policy, ACL, and access points: the four interacting layers that are each read wrong one at a time. |
| `terraform-plan-risk-reporter` | IaC | Ranks plan changes by blast risk, isolating destroys and force-replacements of stateful or irreplaceable resources from the harmless in-place updates they hide among. |
| `github-actions-flake-reporter` | CI/CD | Detects flaky jobs (pass-on-rerun on an unchanged SHA), clusters failures by cause, and flags duration regressions across run history, not just the last red run. |

[`sqs-queue-auditor`](./skills/sqs-queue-auditor/) (8 worked examples) and [`iam-policy-auditor`](./skills/iam-policy-auditor/) (11 worked examples) are the first two built out, each with fixture-based replay tests and a committed ablation eval; the rest are *planned*. [`kubectl-investigator`](./skills/kubectl-investigator/) stays as the methodology-shaped reference template: it shows the directory shape, the worked-example format, and the fixture-based replay tests every skill above follows.

## Using a skill

### Claude Code (recommended)

These skills ship as a plugin in Anyshift's [Claude Code](https://claude.com/claude-code) marketplace. In a Claude Code session:

```
/plugin marketplace add anyshift-io/claude-plugins
/plugin install sre-skills@anyshift
```

The skills are now loaded. The agent reaches for the right one whenever you ask something that maps to an incident, a change review, an oncall handover, a postmortem, or a reliability audit. Pull new skills and versions later with `/plugin marketplace update anyshift`.

### Any other agent

Clone the repo and point your agent at the skill you want. Each skill directory is self-contained: the methodology, the worked examples, and the fixture-based replay tests live together, so you can run the skill against the fixtures before pointing it at your own infrastructure.

```sh
git clone https://github.com/anyshift-io/sre-skills.git
```

Every skill also documents its failure modes: where it is likely to be wrong, and where the agent should escalate to a human instead of acting.

## Going deeper with Anyshift (optional)

The skills work standalone. Two optional layers add infrastructure context:

- **Anyshift MCP as a context primer.** Skills can opt into richer context from the Anyshift MCP server. When the integration is wired up for a skill, that skill publishes a measured "with vs without" delta, so the added value is explicit rather than assumed.
- **Annie, pre-loaded.** Running Anyshift's Annie agent gives you these skills already loaded, with your Terraform state, cloud inventory (AWS / GCP / Azure), and recent deploys wired in.

## What each skill guarantees

- Two worked examples drawn from real incidents or canonical scenarios.
- Fixture-based replay tests that run without external credentials.
- An explicit failure-modes section: where the skill is wrong, where the agent should escalate to a human.

## Looking for more

For a curated index of SRE skills (ours and others), MCP servers, and reading, see [anyshift-io/awesome-sre-skills](https://github.com/anyshift-io/awesome-sre-skills).

## Contributing

Contributions to the vendor-neutral skills are welcome. See [CONTRIBUTING.md](./CONTRIBUTING.md).

## License

[Apache 2.0](./LICENSE).
