from __future__ import annotations

import pytest

from kicad_mcp.server import build_server
from kicad_mcp.tools.router import PROFILE_CATEGORIES, available_profiles, categories_for_profile
from tests.conftest import call_tool_text


def test_available_profiles_include_v2_surface() -> None:
    expected = {
        "full",
        "minimal",
        "schematic_only",
        "pcb_only",
        "manufacturing",
        "high_speed",
        "power",
        "simulation",
        "analysis",
        "pcb",
        "schematic",
    }

    assert expected.issubset(set(available_profiles()))
    assert categories_for_profile("analysis") == PROFILE_CATEGORIES["analysis"]
    assert categories_for_profile("unknown-profile") == PROFILE_CATEGORIES["full"]


@pytest.mark.anyio
async def test_tool_category_output_shows_runtime_metadata() -> None:
    server = build_server("full")

    routing = await call_tool_text(server, "kicad_get_tools_in_category", {"category": "routing"})
    pcb_read = await call_tool_text(server, "kicad_get_tools_in_category", {"category": "pcb_read"})

    assert "route_autoroute_freerouting [HEADLESS / REQUIRES:freerouting]" in routing
    assert "pcb_get_tracks [REQUIRES_KICAD]" in pcb_read
