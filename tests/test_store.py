import tempfile
import unittest
from pathlib import Path
from workbench.store import Store

class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)/'journal.db';self.store=Store(str(self.path))
    def tearDown(self):self.temp.cleanup()
    def test_seed_and_reopen(self):
        self.assertEqual(self.store.snapshot('WIDGET')['available'],20)
        self.assertEqual(Store(str(self.path)).snapshot('WIDGET'),self.store.snapshot('WIDGET'))
    def test_proposal_retains_exact_precondition_and_owner(self):
        action=self.store.propose('alice','purchase',{'sku':'WIDGET','quantity':2})
        self.assertEqual(action['precondition'],self.store.snapshot('WIDGET'))
        self.assertEqual(action['status'],'proposed')
        self.assertEqual(self.store.get(action['id'],'alice'),action)
        with self.assertRaises(ValueError):self.store.get(action['id'],'bob')
    def test_approval_rejects_changed_arguments_and_expires(self):
        action=self.store.propose('alice','purchase',{'sku':'WIDGET','quantity':2})
        with self.assertRaises(ValueError):self.store.approve(action['id'],'alice',{'sku':'WIDGET','quantity':3},action['precondition'])
        approved=self.store.approve(action['id'],'alice',action['args'],action['precondition'],ttl=0)
        self.assertEqual(approved['status'],'approved')
        with self.assertRaises(ValueError):self.store.dispatch(action['id'],'alice')
    def test_dispatch_requires_exact_approval_once(self):
        action=self.store.propose('alice','purchase',{'sku':'WIDGET','quantity':2})
        with self.assertRaises(ValueError):self.store.dispatch(action['id'],'alice')
        self.store.approve(action['id'],'alice',action['args'],action['precondition'])
        token=self.store.dispatch(action['id'],'alice')
        self.assertGreater(len(token),30)
        with self.assertRaises(ValueError):self.store.dispatch(action['id'],'alice')
    def ready(self,kind='purchase',quantity=2):
        action=self.store.propose('alice',kind,{'sku':'WIDGET','quantity':quantity})
        self.store.approve(action['id'],'alice',action['args'],action['precondition'])
        return action,self.store.dispatch(action['id'],'alice')
    def test_receipt_and_effect_are_atomic_and_idempotent(self):
        a,token=self.ready()
        receipt=self.store.execute(a['id'],token,a['args'])
        self.assertEqual(self.store.snapshot('WIDGET')['available'],18)
        self.assertEqual(self.store.execute(a['id'],token,a['args']),receipt)
        self.assertEqual(self.store.snapshot('WIDGET')['available'],18)
        with self.assertRaises(ValueError):self.store.execute(a['id'],'wrong',a['args'])
        with self.assertRaises(ValueError):self.store.execute(a['id'],token,{'sku':'WIDGET','quantity':3})
    def test_reservation_consumes_capacity_and_inventory_adds_stock(self):
        a,token=self.ready('reservation',3);self.store.execute(a['id'],token,a['args'])
        self.assertEqual(self.store.snapshot('WIDGET')['available'],17)
        a,token=self.ready('inventory',5);self.store.execute(a['id'],token,a['args'])
        self.assertEqual(self.store.snapshot('WIDGET')['available'],22)
    def test_precondition_rechecked_at_transaction_boundary(self):
        a,token=self.ready();b,other=self.ready()
        self.store.execute(b['id'],other,b['args'])
        with self.assertRaises(ValueError):self.store.execute(a['id'],token,a['args'])
        self.assertEqual(self.store.get(a['id'],'alice')['receipt'],None)
    def test_recovery_finds_committed_receipt_after_restart(self):
        a,token=self.ready();receipt=self.store.execute(a['id'],token,a['args'])
        reopened=Store(str(self.path))
        self.assertEqual(reopened.reconcile(a['id'],'alice')['receipt'],receipt)
        self.assertEqual(reopened.snapshot('WIDGET')['available'],18)
    def test_missing_receipt_becomes_unknown_and_never_blind_retries(self):
        a,token=self.ready()
        self.assertEqual(self.store.reconcile(a['id'],'alice')['status'],'outcome_unknown')
        with self.assertRaises(ValueError):self.store.dispatch(a['id'],'alice')
        with self.assertRaises(ValueError):self.store.execute(a['id'],token,a['args'])
    def test_cancel_before_dispatch_blocks_effect_and_records_history(self):
        a=self.store.propose('alice','purchase',{'sku':'WIDGET','quantity':2})
        self.store.cancel(a['id'],'alice')
        self.assertEqual(self.store.get(a['id'],'alice')['status'],'cancelled')
        self.assertIn('cancelled',[e['event'] for e in self.store.history(a['id'],'alice')])
        with self.assertRaises(ValueError):self.store.approve(a['id'],'alice',a['args'],a['precondition'])
        self.assertEqual(len(self.store.list_actions('alice')),1)
        self.assertEqual(self.store.list_actions('bob'),[])
    def test_cancel_after_dispatch_does_not_claim_rollback(self):
        a,token=self.ready()
        self.assertEqual(self.store.cancel(a['id'],'alice')['status'],'outcome_unknown')
