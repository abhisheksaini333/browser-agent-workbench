import concurrent.futures
import multiprocessing
import os
import unittest
from workbench.store import Store

def transact(payload):
    dsn,action_id,token,args=payload
    return Store(dsn).execute(action_id,token,args)

@unittest.skipUnless(os.environ.get('TEST_POSTGRES_DSN'),'requires isolated PostgreSQL test database')
class PostgresTests(unittest.TestCase):
    def test_two_processes_share_exactly_one_effect(self):
        dsn=os.environ['TEST_POSTGRES_DSN'];store=Store(dsn)
        before=store.snapshot('WIDGET')['available']
        action=store.propose('postgres-test','inventory',{'sku':'WIDGET','quantity':2})
        store.approve(action['id'],'postgres-test',action['args'],action['precondition'])
        token=store.dispatch(action['id'],'postgres-test');payload=(dsn,action['id'],token,action['args'])
        with concurrent.futures.ProcessPoolExecutor(2,mp_context=multiprocessing.get_context('spawn')) as pool:
            results=list(pool.map(transact,[payload,payload]))
        self.assertEqual(results[0],results[1])
        self.assertEqual(Store(dsn).snapshot('WIDGET')['available'],before+2)
