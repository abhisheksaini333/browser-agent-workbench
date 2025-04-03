import unittest
from workbench.evaluation import summarize
class EvaluationTests(unittest.TestCase):
    def test_failure_denominators_are_retained(self):
        result=summarize([{'success':True,'unsafe_attempt':False,'recovery_failure':False,'latency_ms':10},{'success':False,'unsafe_attempt':True,'recovery_failure':True,'latency_ms':30}])
        self.assertEqual(result['success_rate'],.5);self.assertEqual(result['unsafe_attempts'],1);self.assertEqual(result['recovery_failures'],1);self.assertEqual(result['mean_latency_ms'],20)
