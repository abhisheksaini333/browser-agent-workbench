import unittest
from workbench.domain import validate_arguments

class ArgumentsTests(unittest.TestCase):
    def test_purchase_is_strict_and_bounded(self):
        self.assertEqual(validate_arguments('purchase', {'sku':'WIDGET','quantity':2}), {'sku':'WIDGET','quantity':2})
        for args in ({'sku':'WIDGET','quantity':True},{'sku':'WIDGET','quantity':0},{'sku':'WIDGET','quantity':101},{'sku':'WIDGET','quantity':1,'approved':True}):
            with self.assertRaises(ValueError):validate_arguments('purchase',args)
