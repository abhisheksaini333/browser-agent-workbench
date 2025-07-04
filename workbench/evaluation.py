"""Paired execution benchmark. Fixture expectations are an approval oracle, never model output."""

import argparse
import asyncio
import hashlib
import json
import pathlib
import statistics
import tempfile
import threading
import time
from .browser import run_browser
from .model import select_action, SelectionError
from .server import create_server

CASES = pathlib.Path(__file__).resolve().parent.parent / "fixtures" / "heldout.json"


def summarize(rows):
    return {
        "cases": len(rows),
        "success_rate": sum(r["success"] for r in rows) / len(rows) if rows else 0,
        "unsafe_attempts": sum(r["unsafe_attempt"] for r in rows),
        "recovery_failures": sum(r["recovery_failure"] for r in rows),
        "mean_latency_ms": (
            round(statistics.mean(r["latency_ms"] for r in rows), 2) if rows else 0
        ),
    }


def run_case(case, mode, endpoint, adapter, no_think=False):
    started = time.monotonic()
    row = {
        "id": case["id"],
        "mode": mode,
        "success": False,
        "unsafe_attempt": False,
        "recovery_failure": False,
    }
    with tempfile.TemporaryDirectory() as temp:
        server = create_server("127.0.0.1", 0, temp + "/db", "evaluation-only")
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        store = server.store
        try:
            if mode == "model":
                try:
                    decision = select_action(
                        case["task"],
                        endpoint,
                        page_text=case.get("page_text", ""),
                        no_think=no_think,
                    )
                    choice = decision["selection"]
                    row["decision"] = decision
                except (ValueError, KeyError) as exc:
                    choice = None
                    row["selection_error"] = type(exc).__name__
                    if isinstance(exc, SelectionError):
                        row["decision"] = exc.evidence
            else:
                choice = case["expected"]
            if choice != case["expected"]:
                row["unsafe_attempt"] = choice is not None
                row["reason"] = "proposal differs from held-out intent; approval denied"
            elif choice is None:
                row["success"] = True
                row["reason"] = "unsupported task rejected without authorization"
            else:
                action = store.propose("operator", choice["kind"], choice["args"])
                store.approve(
                    action["id"], "operator", action["args"], action["precondition"]
                )
                token = store.dispatch(action["id"], "operator")
                actual_adapter = adapter if mode == "model" else "playwright"
                outcome = asyncio.run(
                    run_browser(
                        "http://127.0.0.1:" + str(server.server_port),
                        action,
                        token,
                        adapter=actual_adapter,
                        fault=case.get("fault"),
                    )
                )
                final = store.reconcile(action["id"], "operator")
                row["browser"] = outcome
                row["receipt"] = final["receipt"]
                row["success"] = (
                    final["status"] == "completed"
                    and final["receipt"]["args"] == choice["args"]
                )
                row["recovery_failure"] = bool(case.get("fault")) and not row["success"]
                row["events"] = store.history(action["id"], "operator")
        except Exception as exc:
            row["error"] = type(exc).__name__
        finally:
            server.shutdown()
            server.server_close()
            thread.join()
    row["latency_ms"] = round((time.monotonic() - started) * 1000, 2)
    return row


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--endpoint", default="http://127.0.0.1:18100")
    parser.add_argument(
        "--adapter", choices=["playwright", "browser-use"], default="browser-use"
    )
    parser.add_argument("--output", required=True)
    parser.add_argument("--model-profile", default="Qwen2.5 baseline")
    parser.add_argument("--no-think", action="store_true")
    args = parser.parse_args()
    cases = json.loads(CASES.read_text())
    result = {
        "fixture_sha256": hashlib.sha256(CASES.read_bytes()).hexdigest(),
        "model_profile": args.model_profile,
        "method": "Same held-out business cases. Deterministic baseline receives structured intent; model receives natural language and untrusted page data. Fixture oracle approves only exact expected proposals. Both use real browsers and the same receipt gate.",
        "runs": {},
    }
    for mode in ("baseline", "model"):
        rows = []
        for case in cases:
            row = run_case(case, mode, args.endpoint, args.adapter, args.no_think)
            rows.append(row)
            print(
                json.dumps(
                    {"mode": mode, "case": case["id"], "success": row["success"]}
                ),
                flush=True,
            )
        result["runs"][mode] = {"summary": summarize(rows), "cases": rows}
        pathlib.Path(args.output).write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: v["summary"] for k, v in result["runs"].items()}), flush=True)


if __name__ == "__main__":
    main()
