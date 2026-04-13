"""PCB read/write tools backed by KiCad IPC."""

from __future__ import annotations

import re
import subprocess
import uuid
from collections.abc import Callable, Iterable
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Protocol, cast

import structlog
from kipy.board_types import (
    BoardCircle,
    BoardItem,
    BoardRectangle,
    BoardSegment,
    BoardText,
    Net,
    Track,
    Via,
)
from kipy.geometry import Angle, Vector2
from kipy.proto.board.board_types_pb2 import BoardLayer, ViaType
from kipy.proto.common import types as common_types
from mcp.server.fastmcp import FastMCP

from ..config import get_config
from ..connection import KiCadConnectionError, board_transaction, get_board
from ..models.pcb import (
    AddCircleInput,
    AddRectangleInput,
    AddSegmentInput,
    AddTextInput,
    AddTrackInput,
    AddViaInput,
    BulkTrackItem,
    SetBoardOutlineInput,
    SyncPcbFromSchematicInput,
)
from ..utils.layers import resolve_layer
from ..utils.units import mm_to_nm, nm_to_mm
from .schematic import parse_schematic_file

logger = structlog.get_logger(__name__)
BOARD_FILE_VERSION = "20250216"
STRING_PATTERN = r'"((?:\\.|[^"\\])*)"'
FLOAT_PATTERN = r"-?\d+(?:\.\d+)?"
PLACEMENT_MARGIN_MM = 1.27


class _PositionLike(Protocol):
    x_nm: int
    y_nm: int


class _TextValueLike(Protocol):
    value: str


class _TextFieldLike(Protocol):
    text: _TextValueLike


class _NetLike(Protocol):
    name: str


class _FootprintLike(Protocol):
    reference_field: _TextFieldLike
    value_field: _TextFieldLike
    position: Any
    layer: int


class _PadLike(Protocol):
    parent: _FootprintLike
    number: str | int
    net: _NetLike
    position: Any


class _ComponentPlacement(Protocol):
    reference: str
    value: str
    footprint: str
    x: float
    y: float
    rotation: int


def _coord_nm(point: object, axis: str) -> int:
    attr_name = f"{axis}_nm"
    value = getattr(point, attr_name) if hasattr(point, attr_name) else getattr(point, axis)
    return int(value)


def _limit[T](items: Iterable[T]) -> tuple[list[T], int]:
    cfg = get_config()
    collected = list(items)
    return collected[: cfg.max_items_per_response], len(collected)


def _find_net(name: str) -> Net:
    net = Net()
    net.name = name
    return net


def _find_footprint_by_reference(reference: str) -> _FootprintLike | None:
    board = get_board()
    for footprint in cast(Iterable[_FootprintLike], board.get_footprints()):
        if footprint.reference_field.text.value == reference:
            return footprint
    return None


def _format_selection_id(item: object) -> str:
    item_id = getattr(getattr(item, "id", None), "value", "")
    return str(item_id)[:8] + ("..." if item_id else "")


def _escape_sexpr_string(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\r\n", "\n")
        .replace("\r", "\n")
        .replace("\n", "\\n")
    )


def _sexpr_string(value: str) -> str:
    return f'"{_escape_sexpr_string(value)}"'


def _extract_block(content: str, start: int) -> tuple[str, int]:
    depth = 0
    in_string = False
    escaped = False
    for index, char in enumerate(content[start:]):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
        elif char == '"':
            in_string = True
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return content[start : start + index + 1], index + 1
    return "", 0


def _validate_board_text(content: str) -> None:
    depth = 0
    in_string = False
    escaped = False
    for char in content:
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
        elif char == '"':
            in_string = True
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth < 0:
                break
    if depth != 0 or in_string:
        raise ValueError("Refusing to write an invalid PCB file with unbalanced parentheses.")


def _default_board_text() -> str:
    return (
        "(kicad_pcb\n"
        f"\t(version {BOARD_FILE_VERSION})\n"
        '\t(generator "kicad-mcp-pro")\n'
        "\t(general)\n"
        '\t(paper "A4")\n'
        ")\n"
    )


def _get_pcb_file_for_sync() -> Path:
    cfg = get_config()
    if cfg.pcb_file is not None:
        path = cfg.pcb_file
    elif cfg.project_file is not None:
        path = cfg.project_file.with_suffix(".kicad_pcb")
        cfg.pcb_file = path
    else:
        raise ValueError(
            "No PCB file is configured. Call kicad_set_project() or set KICAD_MCP_PCB_FILE."
        )
    if not path.exists():
        path.write_text(_default_board_text(), encoding="utf-8")
    return path


def _normalize_board_content(content: str) -> str:
    stripped = content.strip()
    if not stripped or stripped == "(kicad_pcb)":
        return _default_board_text()
    if "(version" not in content:
        return _default_board_text()
    return content


def _transactional_board_write(mutator: Callable[[str], str]) -> str:
    board_file = _get_pcb_file_for_sync()
    current = _normalize_board_content(board_file.read_text(encoding="utf-8", errors="ignore"))
    updated = mutator(current)
    _validate_board_text(updated)
    with NamedTemporaryFile("w", encoding="utf-8", delete=False, dir=board_file.parent) as handle:
        handle.write(updated)
        temp_path = Path(handle.name)
    temp_path.replace(board_file)
    return str(board_file)


def _board_is_open() -> bool:
    try:
        get_board()
    except KiCadConnectionError:
        return False
    except Exception:
        return False
    return True


def _reload_board_after_file_sync() -> str:
    try:
        board = get_board()
    except KiCadConnectionError:
        return "The PCB file was updated. Reload it manually in KiCad if needed."
    except Exception:
        return "The PCB file was updated. Reload it manually in KiCad if needed."

    try:
        revert = cast(Callable[[], None], board.revert)
        revert()
        return "The PCB file was updated and KiCad was asked to reload it."
    except Exception as exc:
        logger.debug("board_reload_after_sync_failed", error=str(exc))
        return "The PCB file was updated. Reload it manually in KiCad if needed."


def _parse_root_at(block: str) -> tuple[float, float, int] | None:
    for line in block.splitlines()[:12]:
        match = re.match(
            rf"\s*\(at\s+({FLOAT_PATTERN})\s+({FLOAT_PATTERN})(?:\s+({FLOAT_PATTERN}))?\)",
            line,
        )
        if match:
            rotation = int(round(float(match.group(3) or "0")))
            return float(match.group(1)), float(match.group(2)), rotation
    return None


def _iter_blocks(content: str, keyword: str) -> Iterable[str]:
    cursor = 0
    marker = f"({keyword}"
    while cursor < len(content):
        if content[cursor:].startswith(marker):
            block, length = _extract_block(content, cursor)
            if block:
                yield block
                cursor += length
                continue
        cursor += 1


def _bbox_from_block(block: str) -> tuple[float, float]:
    xs: list[float] = []
    ys: list[float] = []

    for rect in re.finditer(
        rf"\(fp_rect\s+\(start\s+({FLOAT_PATTERN})\s+({FLOAT_PATTERN})\)\s+\(end\s+({FLOAT_PATTERN})\s+({FLOAT_PATTERN})\)",
        block,
    ):
        xs.extend([float(rect.group(1)), float(rect.group(3))])
        ys.extend([float(rect.group(2)), float(rect.group(4))])

    for line in re.finditer(
        rf"\(fp_line\s+\(start\s+({FLOAT_PATTERN})\s+({FLOAT_PATTERN})\)\s+\(end\s+({FLOAT_PATTERN})\s+({FLOAT_PATTERN})\)",
        block,
    ):
        xs.extend([float(line.group(1)), float(line.group(3))])
        ys.extend([float(line.group(2)), float(line.group(4))])

    for pad_block in _iter_blocks(block, "pad"):
        at_match = re.search(
            rf"\(at\s+({FLOAT_PATTERN})\s+({FLOAT_PATTERN})(?:\s+{FLOAT_PATTERN})?\)",
            pad_block,
        )
        size_match = re.search(rf"\(size\s+({FLOAT_PATTERN})\s+({FLOAT_PATTERN})\)", pad_block)
        if at_match and size_match:
            center_x = float(at_match.group(1))
            center_y = float(at_match.group(2))
            width = float(size_match.group(1))
            height = float(size_match.group(2))
            xs.extend([center_x - (width / 2), center_x + (width / 2)])
            ys.extend([center_y - (height / 2), center_y + (height / 2)])

    if not xs or not ys:
        return 5.08, 5.08

    width = max(max(xs) - min(xs), 1.0)
    height = max(max(ys) - min(ys), 1.0)
    return round(width, 4), round(height, 4)


def _footprint_size_from_assignment(assignment: str) -> tuple[float, float]:
    library, footprint = _split_footprint_assignment(assignment)
    path = _footprint_file(library, footprint)
    if not path.exists():
        raise FileNotFoundError(f"Footprint '{assignment}' was not found.")
    return _bbox_from_block(path.read_text(encoding="utf-8", errors="ignore"))


def _parse_board_footprint_blocks(content: str) -> dict[str, dict[str, Any]]:
    footprints: dict[str, dict[str, Any]] = {}
    cursor = 0
    while cursor < len(content):
        if content[cursor:].startswith("(footprint"):
            block, length = _extract_block(content, cursor)
            if block:
                ref_match = re.search(rf'\(property\s+"Reference"\s+{STRING_PATTERN}', block)
                name_match = re.match(rf'\(footprint\s+{STRING_PATTERN}', block.lstrip())
                if ref_match and name_match:
                    root_at = _parse_root_at(block)
                    width_mm, height_mm = _bbox_from_block(block)
                    footprints[ref_match.group(1)] = {
                        "name": name_match.group(1),
                        "block": block,
                        "start": cursor,
                        "end": cursor + length,
                        "x_mm": root_at[0] if root_at else None,
                        "y_mm": root_at[1] if root_at else None,
                        "rotation": root_at[2] if root_at else 0,
                        "width_mm": width_mm,
                        "height_mm": height_mm,
                    }
                cursor += length
                continue
        cursor += 1
    return footprints


def _append_board_blocks(content: str, blocks: list[str]) -> str:
    normalized = _normalize_board_content(content).rstrip()
    if not normalized.endswith(")"):
        raise ValueError("The active PCB file does not end with a closing parenthesis.")
    body = normalized[:-1].rstrip()
    rendered = "\n".join("\n".join("\t" + line for line in block.splitlines()) for block in blocks)
    return f"{body}\n{rendered}\n)\n"


def _replace_board_blocks(
    content: str,
    replacements: dict[str, str],
    additions: list[str],
) -> str:
    normalized = _normalize_board_content(content)
    if replacements:
        parsed = _parse_board_footprint_blocks(normalized)
        pieces: list[str] = []
        cursor = 0
        for reference, entry in sorted(
            parsed.items(),
            key=lambda item: int(cast(int, item[1]["start"])),
        ):
            start = int(entry["start"])
            end = int(entry["end"])
            pieces.append(normalized[cursor:start])
            pieces.append(replacements.get(reference, str(entry["block"])))
            cursor = end
        pieces.append(normalized[cursor:])
        normalized = "".join(pieces)
    if additions:
        normalized = _append_board_blocks(normalized, additions)
    return normalized


def _footprint_file(library: str, footprint: str) -> Path:
    cfg = get_config()
    if cfg.footprint_library_dir is None or not cfg.footprint_library_dir.exists():
        raise FileNotFoundError("No KiCad footprint library directory is configured.")
    return cfg.footprint_library_dir / f"{library}.pretty" / f"{footprint}.kicad_mod"


def _split_footprint_assignment(assignment: str) -> tuple[str, str]:
    if ":" not in assignment:
        raise ValueError(
            f"Footprint assignment '{assignment}' must use the 'Library:Footprint' format."
        )
    library, footprint = assignment.split(":", 1)
    if not library or not footprint:
        raise ValueError(
            f"Footprint assignment '{assignment}' must use the 'Library:Footprint' format."
        )
    return library, footprint


def _snap_board_coord(value: float, grid_mm: float) -> float:
    snapped = round(round(value / grid_mm) * grid_mm, 4)
    return 0.0 if abs(snapped) < 1e-6 else snapped


def _replace_property_value(block: str, field_name: str, value: str) -> str:
    pattern = re.compile(rf'(\(property\s+"{re.escape(field_name)}"\s+){STRING_PATTERN}')
    return pattern.sub(lambda match: f"{match.group(1)}{_sexpr_string(value)}", block, count=1)


def _set_pad_net_name(pad_block: str, net_name: str) -> str:
    net_pattern = re.compile(rf'(\(net\s+){STRING_PATTERN}')
    if net_pattern.search(pad_block):
        return net_pattern.sub(
            lambda match: f"{match.group(1)}{_sexpr_string(net_name)}",
            pad_block,
            count=1,
        )
    insert_at = pad_block.rfind("\n)")
    if insert_at == -1:
        insert_at = pad_block.rfind(")")
    if insert_at == -1:
        return pad_block
    return (
        pad_block[:insert_at]
        + f"\n\t\t(net {_sexpr_string(net_name)})"
        + pad_block[insert_at:]
    )


def _assign_pad_nets(block: str, pad_nets: dict[str, str]) -> str:
    rebuilt: list[str] = []
    cursor = 0
    while cursor < len(block):
        if block[cursor:].startswith("(pad"):
            pad_block, length = _extract_block(block, cursor)
            if pad_block:
                pad_match = re.match(rf'\(pad\s+{STRING_PATTERN}', pad_block.lstrip())
                if pad_match and pad_match.group(1) in pad_nets:
                    pad_block = _set_pad_net_name(pad_block, pad_nets[pad_match.group(1)])
                rebuilt.append(pad_block)
                cursor += length
                continue
        rebuilt.append(block[cursor])
        cursor += 1
    return "".join(rebuilt)


def _inject_root_placement(block: str, *, x_mm: float, y_mm: float, rotation: int) -> str:
    layer_match = re.search(r'\n(\s*\(layer\s+"[^"]+"\))', block)
    insertion = (
        f"\n\t(uuid {_sexpr_string(str(uuid.uuid4()))})"
        f"\n\t(at {x_mm:.4f} {y_mm:.4f} {rotation})"
    )
    if layer_match:
        end = layer_match.end()
        return block[:end] + insertion + block[end:]
    line_end = block.find("\n")
    if line_end == -1:
        return block[:-1] + insertion + "\n)"
    return block[:line_end] + insertion + block[line_end:]


def _render_board_footprint_block(
    footprint_assignment: str,
    *,
    reference: str,
    value: str,
    x_mm: float,
    y_mm: float,
    rotation: int,
    pad_nets: dict[str, str],
) -> str:
    library, footprint = _split_footprint_assignment(footprint_assignment)
    path = _footprint_file(library, footprint)
    if not path.exists():
        raise FileNotFoundError(f"Footprint '{footprint_assignment}' was not found.")
    block = path.read_text(encoding="utf-8", errors="ignore").strip()
    block = _replace_property_value(block, "Reference", reference)
    block = _replace_property_value(block, "Value", value)
    block = _assign_pad_nets(block, pad_nets)
    return _inject_root_placement(block, x_mm=x_mm, y_mm=y_mm, rotation=rotation)


def _placement_boxes_overlap(
    x1_mm: float,
    y1_mm: float,
    width1_mm: float,
    height1_mm: float,
    x2_mm: float,
    y2_mm: float,
    width2_mm: float,
    height2_mm: float,
    margin_mm: float,
) -> bool:
    return (
        abs(x1_mm - x2_mm) < ((width1_mm + width2_mm) / 2) + margin_mm
        and abs(y1_mm - y2_mm) < ((height1_mm + height2_mm) / 2) + margin_mm
    )


def _find_open_position(
    seed_x_mm: float,
    seed_y_mm: float,
    width_mm: float,
    height_mm: float,
    payload: SyncPcbFromSchematicInput,
    occupied: list[dict[str, float]],
) -> tuple[float, float]:
    margin_mm = PLACEMENT_MARGIN_MM

    def is_free(candidate_x_mm: float, candidate_y_mm: float) -> bool:
        return not any(
            _placement_boxes_overlap(
                candidate_x_mm,
                candidate_y_mm,
                width_mm,
                height_mm,
                box["x_mm"],
                box["y_mm"],
                box["width_mm"],
                box["height_mm"],
                margin_mm,
            )
            for box in occupied
        )

    snapped_seed = (
        _snap_board_coord(seed_x_mm, payload.grid_mm),
        _snap_board_coord(seed_y_mm, payload.grid_mm),
    )
    if is_free(*snapped_seed):
        return snapped_seed

    step_x_mm = max(
        payload.grid_mm,
        _snap_board_coord(width_mm + margin_mm, payload.grid_mm),
    )
    step_y_mm = max(
        payload.grid_mm,
        _snap_board_coord(height_mm + margin_mm, payload.grid_mm),
    )

    for radius in range(1, 25):
        candidates: list[tuple[int, int]] = []
        for delta_x in range(-radius, radius + 1):
            candidates.append((delta_x, -radius))
            candidates.append((delta_x, radius))
        for delta_y in range(-radius + 1, radius):
            candidates.append((-radius, delta_y))
            candidates.append((radius, delta_y))
        seen: set[tuple[int, int]] = set()
        for delta_x, delta_y in candidates:
            if (delta_x, delta_y) in seen:
                continue
            seen.add((delta_x, delta_y))
            candidate_x_mm = _snap_board_coord(seed_x_mm + (delta_x * step_x_mm), payload.grid_mm)
            candidate_y_mm = _snap_board_coord(seed_y_mm + (delta_y * step_y_mm), payload.grid_mm)
            if is_free(candidate_x_mm, candidate_y_mm):
                return candidate_x_mm, candidate_y_mm

    return snapped_seed


def _export_schematic_net_map() -> tuple[dict[tuple[str, str], str], str]:
    cfg = get_config()
    if cfg.sch_file is None or not cfg.sch_file.exists():
        return {}, "No schematic file is configured, so pad net names were skipped."
    if not cfg.kicad_cli.exists():
        return {}, "kicad-cli is unavailable, so pad net names were skipped."

    out_file = cfg.ensure_output_dir() / "pcb_sync.net"
    variants = [
        ["sch", "export", "netlist", "--output", str(out_file), str(cfg.sch_file)],
        ["sch", "export", "netlist", "--input", str(cfg.sch_file), "--output", str(out_file)],
    ]
    last_stderr = "unknown error"
    for variant in variants:
        result = subprocess.run(
            [str(cfg.kicad_cli), *variant],
            capture_output=True,
            text=True,
            timeout=cfg.cli_timeout,
            check=False,
        )
        if result.returncode == 0 and out_file.exists():
            content = out_file.read_text(encoding="utf-8", errors="ignore")
            return _parse_netlist_text(content), ""
        last_stderr = result.stderr.strip() or last_stderr
    return {}, f"Netlist export failed, so pad net names were skipped: {last_stderr}"


def _parse_netlist_text(content: str) -> dict[tuple[str, str], str]:
    net_map: dict[tuple[str, str], str] = {}
    cursor = 0
    while cursor < len(content):
        if content[cursor:].startswith("(net"):
            block, length = _extract_block(content, cursor)
            if block:
                name_match = re.search(rf'\(name\s+{STRING_PATTERN}\)', block)
                if name_match is not None:
                    net_name = name_match.group(1)
                    for node in re.finditer(
                        rf'\(node\s+\(ref\s+{STRING_PATTERN}\)\s+\(pin\s+{STRING_PATTERN}\)',
                        block,
                    ):
                        net_map[(node.group(1), node.group(2))] = net_name
                cursor += length
                continue
        cursor += 1
    return net_map


def _collect_schematic_components() -> tuple[list[dict[str, Any]], list[str]]:
    cfg = get_config()
    if cfg.sch_file is None or not cfg.sch_file.exists():
        raise ValueError(
            "No schematic file is configured. Call kicad_set_project() or set KICAD_MCP_SCH_FILE."
        )

    data = parse_schematic_file(cfg.sch_file)
    grouped: dict[str, dict[str, Any]] = {}
    issues: list[str] = []
    for symbol in data["symbols"]:
        reference = str(symbol["reference"])
        component = grouped.setdefault(
            reference,
            {
                "reference": reference,
                "value": str(symbol["value"]),
                "footprints": set(),
                "positions": [],
                "rotations": [],
            },
        )
        footprint = str(symbol["footprint"]).strip()
        if footprint:
            component["footprints"].add(footprint)
        component["positions"].append((float(symbol["x"]), float(symbol["y"])))
        component["rotations"].append(int(symbol["rotation"]))

    components: list[dict[str, Any]] = []
    for reference, component in grouped.items():
        footprints = cast(set[str], component["footprints"])
        if len(footprints) > 1:
            footprint_list = ", ".join(sorted(footprints))
            issues.append(
                f"{reference} has conflicting footprint assignments: {footprint_list}"
            )
            continue
        positions = cast(list[tuple[float, float]], component["positions"])
        rotations = cast(list[int], component["rotations"])
        components.append(
            {
                "reference": reference,
                "value": str(component["value"]),
                "footprint": next(iter(footprints), ""),
                "x": sum(position[0] for position in positions) / len(positions),
                "y": sum(position[1] for position in positions) / len(positions),
                "rotation": rotations[0] if rotations else 0,
            }
        )
    return components, issues


def _planned_board_positions(
    components: list[dict[str, Any]],
    payload: SyncPcbFromSchematicInput,
    occupied_boxes: list[dict[str, float]] | None = None,
) -> dict[str, tuple[float, float]]:
    if not components:
        return {}
    min_x = min(float(component["x"]) for component in components)
    min_y = min(float(component["y"]) for component in components)
    positions: dict[str, tuple[float, float]] = {}
    occupied = list(occupied_boxes or [])
    for component in sorted(
        components,
        key=lambda item: (float(item["y"]), float(item["x"]), str(item["reference"])),
    ):
        seed_x_mm = payload.origin_x_mm + ((float(component["x"]) - min_x) * payload.scale_x)
        seed_y_mm = payload.origin_y_mm + ((float(component["y"]) - min_y) * payload.scale_y)
        width_mm, height_mm = _footprint_size_from_assignment(str(component["footprint"]))
        resolved_x_mm, resolved_y_mm = _find_open_position(
            seed_x_mm,
            seed_y_mm,
            width_mm,
            height_mm,
            payload,
            occupied,
        )
        positions[str(component["reference"])] = (resolved_x_mm, resolved_y_mm)
        occupied.append(
            {
                "x_mm": resolved_x_mm,
                "y_mm": resolved_y_mm,
                "width_mm": width_mm,
                "height_mm": height_mm,
            }
        )
    return positions


def register(mcp: FastMCP) -> None:
    """Register PCB tools."""

    @mcp.tool()
    def pcb_get_board_summary() -> str:
        """Summarize the current board."""
        board = get_board()
        tracks = board.get_tracks()
        footprints = board.get_footprints()
        vias = board.get_vias()
        zones = board.get_zones()
        nets = board.get_nets(netclass_filter=None)
        shapes = board.get_shapes()
        return "\n".join(
            [
                "Board summary:",
                f"- Tracks: {len(tracks)}",
                f"- Vias: {len(vias)}",
                f"- Footprints: {len(footprints)}",
                f"- Zones: {len(zones)}",
                f"- Nets: {len(nets)}",
                f"- Shapes: {len(shapes)}",
            ]
        )

    @mcp.tool()
    def pcb_get_tracks() -> str:
        """List board tracks."""
        tracks, total = _limit(cast(Iterable[Track], get_board().get_tracks()))
        if not tracks:
            return "No tracks are present on the active board."

        lines = [f"Tracks ({total} total):"]
        for index, track in enumerate(tracks, start=1):
            lines.append(
                f"{index}. "
                f"({nm_to_mm(_coord_nm(track.start, 'x')):.2f}, "
                f"{nm_to_mm(_coord_nm(track.start, 'y')):.2f}) -> "
                f"({nm_to_mm(_coord_nm(track.end, 'x')):.2f}, "
                f"{nm_to_mm(_coord_nm(track.end, 'y')):.2f}) mm "
                f"layer={BoardLayer.Name(track.layer)} "
                f"width={nm_to_mm(track.width):.3f} mm "
                f"net={track.net.name or '(none)'} id={_format_selection_id(track)}"
            )
        return "\n".join(lines)

    @mcp.tool()
    def pcb_get_vias() -> str:
        """List board vias."""
        vias, total = _limit(cast(Iterable[Via], get_board().get_vias()))
        if not vias:
            return "No vias are present on the active board."

        lines = [f"Vias ({total} total):"]
        for index, via in enumerate(vias, start=1):
            lines.append(
                f"{index}. "
                f"({nm_to_mm(_coord_nm(via.position, 'x')):.2f}, "
                f"{nm_to_mm(_coord_nm(via.position, 'y')):.2f}) mm "
                f"diameter={nm_to_mm(via.diameter):.3f} mm "
                f"drill={nm_to_mm(via.drill_diameter):.3f} mm "
                f"net={via.net.name or '(none)'} type={ViaType.Name(via.type)}"
            )
        return "\n".join(lines)

    @mcp.tool()
    def pcb_get_footprints() -> str:
        """List board footprints."""
        footprints, total = _limit(cast(Iterable[_FootprintLike], get_board().get_footprints()))
        if not footprints:
            return "No footprints are present on the active board."

        lines = [f"Footprints ({total} total):"]
        for footprint in footprints:
            lines.append(
                f"- {footprint.reference_field.text.value} "
                f"({footprint.value_field.text.value}) "
                f"@ ({nm_to_mm(_coord_nm(footprint.position, 'x')):.2f}, "
                f"{nm_to_mm(_coord_nm(footprint.position, 'y')):.2f}) mm "
                f"layer={BoardLayer.Name(footprint.layer)} "
                f"id={_format_selection_id(footprint)}"
            )
        return "\n".join(lines)

    @mcp.tool()
    def pcb_get_nets() -> str:
        """List all board nets."""
        nets, total = _limit(cast(Iterable[Net], get_board().get_nets(netclass_filter=None)))
        if not nets:
            return "No nets are present on the active board."
        lines = [f"Nets ({total} total):"]
        lines.extend(f"- {net.name or '(unnamed)'}" for net in nets)
        return "\n".join(lines)

    @mcp.tool()
    def pcb_get_zones() -> str:
        """List all board copper zones."""
        zones, total = _limit(cast(Iterable[Any], get_board().get_zones()))
        if not zones:
            return "No zones are present on the active board."

        lines = [f"Zones ({total} total):"]
        for index, zone in enumerate(zones, start=1):
            line = f"{index}. name={zone.name or '(unnamed)'} net={zone.net.name or '(none)'}"
            if hasattr(zone, "layer"):
                line += f" layer={BoardLayer.Name(zone.layer)}"
            if hasattr(zone, "layers"):
                line += f" layers={','.join(BoardLayer.Name(layer) for layer in zone.layers)}"
            lines.append(line)
        return "\n".join(lines)

    @mcp.tool()
    def pcb_get_shapes() -> str:
        """List graphical board shapes."""
        shapes, total = _limit(cast(Iterable[Any], get_board().get_shapes()))
        if not shapes:
            return "No graphic shapes are present on the active board."
        lines = [f"Shapes ({total} total):"]
        for index, shape in enumerate(shapes, start=1):
            layer = getattr(shape, "layer", BoardLayer.BL_UNDEFINED)
            lines.append(f"{index}. {type(shape).__name__} layer={BoardLayer.Name(layer)}")
        return "\n".join(lines)

    @mcp.tool()
    def pcb_get_pads() -> str:
        """List board pads."""
        pads, total = _limit(cast(Iterable[_PadLike], get_board().get_pads()))
        if not pads:
            return "No pads are present on the active board."
        lines = [f"Pads ({total} total):"]
        for index, pad in enumerate(pads, start=1):
            lines.append(
                f"{index}. {pad.parent.reference_field.text.value}:{pad.number} "
                f"net={pad.net.name or '(none)'} "
                f"@ ({nm_to_mm(_coord_nm(pad.position, 'x')):.2f}, "
                f"{nm_to_mm(_coord_nm(pad.position, 'y')):.2f}) mm"
            )
        return "\n".join(lines)

    @mcp.tool()
    def pcb_get_layers() -> str:
        """List enabled board layers."""
        layers = get_board().get_enabled_layers()
        names = [BoardLayer.Name(layer) for layer in layers]
        return "Enabled layers:\n" + "\n".join(f"- {name}" for name in names)

    @mcp.tool()
    def pcb_get_stackup() -> str:
        """Show the current stackup."""
        stackup = get_board().get_stackup()
        lines = ["Board stackup:"]
        for layer in stackup.layers:
            material = getattr(layer, "material_name", "") or "-"
            lines.append(
                f"- {BoardLayer.Name(layer.layer)} "
                f"thickness={layer.thickness} nm "
                f"material={material}"
            )
        return "\n".join(lines)

    @mcp.tool()
    def pcb_get_selection() -> str:
        """List currently selected items in the PCB editor."""
        items = list(get_board().get_selection())
        if not items:
            return "No PCB items are currently selected."
        lines = [f"Selected items ({len(items)} total):"]
        for index, item in enumerate(items, start=1):
            lines.append(f"{index}. {type(item).__name__} id={_format_selection_id(item)}")
        return "\n".join(lines)

    @mcp.tool()
    def pcb_get_board_as_string() -> str:
        """Return the current board as a bounded S-expression string."""
        cfg = get_config()
        data = get_board().get_as_string()
        if len(data) > cfg.max_text_response_chars:
            return f"{data[: cfg.max_text_response_chars]}\n... [truncated]"
        return data

    @mcp.tool()
    def pcb_get_ratsnest() -> str:
        """Report currently unconnected board items using the latest DRC view."""
        board = get_board()
        nets = board.get_nets(netclass_filter=None)
        if not nets:
            return "The active board has no nets to analyze."
        return (
            "Live ratsnest extraction is not exposed by KiCad 10.x IPC. "
            "Run `get_unconnected_nets()` or `run_drc()` for an actionable list."
        )

    @mcp.tool()
    def pcb_get_design_rules() -> str:
        """Read the active board design rules file when available."""
        cfg = get_config()
        if cfg.project_dir is None:
            return "No active project is configured."

        matches = sorted(cfg.project_dir.glob("*.kicad_dru"))
        if not matches:
            return "No .kicad_dru design rules file was found in the active project."

        content = matches[0].read_text(encoding="utf-8", errors="ignore")
        if len(content) > cfg.max_text_response_chars:
            content = f"{content[: cfg.max_text_response_chars]}\n... [truncated]"
        return content

    @mcp.tool()
    def pcb_add_track(
        x1_mm: float,
        y1_mm: float,
        x2_mm: float,
        y2_mm: float,
        layer: str = "F_Cu",
        width_mm: float = 0.25,
        net_name: str = "",
    ) -> str:
        """Add a single track segment."""
        payload = AddTrackInput(
            x1_mm=x1_mm,
            y1_mm=y1_mm,
            x2_mm=x2_mm,
            y2_mm=y2_mm,
            layer=layer,
            width_mm=width_mm,
            net_name=net_name,
        )
        with board_transaction() as board:
            track = Track()
            track.start = Vector2.from_xy_mm(payload.x1_mm, payload.y1_mm)
            track.end = Vector2.from_xy_mm(payload.x2_mm, payload.y2_mm)
            track.layer = cast(Any, resolve_layer(payload.layer))
            track.width = mm_to_nm(payload.width_mm)
            if payload.net_name:
                track.net = _find_net(payload.net_name)
            board.create_items([track])
        return "Track added successfully."

    @mcp.tool()
    def pcb_add_tracks_bulk(tracks: list[BulkTrackItem]) -> str:
        """Add multiple tracks in a single operation."""
        validated = [BulkTrackItem.model_validate(track) for track in tracks]
        created: list[Track] = []
        for track_input in validated:
            track = Track()
            track.start = Vector2.from_xy_mm(track_input.x1, track_input.y1)
            track.end = Vector2.from_xy_mm(track_input.x2, track_input.y2)
            track.layer = cast(Any, resolve_layer(track_input.layer))
            track.width = mm_to_nm(track_input.width)
            if track_input.net:
                track.net = _find_net(track_input.net)
            created.append(track)
        with board_transaction() as board:
            board.create_items(created)
        return f"Added {len(created)} tracks."

    @mcp.tool()
    def pcb_add_via(
        x_mm: float,
        y_mm: float,
        diameter_mm: float = 0.8,
        drill_mm: float = 0.4,
        net_name: str = "",
        via_type: str = "through",
    ) -> str:
        """Add a via."""
        payload = AddViaInput(
            x_mm=x_mm,
            y_mm=y_mm,
            diameter_mm=diameter_mm,
            drill_mm=drill_mm,
            net_name=net_name,
            via_type=via_type,
        )
        type_map = {
            "through": ViaType.VT_THROUGH,
            "blind": ViaType.VT_BLIND_BURIED,
            "micro": ViaType.VT_MICRO,
        }
        via = Via()
        via.position = Vector2.from_xy_mm(payload.x_mm, payload.y_mm)
        via.diameter = mm_to_nm(payload.diameter_mm)
        via.drill_diameter = mm_to_nm(payload.drill_mm)
        via.type = cast(Any, type_map[payload.via_type])
        if payload.net_name:
            via.net = _find_net(payload.net_name)
        with board_transaction() as board:
            board.create_items([via])
        return "Via added successfully."

    @mcp.tool()
    def pcb_add_segment(
        x1_mm: float,
        y1_mm: float,
        x2_mm: float,
        y2_mm: float,
        layer: str = "Edge_Cuts",
        width_mm: float = 0.05,
    ) -> str:
        """Add a board graphic segment."""
        payload = AddSegmentInput(
            x1_mm=x1_mm,
            y1_mm=y1_mm,
            x2_mm=x2_mm,
            y2_mm=y2_mm,
            layer=layer,
            width_mm=width_mm,
        )
        segment = BoardSegment()
        segment.layer = cast(Any, resolve_layer(payload.layer))
        segment.start = Vector2.from_xy_mm(payload.x1_mm, payload.y1_mm)
        segment.end = Vector2.from_xy_mm(payload.x2_mm, payload.y2_mm)
        segment.attributes.stroke.width = mm_to_nm(payload.width_mm)
        with board_transaction() as board:
            board.create_items([segment])
        return "Graphic segment added successfully."

    @mcp.tool()
    def pcb_add_circle(
        cx_mm: float,
        cy_mm: float,
        radius_mm: float,
        layer: str = "Edge_Cuts",
        width_mm: float = 0.05,
    ) -> str:
        """Add a board graphic circle."""
        payload = AddCircleInput(
            cx_mm=cx_mm,
            cy_mm=cy_mm,
            radius_mm=radius_mm,
            layer=layer,
            width_mm=width_mm,
        )
        circle = BoardCircle()
        circle.layer = cast(Any, resolve_layer(payload.layer))
        circle.center = Vector2.from_xy_mm(payload.cx_mm, payload.cy_mm)
        circle.radius_point = Vector2.from_xy_mm(payload.cx_mm + payload.radius_mm, payload.cy_mm)
        circle.attributes.stroke.width = mm_to_nm(payload.width_mm)
        with board_transaction() as board:
            board.create_items([circle])
        return "Graphic circle added successfully."

    @mcp.tool()
    def pcb_add_rectangle(
        x1_mm: float,
        y1_mm: float,
        x2_mm: float,
        y2_mm: float,
        layer: str = "Edge_Cuts",
        width_mm: float = 0.05,
    ) -> str:
        """Add a board graphic rectangle."""
        payload = AddRectangleInput(
            x1_mm=x1_mm,
            y1_mm=y1_mm,
            x2_mm=x2_mm,
            y2_mm=y2_mm,
            layer=layer,
            width_mm=width_mm,
        )
        rectangle = BoardRectangle()
        rectangle.layer = cast(Any, resolve_layer(payload.layer))
        rectangle.top_left = Vector2.from_xy_mm(payload.x1_mm, payload.y1_mm)
        rectangle.bottom_right = Vector2.from_xy_mm(payload.x2_mm, payload.y2_mm)
        rectangle.attributes.stroke.width = mm_to_nm(payload.width_mm)
        with board_transaction() as board:
            board.create_items([rectangle])
        return "Graphic rectangle added successfully."

    @mcp.tool()
    def pcb_set_board_outline(
        width_mm: float,
        height_mm: float,
        origin_x_mm: float = 0.0,
        origin_y_mm: float = 0.0,
    ) -> str:
        """Draw a rectangular board outline on Edge.Cuts."""
        payload = SetBoardOutlineInput(
            width_mm=width_mm,
            height_mm=height_mm,
            origin_x_mm=origin_x_mm,
            origin_y_mm=origin_y_mm,
        )
        rectangle = BoardRectangle()
        rectangle.layer = BoardLayer.BL_Edge_Cuts
        rectangle.top_left = Vector2.from_xy_mm(payload.origin_x_mm, payload.origin_y_mm)
        rectangle.bottom_right = Vector2.from_xy_mm(
            payload.origin_x_mm + payload.width_mm,
            payload.origin_y_mm + payload.height_mm,
        )
        rectangle.attributes.stroke.width = mm_to_nm(0.05)
        with board_transaction() as board:
            board.create_items([rectangle])
        return "Board outline added successfully."

    @mcp.tool()
    def pcb_add_text(
        text: str,
        x_mm: float,
        y_mm: float,
        layer: str = "F_SilkS",
        size_mm: float = 1.0,
        rotation_deg: float = 0.0,
        bold: bool = False,
        italic: bool = False,
    ) -> str:
        """Add board text."""
        payload = AddTextInput(
            text=text,
            x_mm=x_mm,
            y_mm=y_mm,
            layer=layer,
            size_mm=size_mm,
            rotation_deg=rotation_deg,
            bold=bold,
            italic=italic,
        )
        text_item = BoardText()
        text_item.layer = cast(Any, resolve_layer(payload.layer))
        text_item.position = Vector2.from_xy_mm(payload.x_mm, payload.y_mm)
        text_item.value = payload.text
        text_item.attributes.size = Vector2.from_xy_mm(payload.size_mm, payload.size_mm)
        text_item.attributes.bold = payload.bold
        text_item.attributes.italic = payload.italic
        text_item.attributes.horizontal_alignment = common_types.HA_LEFT
        text_item.attributes.vertical_alignment = common_types.VA_BOTTOM
        try:
            text_item.attributes.angle = payload.rotation_deg
        except Exception as exc:
            logger.debug("board_text_angle_not_supported", error=str(exc))
        with board_transaction() as board:
            board.create_items([text_item])
        return "Board text added successfully."

    @mcp.tool()
    def pcb_delete_items(item_ids: list[str]) -> str:
        """Delete items by UUID."""
        from kipy.proto.common.types import KIID

        if not item_ids:
            return "No item IDs were supplied."
        kiids = []
        for item_id in item_ids:
            kiid = KIID()
            kiid.value = item_id
            kiids.append(kiid)
        with board_transaction() as board:
            board.remove_items_by_id(kiids)
        return f"Deleted {len(kiids)} item(s)."

    @mcp.tool()
    def pcb_save() -> str:
        """Save the active board."""
        save = cast(Callable[[], None], get_board().save)
        save()
        return "Board saved."

    @mcp.tool()
    def pcb_refill_zones() -> str:
        """Refill all copper zones."""
        get_board().refill_zones(block=True, max_poll_seconds=60.0)
        return "Zones refilled."

    @mcp.tool()
    def pcb_highlight_net(net_name: str) -> str:
        """Attempt to highlight a net in the GUI when supported."""
        if not get_config().enable_experimental_tools:
            return "Net highlighting is experimental. Enable experimental tools to try it."
        return (
            "Net highlighting is not exposed as a stable KiCad 10.x IPC operation. "
            "Use `pcb_get_nets()` to confirm "
            f"the net '{net_name}' exists and highlight it in the GUI."
        )

    @mcp.tool()
    def pcb_set_net_class(net_name: str, class_name: str) -> str:
        """Assign a net class when the runtime supports it."""
        if not get_config().enable_experimental_tools:
            return "Net class assignment is experimental. Enable experimental tools to try it."
        return (
            "Direct net class assignment is not exposed as a stable KiCad 10.x IPC operation. "
            f"Update the project rules for net '{net_name}' to use class '{class_name}'."
        )

    @mcp.tool()
    def pcb_move_footprint(
        reference: str, x_mm: float, y_mm: float, rotation_deg: float = 0.0
    ) -> str:
        """Move a footprint to an absolute location."""
        footprint = _find_footprint_by_reference(reference)
        if footprint is None:
            return f"Footprint '{reference}' was not found on the active board."

        footprint.position = Vector2.from_xy_mm(x_mm, y_mm)
        if hasattr(footprint, "angle"):
            try:
                footprint.angle = Angle.from_degrees(rotation_deg)
            except Exception as exc:
                logger.debug("footprint_angle_not_supported", error=str(exc))
        elif hasattr(footprint, "orientation"):
            try:
                footprint.orientation = rotation_deg
            except Exception as exc:
                logger.debug("footprint_orientation_not_supported", error=str(exc))
        with board_transaction() as board:
            board.update_items([cast(BoardItem, footprint)])
        return f"Moved footprint '{reference}' to ({x_mm}, {y_mm}) mm."

    @mcp.tool()
    def pcb_set_footprint_layer(reference: str, layer: str) -> str:
        """Set the footprint copper side."""
        footprint = _find_footprint_by_reference(reference)
        if footprint is None:
            return f"Footprint '{reference}' was not found on the active board."
        footprint.layer = cast(Any, resolve_layer(layer))
        with board_transaction() as board:
            board.update_items([cast(BoardItem, footprint)])
        return f"Updated footprint '{reference}' to layer '{layer}'."

    @mcp.tool()
    def pcb_sync_from_schematic(
        origin_x_mm: float = 20.0,
        origin_y_mm: float = 20.0,
        scale_x: float = 1.0,
        scale_y: float = 1.0,
        grid_mm: float = 2.54,
        allow_open_board: bool = False,
        use_net_names: bool = True,
        replace_mismatched: bool = False,
    ) -> str:
        """Sync missing PCB footprints from schematic footprint assignments.

        This is a file-based operation intended for initial board bring-up. It adds
        missing footprint instances to the `.kicad_pcb` file using schematic
        references, values, rotations, and assigned `Library:Footprint` names.
        When `replace_mismatched=True`, existing footprints with the same
        reference but the wrong footprint name are replaced in place.
        """
        payload = SyncPcbFromSchematicInput(
            origin_x_mm=origin_x_mm,
            origin_y_mm=origin_y_mm,
            scale_x=scale_x,
            scale_y=scale_y,
            grid_mm=grid_mm,
            allow_open_board=allow_open_board,
            use_net_names=use_net_names,
            replace_mismatched=replace_mismatched,
        )
        if _board_is_open() and not payload.allow_open_board:
            return (
                "Refusing file-based PCB sync while a board is open in KiCad. "
                "Close the board first, or rerun with allow_open_board=True if you want "
                "KiCad to reload the updated file from disk."
            )

        components, issues = _collect_schematic_components()
        if issues:
            return "PCB sync aborted:\n" + "\n".join(f"- {issue}" for issue in issues)
        if not components:
            return "No schematic symbols were found to sync."

        missing_assignments = [
            component["reference"]
            for component in components
            if not str(component["footprint"]).strip()
        ]
        if missing_assignments:
            return (
                "PCB sync aborted because some schematic symbols are missing "
                "footprint assignments:\n"
                + "\n".join(f"- {reference}" for reference in missing_assignments)
            )

        board_file = _get_pcb_file_for_sync()
        board_content = _normalize_board_content(
            board_file.read_text(encoding="utf-8", errors="ignore")
        )
        existing = _parse_board_footprint_blocks(board_content)
        components_by_reference = {
            str(component["reference"]): component for component in components
        }

        expected_names = {
            str(component["reference"]): _split_footprint_assignment(str(component["footprint"]))[1]
            for component in components
        }
        mismatched_references = [
            reference
            for reference, entry in existing.items()
            if reference in expected_names and entry["name"] != expected_names[reference]
        ]
        mismatches = [
            (
                f"{reference}: board has {existing[reference]['name']}, "
                f"schematic expects {expected_names[reference]}"
            )
            for reference in mismatched_references
        ]

        net_map: dict[tuple[str, str], str] = {}
        net_note = ""
        if payload.use_net_names:
            net_map, net_note = _export_schematic_net_map()

        additions: list[str] = []
        replacements: dict[str, str] = {}
        occupied_boxes = [
            {
                "x_mm": float(entry["x_mm"]),
                "y_mm": float(entry["y_mm"]),
                "width_mm": float(entry["width_mm"]),
                "height_mm": float(entry["height_mm"]),
            }
            for entry in existing.values()
            if entry["x_mm"] is not None and entry["y_mm"] is not None
        ]
        components_to_add = [
            component
            for component in components
            if str(component["reference"]) not in existing
        ]
        placements = _planned_board_positions(components_to_add, payload, occupied_boxes)

        for component in components_to_add:
            reference = str(component["reference"])
            x_mm, y_mm = placements[reference]
            pad_nets = {
                pin: name for (ref, pin), name in net_map.items() if ref == reference and name
            }
            additions.append(
                _render_board_footprint_block(
                    str(component["footprint"]),
                    reference=reference,
                    value=str(component["value"]),
                    x_mm=x_mm,
                    y_mm=y_mm,
                    rotation=int(component["rotation"]),
                    pad_nets=pad_nets,
                )
            )

        if payload.replace_mismatched:
            for reference in mismatched_references:
                component = components_by_reference[reference]
                existing_entry = existing[reference]
                x_mm = (
                    float(existing_entry["x_mm"])
                    if existing_entry["x_mm"] is not None
                    else payload.origin_x_mm
                )
                y_mm = (
                    float(existing_entry["y_mm"])
                    if existing_entry["y_mm"] is not None
                    else payload.origin_y_mm
                )
                pad_nets = {
                    pin: name
                    for (ref, pin), name in net_map.items()
                    if ref == reference and name
                }
                replacements[reference] = _render_board_footprint_block(
                    str(component["footprint"]),
                    reference=reference,
                    value=str(component["value"]),
                    x_mm=x_mm,
                    y_mm=y_mm,
                    rotation=int(existing_entry["rotation"]),
                    pad_nets=pad_nets,
                )

        if not additions and not mismatches:
            return "The PCB already contains all schematic footprint assignments."

        if additions or replacements:
            _transactional_board_write(
                lambda current: _replace_board_blocks(current, replacements, additions)
            )

        reload_note = (
            _reload_board_after_file_sync()
            if (additions or replacements) and payload.allow_open_board
            else "The PCB file was updated. Reload it manually in KiCad if needed."
            if additions or replacements
            else ""
        )

        lines = [
            f"Schematic components considered: {len(components)}",
            f"Existing PCB footprints kept: {len(existing) - len(replacements)}",
            f"New footprints added: {len(additions)}",
            f"Mismatched footprints replaced: {len(replacements)}",
        ]
        if mismatches:
            lines.append("Existing footprint mismatches:")
            lines.extend(f"- {mismatch}" for mismatch in mismatches[:20])
            if len(mismatches) > 20:
                lines.append(f"... and {len(mismatches) - 20} more")
            if not payload.replace_mismatched:
                lines.append(
                    "Rerun with replace_mismatched=True to replace those footprints in place."
                )
        if net_note:
            lines.append(net_note)
        if reload_note:
            lines.append(reload_note)
        return "\n".join(lines)
