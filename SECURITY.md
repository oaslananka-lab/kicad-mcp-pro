# Security Policy

## Reporting A Vulnerability

Use GitHub's private vulnerability reporting flow for this repository whenever possible.
If private reporting is unavailable, contact the maintainer privately before disclosing the issue
in a public issue or discussion.

Include:

- A clear description of the issue
- Reproduction steps or a proof of concept
- Affected versions, environments, and likely impact
- Any suggested mitigation or patch guidance

Do not open public issues for undisclosed security problems.

## Supported Versions

| Version | Supported |
| ------- | --------- |
| `3.x`   | Yes       |
| `2.x`   | Security fixes only |
| `1.x`   | No        |
| `<1.0`  | No        |

## Security Gates

Required local and CI gates include Ruff, mypy strict, pytest with coverage,
Bandit, the pip-audit backed dependency audit, Gitleaks, actionlint, and zizmor.
Safety CLI is an optional additional supply-chain scan and does not replace the
enforced pip-audit gate.

Do not include secret values in issues, logs, examples, or diagnostics. CLI
diagnostics report whether tokens are configured without printing the values.

## Accepted Advisories

No accepted ignored advisories are currently active. If a future advisory must
be accepted temporarily, document the affected dependency, affected optional
extra or runtime path, mitigation, and the exact audit ignore used in CI.

## Response Expectations

- Initial acknowledgement: within 5 business days
- Follow-up status update: within 10 business days when reproduction succeeds
- Fix or mitigation target: best effort, based on severity and release timing
