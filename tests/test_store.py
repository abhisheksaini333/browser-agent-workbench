import tempfile
import unittest
from pathlib import Path
from workbench.store import Store


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "journal.db"
        self.store = Store(str(self.path))

    def tearDown(self):
        self.temp.cleanup()

    def test_seed_and_reopen(self):
        self.assertEqual(self.store.snapshot("WIDGET")["available"], 20)
        self.assertEqual(
            Store(str(self.path)).snapshot("WIDGET"), self.store.snapshot("WIDGET")
        )

    def test_proposal_retains_exact_precondition_and_owner(self):
        action = self.store.propose(
            "alice", "purchase", {"sku": "WIDGET", "quantity": 2}
        )
        self.assertEqual(action["precondition"], self.store.snapshot("WIDGET"))
        self.assertEqual(action["status"], "proposed")
        self.assertEqual(self.store.get(action["id"], "alice"), action)
        with self.assertRaises(ValueError):
            self.store.get(action["id"], "bob")

    def test_approval_rejects_changed_arguments_and_expires(self):
        action = self.store.propose(
            "alice", "purchase", {"sku": "WIDGET", "quantity": 2}
        )
        with self.assertRaises(ValueError):
            self.store.approve(
                action["id"],
                "alice",
                {"sku": "WIDGET", "quantity": 3},
                action["precondition"],
            )
        approved = self.store.approve(
            action["id"], "alice", action["args"], action["precondition"], ttl=0
        )
        self.assertEqual(approved["status"], "approved")
        with self.assertRaises(ValueError):
            self.store.dispatch(action["id"], "alice")

    def test_dispatch_requires_exact_approval_once(self):
        action = self.store.propose(
            "alice", "purchase", {"sku": "WIDGET", "quantity": 2}
        )
        with self.assertRaises(ValueError):
            self.store.dispatch(action["id"], "alice")
        self.store.approve(
            action["id"], "alice", action["args"], action["precondition"]
        )
        token = self.store.dispatch(action["id"], "alice")
        self.assertGreater(len(token), 30)
        with self.assertRaises(ValueError):
            self.store.dispatch(action["id"], "alice")

    def ready(self, kind="purchase", quantity=2):
        action = self.store.propose(
            "alice", kind, {"sku": "WIDGET", "quantity": quantity}
        )
        self.store.approve(
            action["id"], "alice", action["args"], action["precondition"]
        )
        return action, self.store.dispatch(action["id"], "alice")

    def test_receipt_and_effect_are_atomic_and_idempotent(self):
        a, token = self.ready()
        receipt = self.store.execute(a["id"], token, a["args"])
        self.assertEqual(self.store.snapshot("WIDGET")["available"], 18)
        self.assertEqual(self.store.execute(a["id"], token, a["args"]), receipt)
        self.assertEqual(self.store.snapshot("WIDGET")["available"], 18)
        with self.assertRaises(ValueError):
            self.store.execute(a["id"], "wrong", a["args"])
        with self.assertRaises(ValueError):
            self.store.execute(a["id"], token, {"sku": "WIDGET", "quantity": 3})

    def test_reservation_consumes_capacity_and_inventory_adds_stock(self):
        a, token = self.ready("reservation", 3)
        self.store.execute(a["id"], token, a["args"])
        self.assertEqual(self.store.snapshot("WIDGET")["available"], 17)
        a, token = self.ready("inventory", 5)
        self.store.execute(a["id"], token, a["args"])
        self.assertEqual(self.store.snapshot("WIDGET")["available"], 22)

    def test_precondition_rechecked_at_transaction_boundary(self):
        a, token = self.ready()
        b, other = self.ready()
        self.store.execute(b["id"], other, b["args"])
        with self.assertRaises(ValueError):
            self.store.execute(a["id"], token, a["args"])
        self.assertEqual(self.store.get(a["id"], "alice")["receipt"], None)

    def test_recovery_finds_committed_receipt_after_restart(self):
        a, token = self.ready()
        receipt = self.store.execute(a["id"], token, a["args"])
        reopened = Store(str(self.path))
        self.assertEqual(reopened.reconcile(a["id"], "alice")["receipt"], receipt)
        self.assertEqual(reopened.snapshot("WIDGET")["available"], 18)

    def test_missing_receipt_becomes_unknown_and_never_blind_retries(self):
        a, token = self.ready()
        self.assertEqual(
            self.store.reconcile(a["id"], "alice")["status"], "outcome_unknown"
        )
        with self.assertRaises(ValueError):
            self.store.dispatch(a["id"], "alice")
        with self.assertRaises(ValueError):
            self.store.execute(a["id"], token, a["args"])

    def test_cancel_before_dispatch_blocks_effect_and_records_history(self):
        a = self.store.propose("alice", "purchase", {"sku": "WIDGET", "quantity": 2})
        self.store.cancel(a["id"], "alice")
        self.assertEqual(self.store.get(a["id"], "alice")["status"], "cancelled")
        self.assertIn(
            "cancelled", [e["event"] for e in self.store.history(a["id"], "alice")]
        )
        with self.assertRaises(ValueError):
            self.store.approve(a["id"], "alice", a["args"], a["precondition"])
        self.assertEqual(len(self.store.list_actions("alice")), 1)
        self.assertEqual(self.store.list_actions("bob"), [])

    def test_cancel_after_dispatch_does_not_claim_rollback(self):
        a, token = self.ready()
        self.assertEqual(
            self.store.cancel(a["id"], "alice")["status"], "outcome_unknown"
        )

    def test_expired_dispatch_cannot_submit_new_effect(self):
        a, token = self.ready()
        with self.store.connection() as db:
            db.execute("UPDATE actions SET expires=0 WHERE id=?", (a["id"],))
        with self.assertRaises(ValueError):
            self.store.execute(a["id"], token, a["args"])
        self.assertEqual(self.store.snapshot("WIDGET")["available"], 20)

    def test_export_is_verifiable_and_contains_no_capabilities(self):
        from workbench.domain import digest

        a, token = self.ready()
        self.store.execute(a["id"], token, a["args"])
        evidence = self.store.export_evidence(a["id"], "alice")
        self.assertEqual(evidence["sha256"], digest(evidence["record"]))
        self.assertNotIn(token, str(evidence))
        self.assertNotIn("dispatch", evidence["record"]["action"])
        with self.assertRaises(ValueError):
            self.store.export_evidence(a["id"], "bob")

    def test_numeric_type_changes_do_not_reuse_exact_approval(self):
        a = self.store.propose("alice", "purchase", {"sku": "WIDGET", "quantity": 1})
        for quantity in (True, 1.0):
            with self.assertRaises(ValueError):
                self.store.approve(
                    a["id"],
                    "alice",
                    {"sku": "WIDGET", "quantity": quantity},
                    a["precondition"],
                )
        with self.assertRaises(ValueError):
            self.store.approve(
                a["id"], "alice", a["args"], {**a["precondition"], "version": True}
            )
        self.store.approve(a["id"], "alice", a["args"], a["precondition"])
        token = self.store.dispatch(a["id"], "alice")
        with self.assertRaises(ValueError):
            self.store.execute(a["id"], token, {"sku": "WIDGET", "quantity": True})

    def test_selection_evidence_remains_bound_to_its_action_after_restart(self):
        decision = {
            "model": "fixture-model",
            "selection": {"kind": "purchase", "args": {"sku": "WIDGET", "quantity": 1}},
            "raw_output": "bounded fixture",
        }
        first = self.store.propose(
            "alice", "purchase", {"sku": "WIDGET", "quantity": 1}, decision=decision
        )
        second = self.store.propose(
            "alice", "inventory", {"sku": "DESK", "quantity": 2}
        )
        reopened = Store(str(self.path))
        self.assertEqual(reopened.get(first["id"], "alice")["decision"], decision)
        self.assertIsNone(reopened.get(second["id"], "alice")["decision"])
        by_id = {a["id"]: a for a in reopened.list_actions("alice")}
        self.assertEqual(by_id[first["id"]]["decision"], decision)


    def test_invalid_ttl_does_not_mutate_the_proposal(self):
        for ttl in (True, False, -1, float("nan"), float("inf"), -float("inf"), "30", None):
            with self.subTest(ttl=ttl):
                action = self.store.propose("alice", "purchase", {"sku": "WIDGET", "quantity": 1})
                with self.assertRaises(ValueError):
                    self.store.approve(action["id"], "alice", action["args"], action["precondition"], ttl=ttl)
                self.assertEqual(self.store.get(action["id"], "alice")["status"], "proposed")
                self.assertEqual(self.store.history(action["id"], "alice"), [])

    def test_fractional_and_capped_lifetimes_remain_supported(self):
        from unittest.mock import patch
        for ttl, duration in ((0, 0), (0.5, 0.5), (30, 30), (900, 300)):
            with self.subTest(ttl=ttl):
                action = self.store.propose("alice", "purchase", {"sku": "WIDGET", "quantity": 1})
                with patch("workbench.store.time.time", return_value=1000):
                    approved = self.store.approve(action["id"], "alice", action["args"], action["precondition"], ttl=ttl)
                self.assertEqual(approved["expires"], 1000 + duration)


    def test_expiry_boundary_is_closed_for_every_capability_entrypoint(self):
        from unittest.mock import patch
        for operation in ("dispatch", "portal", "execute"):
            with self.subTest(operation=operation):
                with patch("workbench.store.time.time", return_value=1000):
                    action = self.store.propose("alice", "purchase", {"sku": "WIDGET", "quantity": 1})
                    self.store.approve(action["id"], "alice", action["args"], action["precondition"], ttl=10)
                    token = self.store.dispatch(action["id"], "alice") if operation != "dispatch" else None
                with patch("workbench.store.time.time", return_value=1010):
                    with self.assertRaises(ValueError):
                        if operation == "dispatch":
                            self.store.dispatch(action["id"], "alice")
                        elif operation == "portal":
                            self.store.portal_action(action["id"], token)
                        else:
                            self.store.execute(action["id"], token, action["args"])
                self.assertEqual(self.store.snapshot("WIDGET")["available"], 20)
                self.assertIsNone(self.store.get(action["id"], "alice")["receipt"])

    def test_malformed_persisted_expiry_is_rejected_without_type_errors(self):
        from unittest.mock import patch
        for expires in (None, float("inf"), "not-a-clock"):
            for operation in ("dispatch", "portal", "execute"):
                with self.subTest(expires=expires, operation=operation):
                    action = self.store.propose("alice", "purchase", {"sku": "WIDGET", "quantity": 1})
                    self.store.approve(action["id"], "alice", action["args"], action["precondition"])
                    token = self.store.dispatch(action["id"], "alice") if operation != "dispatch" else None
                    with self.store.connection() as db:
                        db.execute("UPDATE actions SET expires=? WHERE id=?", (expires, action["id"]))
                    with self.assertRaises(ValueError):
                        if operation == "dispatch":
                            self.store.dispatch(action["id"], "alice")
                        elif operation == "portal":
                            self.store.portal_action(action["id"], token)
                        else:
                            self.store.execute(action["id"], token, action["args"])
                    self.assertEqual(self.store.snapshot("WIDGET")["available"], 20)

    def test_recorded_receipt_remains_replayable_after_expiry_without_effect(self):
        from unittest.mock import patch
        action, token = self.ready()
        receipt = self.store.execute(action["id"], token, action["args"])
        with patch("workbench.store.time.time", return_value=10**12):
            self.assertEqual(self.store.execute(action["id"], token, action["args"]), receipt)
        self.assertEqual(self.store.snapshot("WIDGET")["available"], 18)

    def test_repeated_cancellation_and_reconciliation_do_not_duplicate_events(self):
        action = self.store.propose("alice", "purchase", {"sku": "WIDGET", "quantity": 2})
        self.store.cancel(action["id"], "alice")
        history = self.store.history(action["id"], "alice")
        self.store.cancel(action["id"], "alice")
        self.store.reconcile(action["id"], "alice")
        self.assertEqual(self.store.history(action["id"], "alice"), history)
        dispatched, token = self.ready()
        self.store.reconcile(dispatched["id"], "alice")
        unknown_history = self.store.history(dispatched["id"], "alice")
        self.store.reconcile(dispatched["id"], "alice")
        self.store.cancel(dispatched["id"], "alice")
        self.assertEqual(self.store.history(dispatched["id"], "alice"), unknown_history)
        self.assertEqual(self.store.get(dispatched["id"], "alice")["status"], "outcome_unknown")
        self.assertEqual(self.store.snapshot("WIDGET")["available"], 20)

    def test_completed_receipt_is_not_given_spurious_cancel_or_reconcile_events(self):
        action, token = self.ready()
        receipt = self.store.execute(action["id"], token, action["args"])
        history = self.store.history(action["id"], "alice")
        self.store.cancel(action["id"], "alice")
        self.store.reconcile(action["id"], "alice")
        self.assertEqual(self.store.history(action["id"], "alice"), history)
        self.assertEqual(self.store.get(action["id"], "alice")["receipt"], receipt)
