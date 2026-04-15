"""Gate-to-fixer registry for the auto-fix loop.

This module describes *which* tool to call and *why*, given a gate name and
optional failure reason text.  For ``auto_applicable`` fixers it also exposes
a ``callable_import`` path so that ``project_auto_fix_loop`` can invoke the
underlying implementation directly — without going through MCP transport.

Callable convention: ``"module_path:function_name"``  where ``module_path`` is
relative to the ``kicad_mcp`` package (e.g. ``tools.schematic:run_auto_annotate``).
The function must take no required arguments and return a ``str`` summary.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class FixerAction:
    """A single recommended fix action for a failing gate.

    ``auto_applicable`` indicates the server can apply the fix without agent
    involvement (e.g., zone refill, annotation).  When ``False``, the action is
    returned as an instruction for the agent.

    ``callable_import`` — optional ``"module:function"`` string used by
    ``project_auto_fix_loop`` to call the fixer directly.
    """

    tool: str
    description: str
    args: dict[str, Any] = field(default_factory=dict)
    auto_applicable: bool = False
    callable_import: str = ""  # e.g. "tools.schematic:run_auto_annotate"


# ---------------------------------------------------------------------------
# Gate-name → ordered list of FixerActions
#
# Each entry in a fixer list is tried in order; the first matching one is used
# by project_auto_fix_loop.  Multiple entries cover different failure reasons.
# ---------------------------------------------------------------------------

GATE_FIXERS: dict[str, list[FixerAction]] = {
    "Schematic": [
        FixerAction(
            tool="sch_annotate",
            description="Annotate un-annotated schematic symbols.",
            auto_applicable=True,
            callable_import="tools.schematic:run_auto_annotate",
        ),
        FixerAction(
            tool="sch_get_bounding_boxes",
            description=(
                "Check for overlapping symbols: get current bounding boxes, "
                "then use sch_find_free_placement + sch_auto_place_symbols to fix."
            ),
        ),
        FixerAction(
            tool="run_erc",
            description="Run ERC to surface remaining schematic rule violations.",
        ),
    ],
    "Schematic connectivity": [
        FixerAction(
            tool="sch_check_power_flags",
            description="Add missing PWR_FLAG symbols to power nets.",
        ),
        FixerAction(
            tool="sch_analyze_net_compilation",
            description="Inspect net compilation errors and fix dangling labels.",
        ),
    ],
    "PCB": [
        FixerAction(
            tool="pcb_refill_zones",
            description="Refill copper zones to resolve unconnected-net violations.",
            auto_applicable=True,
            callable_import="tools.pcb:run_auto_refill_zones",
        ),
        FixerAction(
            tool="run_drc",
            description="Run DRC to identify remaining rule violations.",
        ),
    ],
    "Placement": [
        FixerAction(
            tool="pcb_place_decoupling_caps",
            description="Place decoupling capacitors near their IC partners.",
        ),
        FixerAction(
            tool="pcb_auto_place_by_schematic",
            description="Re-run schematic-guided auto-placement.",
        ),
        FixerAction(
            tool="pcb_score_placement",
            description="Score current placement to identify specific constraint failures.",
        ),
    ],
    "PCB transfer": [
        FixerAction(
            tool="pcb_sync_from_schematic",
            description="Synchronise PCB footprints from the schematic netlist.",
        ),
        FixerAction(
            tool="pcb_transfer_quality_gate",
            description="Inspect transfer-gate details to identify missing footprints.",
        ),
    ],
    "Manufacturing": [
        FixerAction(
            tool="dfm_run_manufacturer_check",
            description="Run detailed DFM check to see specific manufacturing violations.",
        ),
        FixerAction(
            tool="pcb_refill_zones",
            description="Refill zones — common cause of DFM copper-coverage failures.",
            auto_applicable=True,
            callable_import="tools.pcb:run_auto_refill_zones",
        ),
    ],
    "Footprint parity": [
        FixerAction(
            tool="pcb_sync_from_schematic",
            description="Sync missing footprints from schematic to PCB.",
        ),
        FixerAction(
            tool="validate_footprints_vs_schematic",
            description="Inspect footprint-parity details to identify mismatched refs.",
        ),
    ],
}

# Gate names that, when failing, block *all* downstream gates.
BLOCKING_GATES: frozenset[str] = frozenset({"Schematic", "Schematic connectivity"})


def fixers_for_gate(gate_name: str) -> list[FixerAction]:
    """Return the ordered fixer list for a gate, or an empty list if unknown."""
    return GATE_FIXERS.get(gate_name, [])


def auto_fix_description(gate_name: str) -> str | None:
    """Return the description of the first auto-applicable fixer, or None."""
    for action in fixers_for_gate(gate_name):
        if action.auto_applicable:
            return action.description
    return None


def first_agent_action(gate_name: str) -> FixerAction | None:
    """Return the first non-auto fixer action for the agent to take."""
    for action in fixers_for_gate(gate_name):
        if not action.auto_applicable:
            return action
    return None
