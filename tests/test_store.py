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
