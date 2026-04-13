from __future__ import annotations

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
