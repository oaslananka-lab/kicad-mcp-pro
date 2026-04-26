# v3.0.0 Implementation Summary

## Changed

- Added schematic T-intersection detection, missing-junction insertion,
  duplicate wire removal, and collinear wire merging.
- Added symbol-obstacle-aware schematic routing with A* first, Z-route fallback,
  and direct-route warning fallback.
- Added a pre-sync gate and backward-compatible
  `pcb_sync_from_schematic(force=False, auto_place=True)` behavior.
- Added default post-sync force-directed placement, ratsnest-derived placement
  net weighting helpers, and decoupling-cap proximity reports.
- Added `project_full_validation_loop()`, `project_gate_trend()`,
  `professional_circuit_design`, and `post_placement_routing`.
- Added a lightweight PDN mesh solver, `check_power_integrity()`, SQLite-backed
  gate history, and ten YAML subcircuit templates.

## Tests Added

- Junction detection, junction insertion, wire deduplication, and obstacle
  routing unit coverage.
- Schematic A* router unit coverage.
- PDN mesh and gate-history unit coverage.
- PCB sync force override, decoupling report, and placement net-weight tests.

## Verification

- Ruff: green.
- Mypy: green.
- Unit/integration/e2e pytest suite: green.
- Coverage: `82.25%`.
- `build_server('full')`: green.

## Risks

- The requested `>=90%` coverage target is not yet met.
- Live KiCad GUI, Docker FreeRouting, and external publish workflows still need
  hosted/environment-specific validation before public release.
