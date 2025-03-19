import asyncio
import os
import tempfile
import threading
import unittest
from workbench.server import create_server
from workbench.browser import run_browser

@unittest.skipUnless(os.environ.get('RUN_BROWSER_TESTS'),'requires Chromium')
class BrowserTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.server=create_server('127.0.0.1',0,self.tmp.name+'/db','browser-test');self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start();self.url='http://127.0.0.1:'+str(self.server.server_port)
    def tearDown(self):self.server.shutdown();self.server.server_close();self.thread.join();self.tmp.cleanup()
    def ready(self):
        s=self.server.store;a=s.propose('operator','purchase',{'sku':'WIDGET','quantity':2});s.approve(a['id'],'operator',a['args'],a['precondition']);return a,s.dispatch(a['id'],'operator')
    def test_real_browser_submits_and_observes_receipt(self):
        a,token=self.ready();r=asyncio.run(run_browser(self.url,a,token))
        self.assertEqual(r['status'],'completed');self.assertEqual(r['receipt']['action_id'],a['id']);self.assertEqual(self.server.store.snapshot('WIDGET')['available'],18)
    def test_sigkill_after_server_commit_recovers_without_duplicate(self):
        a,token=self.ready();r=asyncio.run(run_browser(self.url,a,token,fault='kill_after_commit'))
        self.assertEqual(r['status'],'outcome_unknown');self.assertEqual(r['fault'],'SIGKILL after committed POST before browser response')
        self.assertEqual(self.server.store.snapshot('WIDGET')['available'],18)
        recovered=self.server.store.reconcile(a['id'],'operator')
        self.assertEqual(recovered['status'],'completed')
        self.assertEqual(recovered['receipt']['action_id'],a['id'])
        self.assertEqual(self.server.store.snapshot('WIDGET')['available'],18)
    def test_changed_layout_stops_instead_of_guessing(self):
        a,token=self.ready();r=asyncio.run(run_browser(self.url,a,token,fault='changed_layout'))
        self.assertEqual(r['status'],'outcome_unknown');self.assertIsNone(self.server.store.get(a['id'],'operator')['receipt'])
    def test_isolated_sessions_do_not_share_previous_storage(self):
        a,token=self.ready();r=asyncio.run(run_browser(self.url,a,token))
        self.assertTrue(r['isolated']);a,token=self.ready();r=asyncio.run(run_browser(self.url,a,token));self.assertTrue(r['isolated'])
