"""End-to-end browser loss with the actual PostgreSQL receipt boundary."""

import asyncio
import os
import threading
import unittest
from workbench.browser import run_browser
from workbench.server import create_server


@unittest.skipUnless(
    os.environ.get("RUN_BROWSER_USE_TESTS") and os.environ.get("TEST_POSTGRES_DSN"),
    "requires Browser Use, Chromium and PostgreSQL",
)
class PostgresBrowserTests(unittest.TestCase):
    def test_lost_confirmation_recovers_postgres_receipt_without_second_effect(self):
        server = create_server(
            "127.0.0.1", 0, os.environ["TEST_POSTGRES_DSN"], "postgres-browser-test"
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        store = server.store
        try:
            before = store.snapshot("WIDGET")["available"]
            a = store.propose("operator", "purchase", {"sku": "WIDGET", "quantity": 1})
            store.approve(a["id"], "operator", a["args"], a["precondition"])
            token = store.dispatch(a["id"], "operator")
            result = asyncio.run(
                run_browser(
                    "http://127.0.0.1:" + str(server.server_port),
                    a,
                    token,
                    adapter="browser-use",
                    fault="kill_after_commit",
                )
            )
            self.assertEqual(result["status"], "outcome_unknown")
            recovered = store.reconcile(a["id"], "operator")
            self.assertEqual(recovered["receipt"]["action_id"], a["id"])
            self.assertEqual(store.snapshot("WIDGET")["available"], before - 1)
            self.assertEqual(
                store.execute(a["id"], token, a["args"]), recovered["receipt"]
            )
            self.assertEqual(store.snapshot("WIDGET")["available"], before - 1)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()
