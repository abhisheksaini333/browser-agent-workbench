import os
import tempfile
import threading
import unittest
from workbench.server import create_server

@unittest.skipUnless(os.environ.get('RUN_UI_TESTS'),'requires built frontend and Chromium')
class UITests(unittest.TestCase):
    def test_operator_proposes_approves_and_runs_action(self):
        from playwright.sync_api import sync_playwright
        with tempfile.TemporaryDirectory() as tmp:
            server=create_server('127.0.0.1',0,tmp+'/db','ui-fixture');thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            try:
                with sync_playwright() as p:
                    browser=p.chromium.launch(executable_path=os.environ.get('CHROMIUM_PATH','/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'),headless=True)
                    page=browser.new_page();page.goto('http://127.0.0.1:'+str(server.server_port))
                    page.get_by_label('Operator key').fill('ui-fixture');page.get_by_role('button',name='Open workspace').click()
                    page.get_by_label('Task').fill('purchase 2 WIDGET');page.get_by_role('button',name='Propose action',exact=True).click()
                    page.get_by_role('button',name='Approve exact action',exact=True).click()
                    page.get_by_role('button',name='Run approved action',exact=True).click()
                    page.get_by_label('Action detail').get_by_text('Receipt confirmed',exact=True).wait_for(timeout=20000)
                    self.assertEqual(server.store.snapshot('WIDGET')['available'],18)
                    page.set_viewport_size({'width':390,'height':844})
                    self.assertTrue(page.evaluate('document.documentElement.scrollWidth <= innerWidth'))
                    browser.close()
            finally:server.shutdown();server.server_close();thread.join()
