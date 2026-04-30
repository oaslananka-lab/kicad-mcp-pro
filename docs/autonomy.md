# Repository Autonomy

This repository is configured for a dual-owner model.

## Ownership

- `oaslananka/kicad-mcp-pro` is the public canonical repository.
- `oaslananka-lab/kicad-mcp-pro` is the automation mirror.

Commits, branches, and tags move from canonical to the lab mirror. Release artifacts move back from the lab mirror to canonical after release publication.

## CI/CD Authority

Normal automation runs only on `oaslananka-lab/kicad-mcp-pro`:

- CI matrix
- Security scanning
- CodeQL
- Scorecard
- release automation
- documentation deploy
- image and Docker checks

The canonical repository may run only the forward mirror/sync path needed to
copy canonical refs to the lab repository. The lab mirror pulls from canonical
on a schedule and owns normal validation, release, documentation, and security
automation.

## Secrets

Doppler project `all`, config `main` is the secret source of truth. Workflows use `DOPPLER_TOKEN` to fetch runtime secrets through `doppler run`.

## Automation Boundaries

Automation does not publish releases or push tags without an explicit manual release workflow invocation and release environment approval.
