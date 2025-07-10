# Local API

All `/api` requests require `Authorization: Bearer <WORKBENCH_KEY>`. The server accepts only its literal `localhost:port` or `127.0.0.1:port` Host authority and a matching Origin when present. Use the same external and internal port when forwarding the local service.

| Method | Route | Result |
| --- | --- | --- |
| GET | `/health` | Liveness only |
| GET | `/api/actions` | Operator's latest 200 actions |
| POST | `/api/actions` | Typed unapproved proposal from `kind` and `args` |
| POST | `/api/tasks` | Proposal from `task` and explicit `mode: baseline` or `model` |
| GET | `/api/resources/WIDGET` | Owned resource snapshot |
| GET | `/api/actions/{id}` | Action without approval/dispatch secrets |
| POST | `/api/actions/{id}/approve` | Approve exact `args` and `precondition` |
| POST | `/api/actions/{id}/run` | Execute with `adapter: playwright`, `browser-use`, or `playwright-mcp` |
| POST | `/api/actions/{id}/cancel` | Cancel pending work; dispatched uncertainty remains explicit |
| POST | `/api/actions/{id}/reconcile` | Find the authoritative application receipt |
| GET | `/api/actions/{id}/events` | Ordered action history |
| GET | `/api/actions/{id}/evidence` | Redacted record and canonical JSON SHA-256 |

```json
{"kind":"purchase","args":{"sku":"WIDGET","quantity":2}}
```

Quantities are integers from 1 to 100. Boolean and float substitutions are rejected. Extra argument fields, arbitrary URLs, JavaScript and approval fields are not part of the model action schema. Approval lasts at most five minutes. The API never returns its browser dispatch capability.

Errors use JSON: 400 invalid contract, 401 missing/incorrect operator key, 403 denied authority or capability, 409 stale approval/state/busy browser lane, 408 incomplete body deadline, 502 local model unavailable, and 503 connection admission limit. The workspace displays operational errors without exposing stack traces.
