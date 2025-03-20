import unittest
from workbench.model import validate_selection, baseline
class SelectionTests(unittest.TestCase):
    def test_model_cannot_supply_approval_or_arbitrary_browser_code(self):
        valid={'kind':'purchase','args':{'sku':'WIDGET','quantity':2}}
        self.assertEqual(validate_selection(valid),valid)
        for value in ({**valid,'approved':True},{'javascript':'fetch("/approve")'},{'kind':'navigate','args':{'url':'https://example.com'}}):
            with self.assertRaises(ValueError):validate_selection(value)
    def test_baseline_is_a_declared_comparator(self):
        self.assertEqual(baseline('purchase 2 WIDGET'),{'kind':'purchase','args':{'sku':'WIDGET','quantity':2}})
        with self.assertRaises(ValueError):baseline('Please get some things')
