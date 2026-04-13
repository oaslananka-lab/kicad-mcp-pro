"""Tool metadata decorators used for discovery and profile documentation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class ToolMetadata:
    """Discovery metadata attached to a public MCP tool."""

    headless_compatible: bool = False
    requires_kicad_running: bool = False
    dependencies: tuple[str, ...] = ()


_TOOL_METADATA: dict[str, ToolMetadata] = {}


def _merge_metadata(
    current: ToolMetadata,
    *,
    headless_compatible: bool | None = None,
    requires_kicad_running: bool | None = None,
    dependency: str | None = None,
) -> ToolMetadata:
    dependencies = list(current.dependencies)
    if dependency and dependency not in dependencies:
        dependencies.append(dependency)
    return ToolMetadata(
        headless_compatible=(
            current.headless_compatible
            if headless_compatible is None
            else current.headless_compatible or headless_compatible
        ),
        requires_kicad_running=(
            current.requires_kicad_running
            if requires_kicad_running is None
            else current.requires_kicad_running or requires_kicad_running
        ),
        dependencies=tuple(dependencies),
    )


def _apply_metadata[**P, R](
    func: Callable[P, R],
    *,
    headless_compatible: bool | None = None,
    requires_kicad_running: bool | None = None,
    dependency: str | None = None,
) -> Callable[P, R]:
    current = _TOOL_METADATA.get(func.__name__, ToolMetadata())
    updated = _merge_metadata(
        current,
        headless_compatible=headless_compatible,
        requires_kicad_running=requires_kicad_running,
        dependency=dependency,
    )
    _TOOL_METADATA[func.__name__] = updated
    return func


def headless_compatible[**P, R](func: Callable[P, R]) -> Callable[P, R]:
    """Mark a tool as usable without a live KiCad IPC session."""
    return _apply_metadata(func, headless_compatible=True)


def requires_kicad_running[**P, R](func: Callable[P, R]) -> Callable[P, R]:
    """Mark a tool as requiring an active KiCad IPC connection."""
    return _apply_metadata(func, requires_kicad_running=True)


def requires_dependency(name: str) -> Callable[[Callable[..., object]], Callable[..., object]]:
    """Mark a tool as requiring an optional dependency family."""

    def decorator[**P, R](func: Callable[P, R]) -> Callable[P, R]:
        return _apply_metadata(func, dependency=name)

    return decorator


def get_tool_metadata(tool_name: str) -> ToolMetadata | None:
    """Return discovery metadata for a registered tool name."""
    return _TOOL_METADATA.get(tool_name)
