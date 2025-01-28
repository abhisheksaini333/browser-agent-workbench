# Dependency profiles

The portable journal and owned portal use Python's standard library. Integration profiles pin Browser Use 0.1.18, Playwright 1.49.1, React 18.3.1 and Vite 5.4.11. Browser Use requires Python >=3.11. Its URL allowlist is not a security boundary: the workbench independently restricts every network request to the exact owned portal origin. The historical profile is an isolated compatibility fixture, not a recommendation to expose old dependencies publicly.

The later MCP adapter targets @playwright/mcp 0.0.3 (published March 25 20:08 UTC; March 26 in Asia/Kolkata). Models are external artifacts, never repository contents. Early local generation uses an audited Apache-licensed Qwen2.5 1.5B checkpoint; Qwen3 is a later optional comparison. Exact hashes and measured results belong in the execution evidence ledger.

Sources: [Browser Use metadata](https://pypi.org/pypi/browser-use/0.1.18/json), [Playwright metadata](https://pypi.org/pypi/playwright/1.49.1/json), [MCP metadata](https://registry.npmjs.org/@playwright%2fmcp).
