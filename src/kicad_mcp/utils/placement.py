"""Force-directed placement utilities for PCB components.

Implements a spring-embedder algorithm where:
- Connected components attract each other (spring force).
- All components repel each other (Coulomb force).
- Boundary walls push components inward.

The algorithm is unit-free; callers supply coordinates in mm and receive mm back.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import NamedTuple

# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

class Point(NamedTuple):
    x: float
    y: float


@dataclass
class PlacementComponent:
    ref: str
    x: float
    y: float
    # width / height in mm (bounding box)
    w: float = 2.0
    h: float = 2.0
    fixed: bool = False


@dataclass
class PlacementNet:
    """A net connects a set of component refs."""
    name: str
    refs: list[str] = field(default_factory=list)
    # weight controls spring stiffness (higher = pulled closer)
    weight: float = 1.0


@dataclass
class ForceDirectedConfig:
    iterations: int = 300
    k_spring: float = 0.4      # spring attraction coefficient
    k_repel: float = 80.0      # Coulomb repulsion coefficient
    k_wall: float = 5.0        # boundary wall coefficient
    damping: float = 0.85      # velocity damping per step
    min_dist: float = 0.5      # minimum distance to avoid div/0
    board_w: float = 100.0     # board width (mm) — soft boundary
    board_h: float = 80.0      # board height (mm) — soft boundary
    seed: int = 42


# ---------------------------------------------------------------------------
# Core algorithm
# ---------------------------------------------------------------------------

def _centroid(comps: list[PlacementComponent], refs: list[str]) -> Point:
    xs = [c.x for c in comps if c.ref in refs]
    ys = [c.y for c in comps if c.ref in refs]
    if not xs:
        return Point(0.0, 0.0)
    return Point(sum(xs) / len(xs), sum(ys) / len(ys))


def force_directed_placement(
    components: list[PlacementComponent],
    nets: list[PlacementNet],
    cfg: ForceDirectedConfig | None = None,
) -> list[PlacementComponent]:
    """Run force-directed placement and return updated component list (copies).

    Fixed components are not moved but still exert forces on others.
    """
    if cfg is None:
        cfg = ForceDirectedConfig()

    comps = [PlacementComponent(**c.__dict__) for c in components]
    ref_idx: dict[str, int] = {c.ref: i for i, c in enumerate(comps)}

    # Velocity storage (for momentum)
    vx: list[float] = [0.0] * len(comps)
    vy: list[float] = [0.0] * len(comps)

    # Build adjacency: for each component, which other components are connected?
    adjacency: dict[str, list[tuple[str, float]]] = {c.ref: [] for c in comps}
    for net in nets:
        for r1 in net.refs:
            for r2 in net.refs:
                if r1 != r2:
                    adjacency[r1].append((r2, net.weight))

    step_size = min(cfg.board_w, cfg.board_h) * 0.05  # initial max displacement

    for iteration in range(cfg.iterations):
        # Cooling: reduce step size over time
        temperature = step_size * (1.0 - iteration / cfg.iterations) + 0.1

        fx: list[float] = [0.0] * len(comps)
        fy: list[float] = [0.0] * len(comps)

        # --- Repulsion: all pairs ---
        for i in range(len(comps)):
            for j in range(i + 1, len(comps)):
                dx = comps[i].x - comps[j].x
                dy = comps[i].y - comps[j].y
                dist = max(math.hypot(dx, dy), cfg.min_dist)
                # Overlap clearance: if bounding boxes overlap, push harder
                min_clear = (comps[i].w + comps[j].w) * 0.5 + 1.0
                effective_k = cfg.k_repel
                if dist < min_clear:
                    effective_k *= (min_clear / dist) ** 2
                force = effective_k / (dist * dist)
                nx, ny = dx / dist, dy / dist
                fx[i] += force * nx
                fy[i] += force * ny
                fx[j] -= force * nx
                fy[j] -= force * ny

        # --- Attraction: connected pairs (spring) ---
        for i, comp in enumerate(comps):
            for neighbor_ref, weight in adjacency[comp.ref]:
                neighbor_index = ref_idx.get(neighbor_ref)
                if neighbor_index is None:
                    continue
                dx = comps[neighbor_index].x - comp.x
                dy = comps[neighbor_index].y - comp.y
                dist = max(math.hypot(dx, dy), cfg.min_dist)
                force = cfg.k_spring * weight * dist
                nx, ny = dx / dist, dy / dist
                fx[i] += force * nx
                fy[i] += force * ny

        # --- Wall repulsion (soft boundary) ---
        for i, comp in enumerate(comps):
            # Left wall
            if comp.x < comp.w:
                fx[i] += cfg.k_wall / max(comp.x, 0.01)
            # Right wall
            right_gap = cfg.board_w - comp.x - comp.w
            if right_gap < comp.w:
                fx[i] -= cfg.k_wall / max(right_gap, 0.01)
            # Top wall
            if comp.y < comp.h:
                fy[i] += cfg.k_wall / max(comp.y, 0.01)
            # Bottom wall
            bottom_gap = cfg.board_h - comp.y - comp.h
            if bottom_gap < comp.h:
                fy[i] -= cfg.k_wall / max(bottom_gap, 0.01)

        # --- Integrate ---
        for i, comp in enumerate(comps):
            if comp.fixed:
                vx[i] = 0.0
                vy[i] = 0.0
                continue
            vx[i] = (vx[i] + fx[i]) * cfg.damping
            vy[i] = (vy[i] + fy[i]) * cfg.damping
            # Clamp displacement by temperature
            speed = math.hypot(vx[i], vy[i])
            if speed > temperature:
                vx[i] = vx[i] / speed * temperature
                vy[i] = vy[i] / speed * temperature
            comp.x += vx[i]
            comp.y += vy[i]
            # Hard clamp to board
            comp.x = max(comp.w * 0.5, min(cfg.board_w - comp.w * 0.5, comp.x))
            comp.y = max(comp.h * 0.5, min(cfg.board_h - comp.h * 0.5, comp.y))

    return comps


# ---------------------------------------------------------------------------
# BGA fanout geometry helpers
# ---------------------------------------------------------------------------

@dataclass
class BGABall:
    row: str      # A, B, C … (IPC row letter)
    col: int      # 1-based column index
    net: str
    x_mm: float = 0.0
    y_mm: float = 0.0


def generate_bga_fanout_plan(
    balls: list[BGABall],
    pitch_mm: float,
    via_drill_mm: float = 0.2,
    via_annular_mm: float = 0.1,
    escape_layer: str = "In1.Cu",
    strategy: str = "dog_ear",
) -> list[dict[str, object]]:
    """Return a list of via-placement descriptors for BGA fanout.

    Each descriptor has:
      ref: ball reference (e.g. "A1")
      net: net name
      ball_x, ball_y: ball center in mm
      via_x, via_y: via center in mm
      escape_layer: inner layer to fan out to
      track_width_mm: suggested track width (0.1 mm for 0.5mm pitch, 0.15 for 0.8mm+)
      dog_ear_dir: (dx, dy) unit direction of the short stub

    Strategies:
      dog_ear   — via offset diagonally ~0.5*pitch from ball center (most common)
      inline    — via directly below ball on adjacent row (for 1mm+ pitch)
    """
    track_w = 0.1 if pitch_mm <= 0.65 else 0.15

    vias: list[dict[str, object]] = []
    for ball in balls:
        bx, by = ball.x_mm, ball.y_mm

        if strategy == "dog_ear":
            # Diagonal escape direction depends on quadrant — use simple alternating pattern
            # For a real layout this would be quadrant-aware; here we use a hash-based approach
            col_odd = ball.col % 2
            row_ord = ord(ball.row[0]) - ord("A")
            row_odd = row_ord % 2
            dx = 1.0 if (col_odd ^ row_odd) == 0 else -1.0
            dy = 1.0 if row_odd == 0 else -1.0
            # Normalize diagonal
            magnitude = math.hypot(dx, dy)
            dx /= magnitude
            dy /= magnitude
            offset = pitch_mm * 0.55
            vx = bx + dx * offset
            vy = by + dy * offset
        else:  # inline
            # Place via directly to the right/left alternating by column
            dx = 1.0 if ball.col % 2 == 0 else -1.0
            vx = bx + dx * pitch_mm
            vy = by

        vias.append({
            "ref": f"{ball.row}{ball.col}",
            "net": ball.net,
            "ball_x": round(bx, 4),
            "ball_y": round(by, 4),
            "via_x": round(vx, 4),
            "via_y": round(vy, 4),
            "via_drill_mm": via_drill_mm,
            "via_annular_mm": via_annular_mm,
            "escape_layer": escape_layer,
            "track_width_mm": track_w,
            "dog_ear_dx": round(dx if strategy == "dog_ear" else 0.0, 4),
            "dog_ear_dy": round(dy if strategy == "dog_ear" else 0.0, 4),
        })

    return vias
