# Manufacturing Export

1. Run `project_quality_gate()`.
2. If the gate is not `PASS`, stop and fix the reported blocking issues.
3. Run DRC and ERC for detailed reports.
4. Confirm the board stats and DFM summary.
5. Use low-level export tools for debugging artifacts when needed.
6. Treat `export_manufacturing_package()` as the final release step only after the
   project gate is clean.
