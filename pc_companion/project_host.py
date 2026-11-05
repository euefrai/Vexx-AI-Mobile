"""Project-local static HTTP host. Never serve dotfiles, links or files outside the root."""
import argparse
import json
import os
from pathlib import Path
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlsplit


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--root',required=True);parser.add_argument('--port',type=int,required=True);parser.add_argument('--nonce',required=True)
    args=parser.parse_args();root=Path(args.root).resolve()
    class Handler(SimpleHTTPRequestHandler):
        extensions_map={**SimpleHTTPRequestHandler.extensions_map,'.js':'text/javascript','.mjs':'text/javascript','.css':'text/css'}
        def __init__(self,*a,**kw):super().__init__(*a,directory=str(root),**kw)
        def serve(self,head=False):
            try:
                host=urlsplit('http://'+self.headers.get('Host',''));valid_host=host.hostname in ('127.0.0.1','localhost','::1') and host.port==args.port
            except ValueError:valid_host=False
            origin=self.headers.get('Origin')
            if not valid_host or (origin and origin not in ('http://127.0.0.1:'+str(args.port),'http://localhost:'+str(args.port))) or self.headers.get('Sec-Fetch-Site')=='cross-site':
                self.send_error(403);return
            if urlsplit(self.path).path=='/_vexx_health':
                body=json.dumps({'service':'vexx-project-host','nonce':args.nonce,'pid':os.getpid()}).encode()
                self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(body)));self.end_headers()
                if not head:self.wfile.write(body)
                return
            parts=unquote(urlsplit(self.path).path).replace('\\','/').split('/')
            if any(p.startswith('.') or ':' in p for p in parts if p) or 'node_modules' in parts:
                self.send_error(403);return
            candidate=root.joinpath(*[p for p in parts if p])
            try:
                if candidate.is_dir():candidate=candidate/'index.html'
                if not candidate.resolve().is_relative_to(root):raise ValueError()
                for part in (candidate,*candidate.parents):
                    if part==root:break
                    if part.is_symlink() or getattr(os.path,'isjunction',lambda _:False)(part):raise ValueError()
                if not candidate.is_file():raise ValueError()
            except (OSError,ValueError):self.send_error(403);return
            if head:super().do_HEAD()
            else:super().do_GET()
        def do_GET(self):self.serve()
        def do_HEAD(self):self.serve(head=True)
    server=ThreadingHTTPServer(('127.0.0.1',args.port),Handler)
    print('Vexx static host ready',flush=True)
    server.serve_forever()


if __name__=='__main__':main()
