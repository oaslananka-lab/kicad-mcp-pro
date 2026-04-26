# Phase 0 v3 Baseline

Repository base for `release/v3.0.0` is current `main` commit `8f48db2`
(`v2.4.8`). The historical v3 prompt mentions `v2.4.0`; this branch was
correctly started from the live `v2.4.8` line instead.

## Source Decisions

- Smithery remains out of scope and is not restored.
- YAML subcircuit blueprints remain the public template format.
- CI/CD publishing authority is the `oaslananka-lab/kicad-mcp-pro` GitHub org
  workflow. Personal GitHub, Azure, and GitLab remain sync/manual targets.

## Baseline Reads

- `src/kicad_mcp/tools/schematic.py`: wiring, placement, template, and
  transactional schematic-write surfaces reviewed for junction and obstacle
  fixes.
- `src/kicad_mcp/tools/pcb.py`: PCB sync, placement, ratsnest, decoupling, and
  board-write surfaces reviewed for pre-sync and auto-placement integration.
- `src/kicad_mcp/tools/validation.py`: gate composition reviewed for pre-sync
  and design-intent warning integration.
- `src/kicad_mcp/utils/placement.py`: force-directed placement reviewed for
  default post-sync use.
- `src/kicad_mcp/tools/fixers.py`: gate-to-fixer registry reviewed for
  schematic connectivity and pre-sync fix queue updates.
- `src/kicad_mcp/prompts/workflows.py`: existing prompt surface reviewed before
  adding canonical v3 workflows.
- `src/kicad_mcp/models/intent.py`: design-intent model reviewed; no breaking
  schema migration was needed for this tranche.
- `reports/plan_drift.md`: prior v2.4 drift reviewed and updated below.
- `docs/development/architecture.md`: four-layer architecture reviewed and kept
  intact.

## Verification Snapshot

- `uv run python -m ruff check src/ tests/`: green.
- `uv run python -m mypy src/kicad_mcp/`: green.
- `uv run python -m pytest tests/unit/ tests/integration/ tests/e2e/ -q --cov=kicad_mcp --cov-report=term-missing`: green, `82.25%`.
- `uv run python -c "from kicad_mcp.server import build_server; s = build_server('full'); print('ok')"`: green.

## Remaining Release Note

The v3 prompt asks for a final `>=90%` coverage target. This branch preserves a
green suite above the repository's configured `70%` gate, but the current total
coverage is `82.25%`; raising it to `90%` remains a larger test-hardening effort.
