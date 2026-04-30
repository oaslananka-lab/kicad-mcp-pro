# Automation Policy

This repository supports automation, but human maintainers keep authority over
release, security, and public API decisions.

## Repository Roles

- `oaslananka/kicad-mcp-pro` is the canonical public project.
- `oaslananka-lab/kicad-mcp-pro` runs CI, security scanning, release
  preparation, docs deployment, and mirror automation.
- `repo-steward` is the preferred control plane for periodic repository audits,
  triage reports, and capability checks.

Development automation is maintained under the lab organization. Public package
metadata and user-facing links stay pointed at the canonical project unless a
specific CI badge or workflow link needs the lab repository.

## Agent Boundaries

Jules, Copilot coding agent, and similar coding workers may be used only on
issues that maintainers have triaged and labeled as suitable for automation.
Use `agent:candidate` for eligible issues, `agent:working` while automation is
active, and `agent:needs-human` when a maintainer decision is required.

Gemini Code Assist and review-oriented tools may comment on pull requests, but
they are not release owners.

Automation must not take ownership of:

- Secrets, token rotation, or Doppler project/config changes.
- PyPI/TestPyPI publishing or GitHub Release creation.
- OIDC or Trusted Publishing setup.
- Workflow permission escalation.
- Public API, MCP tool schema, or package ownership changes.
- Major dependency migrations or Docker base image major upgrades.
- Deployment infrastructure changes.

## Issue Labels

Use these labels to make automation decisions explicit:

- `needs:triage`: maintainer review is needed before work starts.
- `needs:human`: a maintainer decision is required.
- `risk:low`, `risk:medium`, `risk:high`: expected implementation and review
  risk.
- `agent:candidate`: a coding agent may work after maintainer triage.
- `core-runtime`: KiCad, MCP, Pydantic, Typer, or runtime dependency surface.
- `breaking-change`: public behavior, config, packaging, or workflow behavior
  may break.

Low-risk documentation, tests, CI maintenance, and small developer-tooling
changes are the normal automation candidates. Runtime behavior, release flows,
and security-sensitive changes require maintainer review even when automation
prepares the patch.

## Merge Automation

Mergify or equivalent merge automation may merge only low-risk pull requests
when all protected checks pass, required reviews are complete, and no
`needs:human`, `risk:high`, `breaking-change`, `core-runtime`, or
`type:security` label is present.

Merge automation must not publish packages, create releases, approve protected
environments, or bypass required reviews.

## Dependency Automation

Dependabot is reserved for security updates and alert-driven remediation.
Renovate owns normal version-update pull requests and groups low-risk
development tooling updates. Runtime dependencies, major updates, Docker base
image major updates, and the KiCad/MCP/Pydantic/Typer ecosystem require
Dependency Dashboard approval and maintainer review.
