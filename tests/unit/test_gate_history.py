from __future__ import annotations

from pathlib import Path

from kicad_mcp.resources.gate_history import GateHistory
from kicad_mcp.tools.validation import GateOutcome


def test_gate_history_records_trends_and_regressions(tmp_path: Path) -> None:
    history = GateHistory(tmp_path / "gate_history.db")
    history._init()

    history.record(GateOutcome("Schematic", "PASS", "ok"))
    history.record(GateOutcome("Schematic", "FAIL", "bad", ["wire missing"]))

    trend = history.trend("Schematic")

    assert trend[0]["status"] == "FAIL"
    assert trend[0]["issue_count"] == 1
    assert history.regression_check() == ["Schematic regressed from PASS to FAIL."]
