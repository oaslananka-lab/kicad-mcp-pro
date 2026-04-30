# Branch Protection

Rulesets are stored as code in `.github/rulesets/main.json`.

Create in the canonical repository:

```bash
gh api -X POST /repos/oaslananka/kicad-mcp-pro/rulesets --input .github/rulesets/main.json
```

Create in the lab repository:

```bash
gh api -X POST /repos/oaslananka-lab/kicad-mcp-pro/rulesets --input .github/rulesets/main.json
```

If the ruleset already exists, use the ruleset id:

```bash
gh api /repos/oaslananka-lab/kicad-mcp-pro/rulesets
gh api -X PUT /repos/oaslananka-lab/kicad-mcp-pro/rulesets/<id> --input .github/rulesets/main.json
```

The current policy requires pull requests, one review, code owner review, signed
commits, non-fast-forward protection, and these required status checks:

- `CI`
- `Security`
- `CodeQL`
- `Gitleaks`
- `Trivy (base image)`
- `Docs`

Check names must match the contexts that GitHub reports after workflow
execution. Update `.github/rulesets/main.json` when a required workflow is
renamed.
