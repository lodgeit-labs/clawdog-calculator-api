"""Service layer for the calculator-API.

Holds bridge-layer logic that is NOT route-handler glue. Per Lesson #36, route
handlers stay thin and logic lives here. Phase 4 (`mut-2026-05-29-mc08` Option-A
PR 2) introduces this package alongside the MCP route surface; the existing
`api.lib.*` modules remain for shared utilities (advisory boundary, rate-table
resolver).
"""
