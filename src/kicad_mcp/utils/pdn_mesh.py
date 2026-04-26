"""Lightweight DC PDN mesh solver for file-based power integrity checks."""

from __future__ import annotations

from dataclasses import dataclass, field

COPPER_RESISTIVITY_OHM_M = 1.724e-8
OZ_TO_THICKNESS_MM = 0.0348


@dataclass(frozen=True)
class PdnLoad:
    """A load attached to a power net."""

    ref: str
    current_a: float
    distance_mm: float


@dataclass(frozen=True)
class PdnResult:
    """PDN voltage-drop result."""

    max_drop_mv: float
    drops_mv: dict[str, float] = field(default_factory=dict)
    violations: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)


class PdnMesh:
    """Simple resistive PDN model using copper trace resistance."""

    def solve(
        self,
        *,
        net_name: str,
        source_ref: str,
        loads: list[PdnLoad],
        trace_width_mm: float,
        copper_weight_oz: float = 1.0,
        nominal_voltage_v: float = 3.3,
        tolerance_pct: float = 5.0,
    ) -> PdnResult:
        """Estimate voltage drop for each load using a 1-D equivalent resistance."""
        if trace_width_mm <= 0:
            raise ValueError("trace_width_mm must be positive.")
        if copper_weight_oz <= 0:
            raise ValueError("copper_weight_oz must be positive.")
        thickness_mm = copper_weight_oz * OZ_TO_THICKNESS_MM
        area_m2 = (trace_width_mm / 1000.0) * (thickness_mm / 1000.0)
        limit_mv = nominal_voltage_v * (tolerance_pct / 100.0) * 1000.0
        drops: dict[str, float] = {}
        violations: list[str] = []
        recommendations: list[str] = []
        for load in loads:
            resistance_ohm = COPPER_RESISTIVITY_OHM_M * (load.distance_mm / 1000.0) / area_m2
            drop_mv = load.current_a * resistance_ohm * 1000.0
            drops[load.ref] = drop_mv
            if drop_mv > limit_mv:
                violations.append(
                    f"{load.ref} drops {drop_mv:.1f} mV on {net_name}, above {limit_mv:.1f} mV."
                )
        if violations:
            recommendations.append(
                f"Widen {net_name} traces from {trace_width_mm:.2f} mm or add copper pours "
                f"between {source_ref} and the listed loads."
            )
        return PdnResult(
            max_drop_mv=max(drops.values(), default=0.0),
            drops_mv=drops,
            violations=violations,
            recommendations=recommendations,
        )
