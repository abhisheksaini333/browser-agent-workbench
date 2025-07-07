import json
import tempfile
import threading
import unittest
import urllib.request
import urllib.error
from workbench.server import create_server


class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.server = create_server("127.0.0.1", 0, self.temp.name + "/db", "test-key")
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = "http://127.0.0.1:" + str(self.server.server_port)

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()

    def request(self, path, data=None, key="test-key"):
        req = urllib.request.Request(
            self.url + path,
            data=json.dumps(data).encode() if data is not None else None,
            headers={
                "Authorization": "Bearer " + key,
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(req) as response:
            return json.load(response)

    def test_authenticated_proposal_and_listing(self):
        with self.assertRaises(urllib.error.HTTPError) as err:
            self.request("/api/actions", key="bad")
        self.assertEqual(err.exception.code, 401)
        a = self.request(
            "/api/actions",
            {"kind": "purchase", "args": {"sku": "WIDGET", "quantity": 2}},
        )
        self.assertEqual(self.request("/api/actions")[0]["id"], a["id"])
        self.assertNotIn("dispatch", a)

    def test_portal_capability_scoped_to_one_action(self):
        a = self.server.store.propose(
            "operator", "purchase", {"sku": "WIDGET", "quantity": 2}
        )
        self.server.store.approve(a["id"], "operator", a["args"], a["precondition"])
        token = self.server.store.dispatch(a["id"], "operator")
        req = urllib.request.Request(
            self.url + "/portal/action/" + a["id"], headers={"X-Dispatch-Token": token}
        )
        with urllib.request.urlopen(req) as r:
            self.assertEqual(json.load(r)["args"], a["args"])
        req = urllib.request.Request(
            self.url + "/portal/action/" + a["id"], headers={"X-Dispatch-Token": "bad"}
        )
        with self.assertRaises(urllib.error.HTTPError) as err:
            urllib.request.urlopen(req)
        self.assertEqual(err.exception.code, 403)

    def test_baseline_task_creates_unapproved_action(self):
        a = self.request(
            "/api/tasks", {"task": "reservation 1 ROOM", "mode": "baseline"}
        )
        self.assertEqual(a["action"]["kind"], "reservation")
        self.assertEqual(a["action"]["status"], "proposed")

    def test_cross_origin_request_is_rejected(self):
        req = urllib.request.Request(
            self.url + "/api/actions",
            data=b"{}",
            headers={
                "Authorization": "Bearer test-key",
                "Origin": "https://evil.example",
            },
        )
        with self.assertRaises(urllib.error.HTTPError) as err:
            urllib.request.urlopen(req)
        self.assertEqual(err.exception.code, 403)

    def test_busy_browser_lane_rejects_before_consuming_approval(self):
        a = self.request(
            "/api/actions",
            {"kind": "purchase", "args": {"sku": "WIDGET", "quantity": 1}},
        )
        self.request(
            "/api/actions/" + a["id"] + "/approve",
            {"args": a["args"], "precondition": a["precondition"]},
        )
        self.server.browser_slots.acquire()
        try:
            with self.assertRaises(urllib.error.HTTPError) as err:
                self.request("/api/actions/" + a["id"] + "/run", {})
            self.assertEqual(err.exception.code, 409)
            self.assertEqual(
                self.server.store.get(a["id"], "operator")["status"], "approved"
            )
        finally:
            self.server.browser_slots.release()

    def test_forged_host_is_rejected_even_with_matching_origin(self):
        req = urllib.request.Request(
            self.url + "/api/actions",
            headers={
                "Authorization": "Bearer test-key",
                "Host": "attacker.example",
                "Origin": "http://attacker.example",
            },
        )
        with self.assertRaises(urllib.error.HTTPError) as err:
            urllib.request.urlopen(req)
        self.assertEqual(err.exception.code, 403)

    def test_slow_partial_body_hits_bounded_read_deadline(self):
        import socket, time

        self.server.read_timeout = 0.2
        sock = socket.create_connection(
            ("127.0.0.1", self.server.server_port), timeout=2
        )
        start = time.monotonic()
        sock.sendall(
            (
                "POST /api/actions HTTP/1.1\r\nHost: 127.0.0.1:"
                + str(self.server.server_port)
                + "\r\nAuthorization: Bearer test-key\r\nContent-Length: 100\r\n\r\n{"
            ).encode()
        )
        response = sock.recv(4096)
        sock.close()
        self.assertIn(b"408", response)
        self.assertLess(time.monotonic() - start, 2)

    def test_request_admission_rejects_seventeenth_partial_connection(self):
        import socket

        sockets = []
        self.server.read_timeout = 5
        try:
            for _ in range(17):
                connection = socket.create_connection(
                    ("127.0.0.1", self.server.server_port), timeout=2
                )
                connection.sendall(b"GET /health HTTP/1.1\r\n")
                sockets.append(connection)
            response = sockets[-1].recv(4096)
            self.assertIn(b"503 Service Unavailable", response)
        finally:
            for connection in sockets:
                connection.close()
