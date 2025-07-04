import unittest
from workbench.browser import exact_origin


class OriginTests(unittest.TestCase):
    def test_origin_rejects_credentials_foreign_hosts_and_schemes(self):
        self.assertEqual(
            exact_origin("http://127.0.0.1:18120/path"), ("http", "127.0.0.1", 18120)
        )
        for url in (
            "http://localhost:password@evil.test",
            "http://evil.test",
            "file:///etc/passwd",
            "javascript:alert(1)",
            "http://127.0.0.1.evil.test",
        ):
            with self.assertRaises(ValueError):
                exact_origin(url)
