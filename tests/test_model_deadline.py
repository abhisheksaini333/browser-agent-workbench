import json
import threading
import time
import unittest
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from workbench.model import select_action


class ModelDeadlineTests(unittest.TestCase):
    def test_stalled_or_dripping_generation_has_absolute_deadline(self):
        class Handler(BaseHTTPRequestHandler):
            mode = "stalled"

            def log_message(self, *args):
                pass

            def do_POST(self):
                self.rfile.read(int(self.headers["Content-Length"]))
                if self.mode == "stalled":
                    time.sleep(0.7)
                    return
                self.send_response(200)
                self.send_header("Content-Length", "1000")
                self.end_headers()
                try:
                    for _ in range(20):
                        self.wfile.write(b" ")
                        self.wfile.flush()
                        time.sleep(0.05)
                except OSError:
                    pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            for mode in ["stalled", "trickling"]:
                Handler.mode = mode
                started = time.monotonic()
                with self.assertRaises(urllib.error.URLError):
                    select_action(
                        "purchase 1 WIDGET",
                        f"http://127.0.0.1:{server.server_port}",
                        timeout=0.2,
                    )
                self.assertLess(time.monotonic() - started, 0.5)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_unbounded_timeout_configuration_is_rejected_before_network(self):
        for timeout in [0, -1, 11, "nan", "bad"]:
            with self.assertRaises(ValueError):
                select_action("purchase 1 WIDGET", "http://localhost", timeout=timeout)

    def test_bounded_model_reply_is_validated_without_leaking_body(self):
        class Handler(BaseHTTPRequestHandler):
            payload = b"{}"

            def log_message(self, *args):
                pass

            def do_POST(self):
                self.rfile.read(int(self.headers["Content-Length"]))
                self.send_response(200)
                self.send_header("Content-Length", str(len(self.payload)))
                self.end_headers()
                self.wfile.write(self.payload)

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            for payload in [
                b"x" * 65537,
                b'{"choices":[]}',
                b'{"choices":[{"message":{"content":null}}]}',
            ]:
                Handler.payload = payload
                with self.assertRaises(ValueError) as error:
                    select_action(
                        "purchase 1 WIDGET", f"http://127.0.0.1:{server.server_port}"
                    )
                self.assertLess(len(str(error.exception)), 120)
            Handler.payload = json.dumps(
                {
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    {
                                        "kind": "purchase",
                                        "args": {"sku": "WIDGET", "quantity": 1},
                                    }
                                )
                            }
                        }
                    ]
                }
            ).encode()
            result = select_action(
                "purchase 1 WIDGET", f"http://127.0.0.1:{server.server_port}"
            )
            self.assertEqual(result["selection"]["args"]["quantity"], 1)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()
