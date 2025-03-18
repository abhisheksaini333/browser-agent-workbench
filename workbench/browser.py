"""Isolated browser execution against one exact owned origin."""
import asyncio
import json
import os
import pathlib
import subprocess
import tempfile
from urllib.parse import urlsplit

def exact_origin(url):
    parsed=urlsplit(url)
    if parsed.username or parsed.password or parsed.scheme not in ('http','https'):
        raise ValueError('invalid origin')
    if parsed.hostname not in ('127.0.0.1','localhost'):
        raise ValueError('only owned loopback portals are allowed')
    return parsed.scheme,parsed.hostname,parsed.port or (443 if parsed.scheme=='https' else 80)

async def run_browser(origin,action,token,*,adapter='playwright',fault=None):
    from playwright.async_api import async_playwright
    allowed=exact_origin(origin);blocked=[];injected=False
    async with async_playwright() as playwright:
        executable=os.environ.get('CHROMIUM_PATH') or ('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' if pathlib.Path('/Applications/Google Chrome.app').exists() else playwright.chromium.executable_path)
        with tempfile.TemporaryDirectory(prefix='workbench-browser-') as profile:
            process=subprocess.Popen([executable,'--headless=new','--remote-debugging-port=0','--user-data-dir='+profile,'--no-first-run','--no-default-browser-check','--disable-background-networking','--no-sandbox'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            try:
                active=pathlib.Path(profile)/'DevToolsActivePort'
                for _ in range(200):
                    if active.exists():break
                    if process.poll() is not None:raise RuntimeError('Chromium exited before startup')
                    await asyncio.sleep(.05)
                if not active.exists():raise RuntimeError('Chromium startup timed out')
                port=active.read_text().splitlines()[0]
                browser=await playwright.chromium.connect_over_cdp('http://127.0.0.1:'+port)
                context=await browser.new_context(service_workers='block')
                await context.set_extra_http_headers({'X-Dispatch-Token':token})
                async def route_request(route):
                    nonlocal injected
                    try:valid=exact_origin(route.request.url)==allowed
                    except ValueError:valid=False
                    if not valid:blocked.append(route.request.url);await route.abort();return
                    if fault=='kill_after_commit' and route.request.method=='POST' and '/portal/action/' in route.request.url:
                        response=await route.fetch()
                        if response.status!=200:raise RuntimeError('fault requires a committed transaction')
                        injected=True
                        process.kill()
                        return
                    await route.continue_()
                await context.route('**/*',route_request)
                page=await context.new_page();page.set_default_timeout(5000)
                await page.goto(origin+'/portal/?action='+action['id'])
                await page.locator('form[data-ready=true]').wait_for()
                await page.get_by_label('Quantity',exact=True).fill(str(action['args']['quantity']))
                await page.get_by_role('button',name='Submit approved operation',exact=True).click()
                await page.get_by_text('Receipt confirmed',exact=True).wait_for()
                receipt=json.loads(await page.locator('#receipt').inner_text())
                await context.close()
                return {'status':'completed','receipt':receipt,'blocked_requests':blocked,'adapter':adapter}
            except Exception:
                if injected:return {'status':'outcome_unknown','fault':'SIGKILL after committed POST before browser response','blocked_requests':blocked,'adapter':adapter}
                raise
            finally:
                if process.poll() is None:process.kill()
                process.wait(timeout=5)
