# Dependency profiles

The portable journal and owned portal use Python's standard library. Integration profiles pin Browser Use 0.1.18, Playwright 1.49.1, React 18.3.1 and Vite 5.4.11. Browser Use requires Python >=3.11. Its URL allowlist is not a security boundary: the workbench independently restricts every network request to the exact owned portal origin. The historical profile is an isolated compatibility fixture, not a recommendation to expose old dependencies publicly.

The later MCP adapter targets @playwright/mcp 0.0.3 (published March 25 20:08 UTC; March 26 in Asia/Kolkata). Models are external artifacts, never repository contents. Early local generation uses an audited Apache-licensed Qwen2.5 1.5B checkpoint; Qwen3 is a later optional comparison. Exact hashes and measured results belong in the execution evidence ledger.

Sources: [Browser Use metadata](https://pypi.org/pypi/browser-use/0.1.18/json), [Playwright metadata](https://pypi.org/pypi/playwright/1.49.1/json), [MCP metadata](https://registry.npmjs.org/@playwright%2fmcp).


## Frozen profiles

`requirements-browser-use.lock` freezes 98 transitive Python distributions. The selected macOS artifacts were audited individually, rather than relying only on a package's first release date. A later same-version jusText wheel was replaced with an explicit URL and hash for its original artifact. The latest selected native artifact is protobuf published January 8 at 21:38 UTC, so the complete profile begins January 9 in Asia/Kolkata. Other operating systems may select different wheels and should review those artifacts separately.

Frontend and MCP npm package locks include exact versions and integrity values. Historical npm overrides keep transitive dependencies within the selected profile. [Dependency provenance](dependency-provenance.json) retains registry publication dates and the selected native Python artifact URLs and hashes. The model locks and immutable checkpoint manifests are separate because they have different runtime constraints.

Container base images are pinned by OCI digest. Installed operating-system packages and the browser represent the current container verification environment; no claim is made that the resulting container image existed at a historical package release date. Review the security document before using legacy dependencies outside the owned local fixture.
