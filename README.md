# sre-skills

[![License](https://img.shields.io/badge/license-Apache_2.0-blue.svg)](./LICENSE)

SRE methodology skills for AI agents. Each skill packages one reliability workflow (investigating a live incident, handing over oncall, writing a postmortem) as a self-contained module your agent loads and runs.

Built and maintained by [Anyshift](https://www.anyshift.io).

## Why use these

Your agent already writes code and runs commands. It does not know how a seasoned SRE actually works an incident: which signals to correlate first, when a deploy is the prime suspect, when to stop digging and page a human. These skills encode that methodology so the agent follows a real playbook instead of improvising.

Every skill runs end-to-end with no Anyshift account and no external credentials. The methodology, the worked examples, and the replay tests all work offline against fixtures.

## Skills

| Skill | Status | What it does |
|---|---|---|
| [`incident-investigator`](./skills/incident-investigator/) | Shipped (reference template) | Investigates a live incident: correlates deploys, traces, logs, recent IAM changes. Covers OOM, DNS, cascading-failure, deploy-correlator paths. |
| `change-impact-analyzer` | *In progress* | Pre-flight checks: IAM blast radius, drift detection, what this PR breaks. |
| `oncall-handover` | *In progress* | Reviews cert expiry, deploy state, SLO burn during oncall handover. |
| `postmortem-author` | *In progress* | Timeline reconstruction, contributing factors, impact quantification. |
| `reliability-auditor` | *In progress* | Production-readiness audit. |

Start with [`incident-investigator`](./skills/incident-investigator/): it is the shipped reference template and shows the shape every other skill follows.

## Using a skill

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
