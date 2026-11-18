"""本地合成资料来源，仅提供来源行为与观察记录。"""
import argparse
from contextlib import contextmanager
import gzip
import hashlib
import html
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import socket
from pathlib import Path
import threading
from urllib.parse import parse_qs, urlsplit

DATA = Path(__file__).resolve().parents[1] / 'data'

class Source:
    def __init__(self):
        self.lock = threading.RLock()
        self.clock = 0
        self.phase = 0
        self.log = []
        self.extra = {}

    def response(self, method, raw_path, headers, body):
        path = urlsplit(raw_path).path
        q = {k:v[-1] for k,v in parse_qs(urlsplit(raw_path).query).items()}
        with self.lock:
            self.log.append({'method':method,'path':raw_path,'time':self.clock,
                             'headers':{k.lower():v for k,v in headers.items()}})
            if path == '/health': return 200, {}, {'来源':'本地合成资料','phase':self.phase,'time':self.clock}
            if path == '/__admin/log': return 200, {}, self.log[:-1]
            if path == '/__admin/advance' and method == 'POST':
                value=json.loads(body or b'{}')
                self.clock += int(value.get('seconds',0))
                self.phase = int(value.get('phase',self.phase))
                return 200, {}, {'phase':self.phase,'time':self.clock}
            if path.startswith('/__admin/'):
                return 404, {}, {'error':'未知演练控制'}
            return self.product(method,path,q,{k.lower():v for k,v in headers.items()},body)

    def records(self):
        rows=[{'id':'P-1','city':'城甲','year':2025,'blob':'/files/common','version':1},{'id':'P-2','city':'城乙','year':2024,'blob':'/files/other','version':1}]
        if self.phase:
            rows=[{'id':'P-3','city':'城甲','year':2025,'blob':'/files/common','version':1},rows[1]]
        if self.phase>=2:rows[1].update(year=2025,version=2)
        return rows
    def product(self,method,path,q,h,body):
        snaps=self.extra.setdefault('snapshots',{})
        if path=='/snapshot' and method=='POST':
            token='S-'+str(len(snaps)+1);snaps[token]={'rows':self.records(),'position':self.phase,'expiry':self.clock+20}
            return 201,{}, {'token':token,'position':self.phase,'next':'/snapshot/'+token+'?page=0','expires_at':self.clock+20}
        if path.startswith('/snapshot/'):
            token=path.rsplit('/',1)[-1];snap=snaps.get(token)
            if not snap or self.clock>=snap['expiry']:return 410,{}, {'error':'快照过期'}
            i=int(q.get('page','0'));items=snap['rows'][i:i+1]
            return 200,{}, {'token':token,'position':snap['position'],'items':items,'next':('/snapshot/'+token+'?page='+str(i+1)) if i+1<len(snap['rows']) else None}
        if path=='/changes':
            after=int(q.get('after','0')); floor=max(0,self.phase-1)
            if after<floor:return 410,{}, {'error':'位置已淘汰','floor':floor}
            changes=[]
            if self.phase>=1 and after<1:
                changes.append({'position':1,'changes':[{'op':'delete','id':'P-1'},{'op':'upsert',**self.records()[0]}]})
            if self.phase>=2 and after<2:
                changes.append({'position':2,'changes':[{'op':'upsert','id':'P-2','city':'城乙','year':2025,'blob':'/files/other','version':2}]})
            return 200,{}, {'after':after,'through':self.phase,'commits':changes}
        if path.startswith('/files/'):
            return 200,{'Content-Type':'text/plain','ETag':'"'+path.rsplit('/',1)[-1]+'"'},('公开政策 '+path).encode()
        return 404,{}, {'error':'无此目录入口'}

class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'
    def log_message(self,*args): pass
    def do_GET(self): self.handle_request()
    def do_POST(self): self.handle_request()
    def handle_request(self):
        size=int(self.headers.get('Content-Length','0'))
        try:
            status,headers,body=self.server.source.response(self.command,self.path,self.headers,self.rfile.read(size))
            if not isinstance(body,(str,bytes)):
                body=json.dumps(body,ensure_ascii=False).encode();headers.setdefault('Content-Type','application/json; charset=utf-8')
            elif isinstance(body,str):
                body=body.encode();headers.setdefault('Content-Type','text/html; charset=utf-8')
        except (ValueError,KeyError,TypeError) as exc:
            status,headers,body=400,{'Content-Type':'application/json'},json.dumps({'error':str(exc)},ensure_ascii=False).encode()
        if status==0:
            self.close_connection=True
            self.connection.shutdown(socket.SHUT_RDWR)
            self.connection.close()
            return
        self.send_response(status)
        for k,v in headers.items():self.send_header(k,str(v))
        self.send_header('Content-Length',len(body))
        self.end_headers()
        if body:self.wfile.write(body)

@contextmanager
def running_source(port=0):
    server=ThreadingHTTPServer(('127.0.0.1',port),Handler)
    server.source=Source()
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try: yield 'http://127.0.0.1:'+str(server.server_port),server.source
    finally: server.shutdown();server.server_close();thread.join()

if __name__=='__main__':
    parser=argparse.ArgumentParser(description='启动本地资料来源')
    parser.add_argument('--port',type=int,default=8765)
    args=parser.parse_args()
    server=ThreadingHTTPServer(('0.0.0.0',args.port),Handler);server.source=Source()
    print('资料来源已启动，端口 '+str(args.port),flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()
