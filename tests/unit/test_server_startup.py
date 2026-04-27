from __future__ import annotations

from pathlib import Path

from kicad_mcp.config import get_config
from kicad_mcp.connection import KiCadConnectionError
from kicad_mcp.server import KiCadFastMCP, _print_startup_diagnostics, build_server, main_callback


def test_print_startup_diagnostics_logs_expected_fields(
    sample_project: Path,
    monkeypatch,
) -> None:
    _ = sample_project
    captured: dict[str, object] = {}

    def fake_info(event: str, **kwargs: object) -> None:
        captured["event"] = event
        captured["kwargs"] = kwargs

    monkeypatch.setattr("kicad_mcp.server.find_kicad_version", lambda _cli: "10.0.1")
    monkeypatch.setattr(
        "kicad_mcp.server.get_board",
        lambda: (_ for _ in ()).throw(KiCadConnectionError("IPC not reachable")),
    )
    monkeypatch.setattr("kicad_mcp.server.logger.info", fake_info)

    _print_startup_diagnostics(get_config())

    assert captured["event"] == "startup_diagnostics"
    payload = captured["kwargs"]
    assert payload["profile"] == "full"
    assert payload["kicad_version"] == "10.0.1"
    assert payload["gate_mode"] == "release-export-only"
    assert str(payload["project_dir"]).endswith("project")
    assert str(payload["ipc_status"]).startswith("unavailable")


def test_print_startup_diagnostics_warns_when_stdio_uses_auth_token(
    sample_project: Path,
    monkeypatch,
) -> None:
    _ = sample_project
    cfg = get_config()
    cfg.transport = "stdio"
    cfg.auth_token = "secret-token"  # noqa: S105 - regression fixture
    warnings: list[str] = []

    monkeypatch.setattr("kicad_mcp.server.find_kicad_version", lambda _cli: "10.0.1")
    monkeypatch.setattr(
        "kicad_mcp.server.get_board",
        lambda: (_ for _ in ()).throw(KiCadConnectionError("IPC not reachable")),
    )
    monkeypatch.setattr(
        "kicad_mcp.server.logger.warning",
        lambda event, **_kwargs: warnings.append(event),
    )
    monkeypatch.setattr("kicad_mcp.server.logger.info", lambda *_args, **_kwargs: None)

    _print_startup_diagnostics(cfg)

    assert warnings == ["stdio_auth_token_ignored"]


def test_main_callback_runs_startup_diagnostics_before_server_run(
    sample_project: Path,
    monkeypatch,
) -> None:
    _ = sample_project
    observed: dict[str, object] = {}

    class FakeServer:
        def start_lazy_registration_background(self) -> None:
            observed["lazy_started"] = True

        def run(self, *, transport: str, mount_path: str | None = None) -> None:
            observed["transport"] = transport
            observed["mount_path"] = mount_path

    monkeypatch.setattr("kicad_mcp.server.setup_logging", lambda *_args: None)

    def fake_build_server(profile: str, *, defer_registration: bool = False) -> FakeServer:
        observed["build_profile"] = profile
        observed["defer_registration"] = defer_registration
        return FakeServer()

    monkeypatch.setattr("kicad_mcp.server.build_server", fake_build_server)

    def fake_diagnostics(cfg, *, probe_runtime: bool = True) -> None:
        observed["profile"] = cfg.profile
        observed["project_dir"] = cfg.project_dir
        observed["probe_runtime"] = probe_runtime

    monkeypatch.setattr("kicad_mcp.server._print_startup_diagnostics", fake_diagnostics)

    main_callback(
        transport="stdio",
        host="127.0.0.1",
        port=3334,
        project_dir=str(sample_project),
        log_level="INFO",
        log_format="console",
        profile="full",
        experimental=False,
    )

    assert observed["profile"] == "full"
    assert observed["build_profile"] == "full"
    assert str(observed["project_dir"]).endswith("project")
    assert observed["defer_registration"] is True
    assert observed["probe_runtime"] is False
    assert observed["lazy_started"] is True
    assert observed["transport"] == "stdio"


def test_deferred_build_registers_tools_on_first_discovery(sample_project: Path) -> None:
    _ = sample_project
    server = build_server("minimal", defer_registration=True)

    assert isinstance(server, KiCadFastMCP)
    assert server._lazy_registration_complete is False

    tool_names = {tool.name for tool in server.list_tools_sync()}

    assert server._lazy_registration_complete is True
    assert "kicad_get_version" in tool_names
    assert "export_bom" in tool_names
