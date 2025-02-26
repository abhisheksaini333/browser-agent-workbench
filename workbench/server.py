"""Loopback HTTP server for the workbench and owned transaction portal."""
import argparse
import hmac
import json
import os
import pathlib
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse
from .store import Store, Conflict, Forbidden

ROOT=pathlib.Path(__file__).resolve().parent.parent

def create_server(host,port,database,key):
    store=Store(database)
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def reply(self,status,data,content_type='application/json'):
            body=json.dumps(data).encode() if content_type=='application/json' else data.encode()
            self.send_response(status)
            for k,v in {'Content-Type':content_type,'Content-Length':str(len(body)),'X-Content-Type-Options':'nosniff','X-Frame-Options':'DENY','Cache-Control':'no-store','Content-Security-Policy':"default-src 'self'; script-src 'self'; style-src 'self'; frame-ancestors 'none'"}.items():self.send_header(k,v)
            self.end_headers();self.wfile.write(body)
        def authenticated(self):
            value=self.headers.get('Authorization','')
            return hmac.compare_digest(value,'Bearer '+key)
        def body(self):
            size=int(self.headers.get('Content-Length','0'))
            if size<0 or size>16384:raise ValueError('request too large')
            data=json.loads(self.rfile.read(size) or b'{}')
            if not isinstance(data,dict):raise ValueError('object required')
            return data
        def handle_request(self,method):
            path=urlparse(self.path).path
            if path=='/health':return self.reply(200,{'status':'ok'})
            if path.startswith('/portal/action/'):
                try:
                    action_id=path.rsplit('/',1)[-1];token=self.headers.get('X-Dispatch-Token','')
                    action=store.portal_action(action_id,token)
                    if method=='GET':return self.reply(200,action)
                    data=self.body();receipt=store.execute(action_id,token,data['args'])
                    return self.reply(200,receipt)
                except Forbidden as exc:return self.reply(403,{'error':str(exc)})
                except Conflict as exc:return self.reply(409,{'error':str(exc)})
                except (ValueError,KeyError,TypeError):return self.reply(400,{'error':'invalid submission'})
            if not self.authenticated():return self.reply(401,{'error':'authentication required'})
            try:
                if method=='GET' and path=='/api/actions':return self.reply(200,store.list_actions('operator'))
                if method=='GET' and path.startswith('/api/resources/'):
                    return self.reply(200,store.snapshot(path.rsplit('/',1)[-1]))
                if method=='POST' and path=='/api/actions':
                    data=self.body();return self.reply(201,store.propose('operator',data['kind'],data['args']))
                parts=path.strip('/').split('/')
                if len(parts)>=3 and parts[:2]==['api','actions']:
                    action_id=parts[2]
                    if method=='GET' and len(parts)==3:return self.reply(200,store.get(action_id,'operator'))
                    if method=='GET' and parts[-1]=='events':return self.reply(200,store.history(action_id,'operator'))
                    if method=='POST' and len(parts)==4:
                        data=self.body();verb=parts[-1]
                        if verb=='approve':return self.reply(200,store.approve(action_id,'operator',data['args'],data['precondition']))
                        if verb=='cancel':return self.reply(200,store.cancel(action_id,'operator'))
                        if verb=='reconcile':return self.reply(200,store.reconcile(action_id,'operator'))
                return self.reply(404,{'error':'not found'})
            except Forbidden as exc:return self.reply(403,{'error':str(exc)})
            except Conflict as exc:return self.reply(409,{'error':str(exc)})
            except (ValueError,KeyError,TypeError) as exc:return self.reply(400,{'error':'invalid request: '+str(exc)})
        def do_GET(self):self.handle_request('GET')
        def do_POST(self):self.handle_request('POST')
    server=ThreadingHTTPServer((host,port),Handler);server.store=store
    return server

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--host',default='127.0.0.1');parser.add_argument('--port',type=int,default=18120);parser.add_argument('--database',default='workbench.db');args=parser.parse_args()
    key=os.environ.get('WORKBENCH_KEY')
    if not key:raise SystemExit('Set WORKBENCH_KEY to a strong local operator secret')
    server=create_server(args.host,args.port,args.database,key)
    print(f'Workbench listening at http://{args.host}:{args.port}',flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()
if __name__=='__main__':main()
