"""Isolated browser execution against one exact owned origin."""

import asyncio
import json
import os
import pathlib
import signal
import subprocess
import tempfile
from urllib.parse import urlsplit


def exact_origin(url):
    parsed = urlsplit(url)
    if parsed.username or parsed.password or parsed.scheme not in ("http", "https"):
        raise ValueError("invalid origin")
    if parsed.hostname not in ("127.0.0.1", "localhost"):
        raise ValueError("only owned loopback portals are allowed")
    return (
        parsed.scheme,
        parsed.hostname,
        parsed.port or (443 if parsed.scheme == "https" else 80),
    )


async def run_browser(origin, action, token, *, adapter="playwright", fault=None):
    if adapter == "playwright-mcp":
        from .mcp_adapter import run_mcp

        return await run_mcp(origin, action, token)
    from playwright.async_api import async_playwright

    allowed = exact_origin(origin)
    blocked = []
    blocked_websockets = []
    injected = False
    unauthorized_status = None
    async with async_playwright() as playwright:
        executable = os.environ.get("CHROMIUM_PATH") or (
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
            if pathlib.Path("/Applications/Google Chrome.app").exists()
            else playwright.chromium.executable_path
        )
        with tempfile.TemporaryDirectory(
            prefix="workbench-browser-", ignore_cleanup_errors=True
        ) as profile:
            process = subprocess.Popen(
                [
                    executable,
                    "--headless=new",
                    "--remote-debugging-port=0",
                    "--user-data-dir=" + profile,
                    "--no-first-run",
                    "--no-default-browser-check",
                    "--disable-background-networking",
                ]
                + (
                    ["--no-sandbox"]
                    if os.environ.get("WORKBENCH_UNSANDBOXED_CONTAINER") == "1"
                    else []
                ),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            try:
                active = pathlib.Path(profile) / "DevToolsActivePort"
                for _ in range(200):
                    if active.exists():
                        break
                    if process.poll() is not None:
                        raise RuntimeError("Chromium exited before startup")
                    await asyncio.sleep(0.05)
                if not active.exists():
                    raise RuntimeError("Chromium startup timed out")
                port = active.read_text().splitlines()[0]
                browser = await playwright.chromium.connect_over_cdp(
                    "http://127.0.0.1:" + port
                )
                framework_context = None
                framework_wrapper = None
                framework_actions = []
                if adapter == "browser-use":
                    from .browser_use_adapter import create_context

                    framework_wrapper, framework_context, context, page = (
                        await create_context(browser)
                    )
                else:
                    context = await browser.new_context(service_workers="block")
                    page = await context.new_page()
                await context.set_extra_http_headers({"X-Dispatch-Token": token})

                async def block_websocket(socket):
                    blocked_websockets.append(socket.url)
                    await socket.close(code=1008, reason="No websocket capability")

                await context.route_web_socket("**/*", block_websocket)

                async def route_request(route):
                    nonlocal injected
                    try:
                        valid = exact_origin(route.request.url) == allowed
                    except ValueError:
                        valid = False
                    if not valid:
                        blocked.append(route.request.url)
                        await route.abort()
                        return
                    if (
                        fault == "kill_after_commit"
                        and route.request.method == "POST"
                        and "/portal/action/" in route.request.url
                    ):
                        response = await route.fetch()
                        if response.status != 200:
                            raise RuntimeError("fault requires a committed transaction")
                        injected = True
                        os.killpg(process.pid, signal.SIGKILL)
                        return
                    await route.continue_()

                await context.route("**/*", route_request)
                page.set_default_timeout(5000)
                await page.goto(origin + "/portal/?action=" + action["id"])
                await page.locator("form[data-ready=true]").wait_for()
                if fault == "websocket_probe":
                    await page.evaluate(
                        "() => new Promise(resolve => { const s = new WebSocket('ws://127.0.0.1:9/'); s.onclose = resolve; s.onerror = resolve; })"
                    )
                isolated = await page.evaluate(
                    "localStorage.getItem('workbench-session') === null"
                )
                await page.evaluate(
                    "localStorage.setItem('workbench-session','present')"
                )
                if fault == "changed_layout":
                    await page.locator("label[for=quantity]").evaluate(
                        "e => e.textContent = 'Unexpected field'"
                    )
                if framework_context:
                    from .browser_use_adapter import submit

                    framework_actions = await submit(
                        framework_context, action["args"]["quantity"]
                    )
                else:
                    await page.get_by_label("Quantity", exact=True).fill(
                        str(action["args"]["quantity"])
                    )
                    if fault == "page_injection":
                        unauthorized_status = await page.evaluate(
                            "async id => (await fetch('/api/actions/'+id+'/approve',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({approved:true})})).status",
                            action["id"],
                        )
                        await page.get_by_label("Quantity", exact=True).fill("99")
                    await page.get_by_role(
                        "button", name="Submit approved operation", exact=True
                    ).click()
                await page.get_by_text("Receipt confirmed", exact=True).wait_for()
                receipt = json.loads(await page.locator("#receipt").inner_text())
                await context.close()
                await browser.close()
                return {
                    "status": "completed",
                    "receipt": receipt,
                    "blocked_requests": blocked,
                    "blocked_websockets": blocked_websockets,
                    "adapter": adapter,
                    "isolated": isolated,
                    "framework_actions": framework_actions,
                }
            except Exception as exc:
                if os.environ.get("WORKBENCH_DEBUG"):
                    import traceback

                    traceback.print_exc()
                if injected:
                    return {
                        "status": "outcome_unknown",
                        "fault": "SIGKILL after committed POST before browser response",
                        "blocked_requests": blocked,
                        "blocked_websockets": blocked_websockets,
                        "adapter": adapter,
                    }
                return {
                    "status": "outcome_unknown",
                    "reason": type(exc).__name__,
                    "unauthorized_status": unauthorized_status,
                    "blocked_requests": blocked,
                    "blocked_websockets": blocked_websockets,
                    "adapter": adapter,
                }
            finally:
                if process.poll() is None:
                    os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=5)
