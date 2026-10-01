import unittest
from workbench.evaluation import summarize


class EvaluationTests(unittest.TestCase):
    def test_failure_denominators_are_retained(self):
        result = summarize(
            [
                {
                    "success": True,
                    "unsafe_attempt": False,
                    "recovery_failure": False,
                    "latency_ms": 10,
                },
                {
                    "success": False,
                    "unsafe_attempt": True,
                    "recovery_failure": True,
                    "latency_ms": 30,
                },
            ]
        )
        self.assertEqual(result["success_rate"], 0.5)
        self.assertEqual(result["unsafe_attempts"], 1)
        self.assertEqual(result["recovery_failures"], 1)
        self.assertEqual(result["mean_latency_ms"], 20)

    def test_invalid_observations_are_rejected_instead_of_distorting_metrics(self):
        base = {
            "success": True,
            "unsafe_attempt": False,
            "recovery_failure": False,
            "latency_ms": 10,
        }
        for key, values in {
            "success": [1, "yes", None],
            "unsafe_attempt": [0, "false"],
            "recovery_failure": [1],
            "latency_ms": [True, -1, float("nan"), float("inf"), "10", None],
        }.items():
            for value in values:
                with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                    summarize([{**base, key: value}])
        for row in ({}, [], None):
            with self.subTest(row=row), self.assertRaises(ValueError):
                summarize([row])

    def test_empty_report_and_zero_latency_remain_valid(self):
        self.assertEqual(
            summarize([]),
            {
                "cases": 0,
                "success_rate": 0,
                "unsafe_attempts": 0,
                "recovery_failures": 0,
                "mean_latency_ms": 0,
            },
        )
        self.assertEqual(
            summarize(
                [
                    {
                        "success": True,
                        "unsafe_attempt": False,
                        "recovery_failure": False,
                        "latency_ms": 0,
                    }
                ]
            )["mean_latency_ms"],
            0,
        )
