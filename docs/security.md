# Security boundaries and compatibility risks

This project demonstrates local owned-portal transactions. It is not a general-purpose isolation system for hostile websites.

## Enforced application controls

- The operator key is required for journal APIs. Browser capabilities cannot invoke those APIs.
- Exact Host and Origin checks prevent a forged Host from redefining the accepted origin. There is no wildcard CORS policy.
- Every write requires a fresh approval bound to exact typed arguments and the original resource version. Boolean/float substitutions for an integer are rejected.
- Transaction SQL is parameterized. Action ownership is checked before journal reads, approval, cancellation, reconciliation and export.
- A browser capability is random, action-specific, expiring and stored as a hash. It never appears in the operator API response or exported evidence.
- HTTP request admission, body size and read time are bounded. The local model client rejects redirects and exposes no arbitrary shell or JavaScript action schema.
- Browser HTTP traffic is restricted to the exact owned loopback origin. Service workers are blocked before navigation and all WebSockets are closed by routing policy. Native Chromium retains its sandbox.
- Page text is untrusted model input. Real tests attempt page-script approval forgery and quantity changes after approval; the server refuses them.

Browser request routing is not an operating-system network boundary. It does not claim to isolate every browser subsystem, DNS/background behavior or WebRTC path. The fixture serves owned static scripts; untrusted text is not injected as HTML. Arbitrary third-party browsing would require an egress-controlled runtime and a separately reviewed threat model.

## Pinned legacy integration profiles

The compatibility profiles intentionally retain API versions under test. A current dependency audit reports five frontend findings (four high, one moderate) and six MCP-profile findings (three high, two moderate, one low), with no critical findings in those npm audits. These are not represented as a clean production dependency audit.

| Area | Relevant exposure | Current boundary |
| --- | --- | --- |
| Vite/esbuild and build-chain dependencies | Development server and untrusted build inputs | The application serves built static assets through Python. `npm run dev` rebuilds files without exposing a Vite web server. Build only trusted repository sources. |
| MCP SDK / Express / route dependencies | HTTP transports and request parsing in affected package versions | The selected MCP composition uses stdio and a fixed set of local tools. It does not expose the SDK's Express HTTP transport. The application HTTP API has its own bounded handler. |
| Browser Use URL allowlist advisory CVE-2025-47241 | Credential-bearing URL can bypass upstream allowlist | The workbench does not rely on that allowlist. Its own exact-origin validation rejects credentials and independently routes browser requests. |
| Compatibility container | Chromium sandbox unavailable in common container configurations | The compose profile explicitly opts out, drops capabilities, uses no-new-privileges and visits only the owned portal. Use native sandboxed execution for the stronger local profile. |

These boundaries reduce exposure in this specific demonstration; they do not fix every upstream vulnerability. A real deployment requires supported dependencies, renewed audits, TLS, proper identity management, network isolation and workload-specific review. Do not expose this pinned reference stack publicly.

The current npm advisory lists can be reproduced with `npm audit --prefix frontend` and `npm audit --prefix adapters/playwright-mcp`. Counts can change as advisories are published. Browser Use advisory source: [upstream security advisory](https://github.com/browser-use/browser-use/security/advisories/GHSA-x39x-9qw5-ghrf).
