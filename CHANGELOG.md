# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [2.0.0] - 2026-04-13

### Added

- `kicad-sch-api`-backed schematic surface with hierarchy, connectivity, and auto-placement helpers.
- FreeRouting orchestration, DSN/SES staging, and rule-file routing tools.
- Live component search, detail, BOM pricing, stock, and alternative-part lookup.
- SPICE simulation tools with InSpice-first and ngspice fallback execution.
- Signal integrity, power integrity, EMC compliance, DFM profile, HDI/multilayer, and Git checkpoint tool families.
- Focused v2 server profiles for `schematic_only`, `pcb_only`, `high_speed`, `power`, `simulation`, and `analysis`.

### Changed

- Raised the runtime baseline to Python 3.12+.
- Replaced the legacy URL-only LCSC helpers with live component search tools in one breaking API transition.
- Hardened core runtime helpers, type safety, CLI discovery, and thread-safe board access.
- Switched tool discovery to show runtime metadata labels and added pagination/filtering to large PCB read tools.
- Bumped package, runtime, and registry metadata to `2.0.0`.

## [1.0.5] - 2026-04-13

### Changed

- Bumped project release version to 1.0.5 across package/runtime/registry metadata.

## [1.0.0] - 2026-04-13

### Added

- Public distribution and CLI branding as `kicad-mcp-pro`.
- Src-based `kicad_mcp` package layout.
- Config-driven project discovery and cross-platform KiCad CLI lookup.
- MCP resources, prompts, profiles, and refactored project/PCB/schematic/export tooling.
- Packaging, CI, docs, registry metadata, and Docker assets.
