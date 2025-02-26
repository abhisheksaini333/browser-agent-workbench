import json
import tempfile
import threading
import unittest
import urllib.request
import urllib.error
from workbench.server import create_server

class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.server=create_server('127.0.0.1',0,self.temp.name+'/db','test-key')
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start();self.url='http://127.0.0.1:'+str(self.server.server_port)
    def tearDown(self):self.server.shutdown();self.server.server_close();self.thread.join();self.temp.cleanup()
    def request(self,path,data=None,key='test-key'):
        req=urllib.request.Request(self.url+path,data=json.dumps(data).encode() if data is not None else None,headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'})
        with urllib.request.urlopen(req) as response:return json.load(response)
    def test_authenticated_proposal_and_listing(self):
        with self.assertRaises(urllib.error.HTTPError) as err:self.request('/api/actions',key='bad')
        self.assertEqual(err.exception.code,401)
        a=self.request('/api/actions',{'kind':'purchase','args':{'sku':'WIDGET','quantity':2}})
        self.assertEqual(self.request('/api/actions')[0]['id'],a['id'])
        self.assertNotIn('dispatch',a)
    def test_portal_capability_scoped_to_one_action(self):
        a=self.server.store.propose('operator','purchase',{'sku':'WIDGET','quantity':2})
        self.server.store.approve(a['id'],'operator',a['args'],a['precondition'])
        token=self.server.store.dispatch(a['id'],'operator')
        req=urllib.request.Request(self.url+'/portal/action/'+a['id'],headers={'X-Dispatch-Token':token})
        with urllib.request.urlopen(req) as r:self.assertEqual(json.load(r)['args'],a['args'])
        req=urllib.request.Request(self.url+'/portal/action/'+a['id'],headers={'X-Dispatch-Token':'bad'})
        with self.assertRaises(urllib.error.HTTPError) as err:urllib.request.urlopen(req)
        self.assertEqual(err.exception.code,403)
