# Doppler Setup

This repository expects Doppler project `all`, config `main`.

## Manually Required GitHub Secret

Set exactly one GitHub secret manually in both repositories:

- `DOPPLER_TOKEN`

The token must be a read-only Doppler service token scoped to project `all`, config `main`.

Set it in:

- `oaslananka/kicad-mcp-pro`
- `oaslananka-lab/kicad-mcp-pro`

The organization repository may inherit the secret from the organization if that is easier to maintain.

Other secret names, including `DOPPLER_GITHUB_SERVICE_TOKEN`, `CODECOV_TOKEN`, `PYPI_TOKEN`, `TEST_PYPI_TOKEN`, and `SAFETY_API_KEY`, may be present as GitHub Actions secrets at runtime. Prefer projecting them into GitHub by Doppler GitHub Sync. If Doppler is temporarily incomplete, release publishing may use the GitHub repository secrets directly without printing or reading secret values.

## Doppler GitHub Sync

In the Doppler dashboard:

1. Open project `all`, config `main`.
2. Install the GitHub integration for both `oaslananka` and `oaslananka-lab`.
3. Create a sync to `oaslananka/kicad-mcp-pro` repository secrets.
4. Create a sync to `oaslananka-lab/kicad-mcp-pro` repository secrets.
5. Use replace mode so GitHub remains a projection of Doppler, not a second source of truth.

## Expected Secrets

The authoritative list for this repo is `.doppler/secrets.txt`.

Current expected names:

- `CODECOV_TOKEN`
- `DOPPLER_GITHUB_SERVICE_TOKEN`
- `PYPI_TOKEN`
- `SAFETY_API_KEY`
- `TEST_PYPI_TOKEN`

Usage:

- `CODECOV_TOKEN`: optional coverage upload token.
- `DOPPLER_GITHUB_SERVICE_TOKEN`: least-privilege GitHub service token for mirror/release synchronization only.
- `PYPI_TOKEN` and `TEST_PYPI_TOKEN`: release workflow token source when Trusted Publishing is not configured. They may be synced from Doppler or configured as GitHub repository secrets.
- `SAFETY_API_KEY`: optional authenticated Safety scan. It is not required for local default gates.

No workflow or diagnostic output should print secret values.

## Verification

```bash
bash scripts/verify_doppler_secrets.sh
```

This command requires the Doppler CLI and a local login or `DOPPLER_TOKEN`.
