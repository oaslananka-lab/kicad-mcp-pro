# Plan Drift

## v3.0.0 Baseline

- The v3.0.0 work starts from current `main` at `8f48db2` / `v2.4.8`, not the
  historical `v2.4.0` reference in the top-level prompt.
- Smithery remains fully removed. No Smithery registry file or publish step is
  reintroduced for v3.0.0.
- Subcircuit templates remain YAML blueprints. The `.kicad_sch` template
  migration is explicitly out of this tranche.
- Release/publish authority is the `oaslananka-lab/kicad-mcp-pro` GitHub org
  workflow; personal GitHub, Azure, and GitLab are sync/manual targets.

## v3.0.0 Coverage

- The local v3 implementation is green against the repository's configured
  quality gate (`fail_under = 70`) and currently reports `82.25%` coverage.
- The requested `>=90%` coverage target is not yet satisfied. Meeting it will
  require a follow-up test-hardening tranche focused on the remaining large
  surfaces (`tools/project.py`, `tools/manufacturing.py`, `tools/schematic.py`,
  `tools/pcb.py`, `tools/signal_integrity.py`, and `utils/ngspice.py`).

## Phase 5

- The repository's bundled subcircuit templates live under `src/kicad_mcp/templates/subcircuits/` as YAML blueprints, not as standalone `.kicad_sch` files. The Phase 5 instruction to validate every template as a KiCad 10 schematic cannot be applied literally without first changing the template format.
- Byte-exact round-trip preservation for benchmark schematics is not currently satisfied by `kicad-sch-api` on the existing fixture corpus. A no-op load/save rewrites files into canonical expanded KiCad syntax, so full compliance will require either fixture canonicalization or a dedicated format-preservation layer beyond the current safe tranche.

## Release Gate

- The local validation baseline is green and the repository metadata has been
  bumped to `2.4.0`, but the branch has not been tagged, pushed, or published.
  Azure hosted validation and the manual PyPI publish stage must run outside
  this local workspace before a real `v2.4.0` release is cut.
- The full v2.4.0 master plan contains deeper fixture-backed engineering work
  that remains intentionally unsquashed into this tranche: PDN mesh solving,
  full SI/PI/EMC golden corpus, persisted gate history, per-tool metrics
  reservoirs, full sampling/elicitation roundtrips, DFM release-package signing,
  and live KiCad/FreeRouting/Docker validation.
