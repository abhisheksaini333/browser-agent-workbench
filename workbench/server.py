"""Loopback HTTP server for the workbench and owned transaction portal."""

import argparse
import asyncio
import hmac
import json
import os
import pathlib
import secrets
import socket
import threading
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse
from .store import Store, Conflict, Forbidden

ROOT = pathlib.Path(__file__).resolve().parent.parent


class RequestDeadline(ValueError):
    pass


class BoundedServer(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 16
    read_timeout = 3

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.request_slots = threading.BoundedSemaphore(16)

    def get_request(self):
        connection, address = super().get_request()
        connection.settimeout(self.read_timeout)
        return connection, address

    def process_request(self, request, address):
        if not self.request_slots.acquire(blocking=False):
            try:
                request.sendall(
                    b"HTTP/1.1 503 Service Unavailable\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"
                )
            finally:
                self.shutdown_request(request)
            return
        try:
            super().process_request(request, address)
        except Exception:
            self.request_slots.release()
            raise

    def process_request_thread(self, request, address):
        try:
            super().process_request_thread(request, address)
        finally:
            self.request_slots.release()


def create_server(host, port, database, key):
    store = Store(database)

    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.read_expired = threading.Event()
            self.read_deadline = threading.Timer(
                self.server.read_timeout, self.expire_read
            )
            self.read_deadline.daemon = True
            self.read_deadline.start()

        def expire_read(self):
            self.read_expired.set()
            try:
                self.connection.shutdown(socket.SHUT_RD)
            except OSError:
                pass

        def finish(self):
            self.read_deadline.cancel()
            super().finish()

        def handle(self):
            try:
                super().handle()
            except (BrokenPipeError, ConnectionResetError):
                # Client cancellation is expected while admission deadlines are enforced.
                return

        def log_message(self, *args):
            pass

        def reply(self, status, data, content_type="application/json"):
            body = (
                json.dumps(data).encode()
                if content_type == "application/json"
                else data.encode()
            )
            self.send_response(status)
            for k, v in {
                "Content-Type": content_type,
                "Content-Length": str(len(body)),
                "X-Content-Type-Options": "nosniff",
                "X-Frame-Options": "DENY",
                "Cache-Control": "no-store",
                "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self'; frame-ancestors 'none'",
            }.items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def authenticated(self):
            value = self.headers.get("Authorization", "")
            return hmac.compare_digest(value, "Bearer " + key)

        def body(self):
            size = int(self.headers.get("Content-Length", "0"))
            if size < 0 or size > 16384:
                raise ValueError("request too large")
            try:
                raw = self.rfile.read(size)
            except TimeoutError as exc:
                raise RequestDeadline("request body deadline exceeded") from exc
            self.read_deadline.cancel()
            if self.read_expired.is_set():
                raise RequestDeadline("absolute request body deadline exceeded")
            data = json.loads(raw or b"{}")
            if not isinstance(data, dict):
                raise ValueError("object required")
            return data

        def handle_request(self, method):
            if method == "GET":
                self.read_deadline.cancel()
            path = urlparse(self.path).path
            authorities = {
                "127.0.0.1:" + str(self.server.server_port),
                "localhost:" + str(self.server.server_port),
            }
            authority = self.headers.get("Host", "")
            if authority not in authorities:
                return self.reply(403, {"error": "host denied"})
            if self.headers.get("Origin") not in (None, "http://" + authority):
                return self.reply(403, {"error": "origin denied"})
            if path == "/health":
                return self.reply(200, {"status": "ok"})
            if method == "GET" and (path == "/" or path.startswith("/assets/")):
                dist = (ROOT / "frontend" / "dist").resolve()
                target = (
                    dist / ("index.html" if path == "/" else path.lstrip("/"))
                ).resolve()
                if not target.is_relative_to(dist) or not target.is_file():
                    return self.reply(404, {"error": "Build the frontend first"})
                content_type = {
                    ".html": "text/html",
                    ".js": "text/javascript",
                    ".css": "text/css",
                }.get(target.suffix, "text/plain")
                return self.reply(200, target.read_text(), content_type)
            if method == "GET" and path in ("/portal/", "/portal/app.js"):
                name = "index.html" if path == "/portal/" else "app.js"
                return self.reply(
                    200,
                    (ROOT / "portal" / name).read_text(),
                    "text/html" if name == "index.html" else "text/javascript",
                )
            if path.startswith("/portal/action/"):
                try:
                    action_id = path.rsplit("/", 1)[-1]
                    token = self.headers.get("X-Dispatch-Token", "")
                    action = store.portal_action(action_id, token)
                    if method == "GET":
                        return self.reply(200, action)
                    data = self.body()
                    receipt = store.execute(action_id, token, data["args"])
                    return self.reply(200, receipt)
                except RequestDeadline as exc:
                    return self.reply(408, {"error": str(exc)})
                except Forbidden as exc:
                    return self.reply(403, {"error": str(exc)})
                except Conflict as exc:
                    return self.reply(409, {"error": str(exc)})
                except (ValueError, KeyError, TypeError):
                    return self.reply(400, {"error": "invalid submission"})
            if not self.authenticated():
                return self.reply(401, {"error": "authentication required"})
            try:
                if method == "GET" and path == "/api/actions":
                    return self.reply(200, store.list_actions("operator"))
                if method == "POST" and path == "/api/tasks":
                    from .model import baseline, select_action

                    data = self.body()
                    if data.get("mode") == "baseline":
                        decision = {
                            "selection": baseline(data["task"]),
                            "model": "deterministic baseline",
                        }
                    elif data.get("mode") == "model":
                        decision = select_action(
                            data["task"],
                            os.environ.get("MODEL_ENDPOINT", "http://127.0.0.1:18100"),
                            no_think=os.environ.get("MODEL_NO_THINK") == "1",
                        )
                    else:
                        raise ValueError("select baseline or model mode")
                    choice = decision["selection"]
                    action = store.propose(
                        "operator", choice["kind"], choice["args"], decision=decision
                    )
                    return self.reply(201, {"action": action, "decision": decision})
                if method == "GET" and path.startswith("/api/resources/"):
                    return self.reply(200, store.snapshot(path.rsplit("/", 1)[-1]))
                if method == "POST" and path == "/api/actions":
                    data = self.body()
                    return self.reply(
                        201, store.propose("operator", data["kind"], data["args"])
                    )
                parts = path.strip("/").split("/")
                if len(parts) >= 3 and parts[:2] == ["api", "actions"]:
                    action_id = parts[2]
                    if method == "GET" and len(parts) == 3:
                        return self.reply(200, store.get(action_id, "operator"))
                    if method == "GET" and parts[-1] == "events":
                        return self.reply(200, store.history(action_id, "operator"))
                    if method == "GET" and parts[-1] == "evidence":
                        return self.reply(
                            200, store.export_evidence(action_id, "operator")
                        )
                    if method == "POST" and len(parts) == 4:
                        data = self.body()
                        verb = parts[-1]
                        if verb == "approve":
                            return self.reply(
                                200,
                                store.approve(
                                    action_id,
                                    "operator",
                                    data["args"],
                                    data["precondition"],
                                ),
                            )
                        if verb == "cancel":
                            return self.reply(200, store.cancel(action_id, "operator"))
                        if verb == "reconcile":
                            return self.reply(
                                200, store.reconcile(action_id, "operator")
                            )
                        if verb == "run":
                            from .browser import run_browser

                            adapter = data.get("adapter", "playwright")
                            if adapter not in (
                                "playwright",
                                "browser-use",
                                "playwright-mcp",
                            ):
                                raise ValueError("unknown adapter")
                            if not self.server.browser_slots.acquire(blocking=False):
                                raise Conflict(
                                    "browser lane is busy; approval retained"
                                )
                            try:
                                action = store.get(action_id, "operator")
                                token = store.dispatch(action_id, "operator")
                                result = asyncio.run(
                                    run_browser(
                                        "http://127.0.0.1:"
                                        + str(self.server.server_port),
                                        action,
                                        token,
                                        adapter=adapter,
                                    )
                                )
                                current = store.reconcile(action_id, "operator")
                                return self.reply(
                                    200, {"action": current, "browser": result}
                                )
                            finally:
                                self.server.browser_slots.release()
                return self.reply(404, {"error": "not found"})
            except RequestDeadline as exc:
                return self.reply(408, {"error": str(exc)})
            except (urllib.error.URLError, TimeoutError):
                return self.reply(
                    502, {"error": "local model unavailable; no action was authorized"}
                )
            except Forbidden as exc:
                return self.reply(403, {"error": str(exc)})
            except Conflict as exc:
                return self.reply(409, {"error": str(exc)})
            except (ValueError, KeyError, TypeError) as exc:
                return self.reply(400, {"error": "invalid request: " + str(exc)})

        def do_GET(self):
            self.handle_request("GET")

        def do_POST(self):
            self.handle_request("POST")

    server = BoundedServer((host, port), Handler)
    server.store = store
    server.browser_slots = threading.BoundedSemaphore(1)
    return server


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18120)
    parser.add_argument("--database", default="workbench.db")
    args = parser.parse_args()
    key = os.environ.get("WORKBENCH_KEY")
    if not key:
        raise SystemExit("Set WORKBENCH_KEY to a strong local operator secret")
    server = create_server(args.host, args.port, args.database, key)
    print(f"Workbench listening at http://{args.host}:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
