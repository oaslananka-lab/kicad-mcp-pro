# Tools Reference

See the README for the complete tool list.

Recommended startup flow:

1. `kicad_get_version()`
2. `kicad_set_project()`
3. `kicad_list_tool_categories()`
4. Inspect resources such as `kicad://project/info`

## Release-Critical Tools

For agent-driven design work, these tools form the minimum safe review loop:

- `project_quality_gate()`
- `project_full_validation_loop()`
- `schematic_connectivity_gate()`
- `pcb_placement_quality_gate()`
- `pcb_transfer_quality_gate()`
- `pcb_score_placement()`
- `manufacturing_quality_gate()`
- `validate_footprints_vs_schematic()`
- `project_gate_trend()`

`export_manufacturing_package()` is a release-only tool and hard-blocks unless the
full project gate is `PASS`.

The `manufacturing` profile keeps its export surface narrow: use `get_board_stats()`
and `export_manufacturing_package()` for the gated handoff. Low-level `export_*()`
tools remain available in broader profiles such as `full` and `minimal` for debugging
or interchange output, and those direct exports do not enforce `project_quality_gate()`.

## Design Intent Tools

These tools persist the engineering assumptions that intent-aware placement checks use:

- `project_set_design_intent()`
- `project_get_design_intent()`
- `project_get_design_spec()`
- `project_infer_design_spec()`
- `project_validate_design_spec()`
- `project_generate_design_prompt()`
- `project_get_next_action()`

Current intent fields:

- connector references
- decoupling pairs
- critical nets
- power-tree references
- analog references
- digital references
- sensor-cluster references
- RF keepout regions
- manufacturer / manufacturer tier

## Schematic Safety Tools

Generated schematics should run these checks before PCB transfer:

- `sch_add_missing_junctions()` scans wires and inserts missing junctions on T-intersections.
- `sch_route_wire_between_pins()` routes around symbol bodies with A*/Z-route fallback.
- `schematic_connectivity_gate()` verifies the resulting schematic connectivity.

`pcb_sync_from_schematic(force=False, auto_place=True)` now runs the pre-sync gate by
default. Use `force=True` only for debugging known-bad intermediate states.

## Placement, Routing, and Power Tools

The default agent layout loop is:

- `pcb_sync_from_schematic(auto_place=True)` to transfer and place footprints.
- `pcb_place_decoupling_caps()` to apply common 100n/1u/10u proximity rules.
- `route_export_dsn()`, `route_autoroute_freerouting()`, and `route_import_ses()` for autorouting.
- `check_power_integrity()` for lightweight PDN mesh voltage-drop screening.

`check_power_integrity()` can also estimate simple AC PDN impedance when frequency
points and decoupling capacitor values are supplied. The result reports impedance
violations separately from DC voltage-drop violations.

## Error Responses

Tool execution failures are returned as MCP tool errors with `isError: true` and
structured content containing `error_code`, `message`, and `hint`. The text content
still includes a readable summary for clients that do not consume structured output.

## Critic Resources

The MCP resource surface mirrors the current review state so an agent can iterate safely:

- `kicad://project/quality_gate`
- `kicad://project/fix_queue`
- `kicad://project/spec`
- `kicad://project/gate_history`
- `kicad://project/next_action`
- `kicad://schematic/connectivity`
- `kicad://board/placement_quality`
- `kicad://gate/{gate_name}`

## Prompt Workflows

Built-in prompt helpers for the critic/fixer loop:

- `design_review_loop`
- `fix_blocking_issues`
- `manufacturing_release_checklist`
- `professional_circuit_design`
- `post_placement_routing`
