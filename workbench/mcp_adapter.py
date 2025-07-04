"""Stdio MCP client for a narrow Playwright MCP compatibility profile."""

import asyncio
import json
import os
import pathlib
import re
import signal


async def run_mcp(origin, action, token):
    from .browser import exact_origin

    exact_origin(origin)
    script = (
        pathlib.Path(__file__).resolve().parent.parent
        / "adapters"
        / "playwright-mcp"
        / "server.cjs"
    )
    env = dict(os.environ, WORKBENCH_ORIGIN=origin, WORKBENCH_DISPATCH_TOKEN=token)
    process = await asyncio.create_subprocess_exec(
        "node",
        str(script),
        env=env,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        start_new_session=True,
    )
    sequence = 0
    steps = []

    async def request(method, params):
        nonlocal sequence
        sequence += 1
        message = {"jsonrpc": "2.0", "id": sequence, "method": method, "params": params}
        process.stdin.write((json.dumps(message) + "\n").encode())
        await process.stdin.drain()
        while True:
            raw = await asyncio.wait_for(process.stdout.readline(), 30)
            if not raw:
                raise RuntimeError("MCP peer closed")
            response = json.loads(raw)
            if response.get("id") == sequence:
                if "error" in response:
                    raise RuntimeError("MCP protocol error")
                return response["result"]

    async def tool(name, args):
        value = await request("tools/call", {"name": name, "arguments": args})
        if value.get("isError"):
            raise RuntimeError("MCP tool failed")
        steps.append(name)
        return "\n".join(c.get("text", "") for c in value.get("content", []))

    try:
        result = await request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "browser-workbench", "version": "0.1.0"},
            },
        )
        if result["protocolVersion"] != "2024-11-05":
            raise ValueError("unexpected MCP profile")
        process.stdin.write(b'{"jsonrpc":"2.0","method":"notifications/initialized"}\n')
        await process.stdin.drain()
        available = await request("tools/list", {})
        if not {"browser_navigate", "browser_type", "browser_click"} <= {
            x["name"] for x in available["tools"]
        }:
            raise ValueError("missing tools")
        snapshot = await tool(
            "browser_navigate", {"url": origin + "/portal/?action=" + action["id"]}
        )

        def reference(text, label):
            for line in text.splitlines():
                if label in line:
                    match = re.search(r"\[ref=([^\]]+)\]", line)
                    if match:
                        return match[1]
            raise ValueError("expected layout absent")

        quantity_ref = reference(snapshot, '"Quantity"')
        snapshot = await tool(
            "browser_type",
            {
                "element": "Quantity",
                "ref": quantity_ref,
                "text": str(action["args"]["quantity"]),
                "submit": False,
            },
        )
        submit_ref = reference(snapshot, '"Submit approved operation"')
        snapshot = await tool(
            "browser_click", {"element": "Submit approved operation", "ref": submit_ref}
        )
        if "Receipt confirmed" not in snapshot:
            raise ValueError("receipt not visible")
        receipt = None
        for line in snapshot.splitlines():
            if line.strip().startswith("- text: "):
                encoded = line.strip()[len("- text: ") :]
                try:
                    text = json.loads(encoded)
                    candidate = json.loads(text)
                    if isinstance(candidate, dict) and "action_id" in candidate:
                        receipt = candidate
                except (ValueError, TypeError):
                    continue
        if receipt is None:
            raise ValueError("receipt body missing")
        if receipt["action_id"] != action["id"] or receipt["args"] != action["args"]:
            raise ValueError("receipt mismatch")
        return {
            "status": "completed",
            "adapter": "playwright-mcp",
            "framework_actions": steps,
            "receipt": receipt,
            "protocol_version": result["protocolVersion"],
        }
    except Exception as exc:
        if os.environ.get("WORKBENCH_DEBUG"):
            import traceback

            traceback.print_exc()
        return {
            "status": "outcome_unknown",
            "adapter": "playwright-mcp",
            "framework_actions": steps,
            "reason": type(exc).__name__,
        }
    finally:
        process.stdin.close()
        try:
            await asyncio.wait_for(process.wait(), 5)
        except asyncio.TimeoutError:
            os.killpg(process.pid, signal.SIGKILL)
            await process.wait()
