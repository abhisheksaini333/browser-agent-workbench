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
