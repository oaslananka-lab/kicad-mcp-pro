from __future__ import annotations

from kicad_mcp.tools.schematic import (
    BBox,
    _deduplicate_segments,
    _detect_t_intersections,
    _insert_junctions_for_batch,
    _route_avoiding_obstacles,
)
from kicad_mcp.utils.sexpr import (
    _escape_sexpr_string,
    _extract_block,
    _sexpr_string,
    _unescape_sexpr_string,
)


def test_sexpr_escape_and_unescape_roundtrip() -> None:
    value = 'Line 1\nQuoted "value" and \\ slash'
    encoded = _sexpr_string(value)

    assert encoded == '"Line 1\\nQuoted \\"value\\" and \\\\ slash"'
    assert _unescape_sexpr_string(encoded[1:-1]) == value


def test_extract_block_ignores_parentheses_inside_strings() -> None:
    content = '(root (symbol "value(with parens)") (other "a \\"quoted\\" value"))'
    start = content.index("(symbol")

    block, length = _extract_block(content, start)

    assert block == '(symbol "value(with parens)")'
    assert length == len(block)


def test_extract_block_returns_empty_when_unbalanced() -> None:
    assert _extract_block('(symbol "unterminated"', 0) == ("", 0)


def test_escape_normalizes_carriage_returns() -> None:
    assert _escape_sexpr_string("line1\r\nline2\rline3") == "line1\\nline2\\nline3"


def test_detect_t_intersections_finds_endpoint_on_segment_midpoint() -> None:
    wires = [(0.0, 0.0, 20.0, 0.0), (10.0, -10.0, 10.0, 0.0)]

    assert _detect_t_intersections(wires) == [(10.0, 0.0)]


def test_insert_junctions_for_batch_avoids_duplicates() -> None:
    content = (
        "(kicad_sch\n"
        "\t(wire (pts (xy 0 0) (xy 20 0))\n"
        "\t\t(stroke (width 0) (type default))\n"
        '\t\t(uuid "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")\n'
        "\t)\n"
        "\t(sheet_instances)\n"
        "\t(junction (at 10 0)\n"
        "\t\t(diameter 0)\n"
        '\t\t(uuid "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")\n'
        "\t)\n"
        ")"
    )

    updated = _insert_junctions_for_batch(content, [(10.0, 0.0), (15.0, 0.0)])

    assert updated.count("(junction") == 2
    assert "(at 15 0)" in updated


def test_deduplicate_segments_removes_duplicates_and_merges_collinear_runs() -> None:
    segments = [
        (0.0, 0.0, 10.0, 0.0),
        (10.0, 0.0, 20.0, 0.0),
        (20.0, 0.0, 10.0, 0.0),
        (5.0, 5.0, 5.0, 10.0),
    ]

    assert _deduplicate_segments(segments) == [
        (0.0, 0.0, 20.0, 0.0),
        (5.0, 5.0, 5.0, 10.0),
    ]


def test_route_avoiding_obstacles_uses_z_route_when_l_shape_crosses_symbol() -> None:
    obstacle = BBox(x_min=5.0, y_min=-2.0, x_max=15.0, y_max=2.0)

    segments, warning = _route_avoiding_obstacles(
        (0.0, 0.0),
        (20.0, 0.0),
        [obstacle],
        snap_to_grid=False,
    )

    assert warning is None
    assert len(segments) >= 3
    assert any(segment[1] < -2.0 or segment[1] > 2.0 for segment in segments)
    assert not any(
        segment[1] == segment[3] == 0.0
        and max(min(segment[0], segment[2]), 5.0) <= min(max(segment[0], segment[2]), 15.0)
        for segment in segments
    )
