from __future__ import annotations

from pathlib import Path

from kicad_mcp.config import get_config
from kicad_mcp.connection import KiCadConnectionError
from kicad_mcp.server import _print_startup_diagnostics, main_callback


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


def test_main_callback_runs_startup_diagnostics_before_server_run(
    sample_project: Path,
    monkeypatch,
) -> None:
    _ = sample_project
    observed: dict[str, object] = {}

    class FakeServer:
        def run(self, *, transport: str, mount_path: str | None = None) -> None:
            observed["transport"] = transport
            observed["mount_path"] = mount_path

    monkeypatch.setattr("kicad_mcp.server.setup_logging", lambda *_args: None)
    monkeypatch.setattr("kicad_mcp.server.build_server", lambda _profile: FakeServer())

    def fake_diagnostics(cfg) -> None:
        observed["profile"] = cfg.profile
        observed["project_dir"] = cfg.project_dir

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
    assert str(observed["project_dir"]).endswith("project")
    assert observed["transport"] == "stdio"
