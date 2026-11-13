#!/usr/bin/env python3
import argparse
import json
import os
import sys
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from api.http_api import Api, MAX_BODY
from api.local_backend import LocalBackend
from api.state import State
from api.termux_backend import TermuxBackend

LOOPBACK = {"127.0.0.1", "localhost", "::1", "0:0:0:0:0:0:0:1"}


def make_handler(api):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt, *args):
            sys.stderr.write("gitgui: " + (fmt % args) + "\n")

        def _dispatch(self, method):
            length = int(self.headers.get("Content-Length") or 0)
            if length > MAX_BODY:
                self._send(413, {"error": "body too large"}, "application/json")
                return
            body = self.rfile.read(length) if length else b""
            parsed = urllib.parse.urlparse(self.path)
            query = urllib.parse.parse_qs(parsed.query)
            try:
                status, payload, ctype = api.route(method, self.path, query, self.headers, body)
            except Exception as e:
                status, payload, ctype = 500, {"error": str(e)}, "application/json"
            self._send(status, payload, ctype)

        def _send(self, status, payload, ctype):
            if isinstance(payload, (dict, list)):
                payload = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                ctype = "application/json"
            if isinstance(payload, str):
                payload = payload.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", ctype + "; charset=utf-8" if ctype.startswith("text") or ctype == "application/json" else ctype)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self):
            self._dispatch("GET")

        def do_POST(self):
            self._dispatch("POST")

    return Handler


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser(description="gitgui - generic git GUI backend server")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--token", default=None, help="bearer token; required when binding non-loopback")
    ap.add_argument("--backend", default="local", choices=["local", "termux"])
    ap.add_argument("--state-dir", default=os.path.join(os.path.expanduser("~"), ".gitgui"))
    ap.add_argument("--gui-dir", default=os.path.join(here, "gui"))
    args = ap.parse_args()

    if args.host not in LOOPBACK and not args.token:
        sys.exit("refusing to bind non-loopback host without --token (set a token for remote use)")

    state = State(args.state_dir)
    backend = LocalBackend(state) if args.backend == "local" else TermuxBackend(state)
    api = Api(backend, state, args.gui_dir, token=args.token)
    server = ThreadingHTTPServer((args.host, args.port), make_handler(api))
    url = f"http://{'127.0.0.1' if args.host in ('localhost', '::1') else args.host}:{args.port}/"
    print(f"gitgui backend={backend.name} state={state.root}")
    print(f"open {url}" + (f"  (token: {args.token})" if args.token else ""))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
