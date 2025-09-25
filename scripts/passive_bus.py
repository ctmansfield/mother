#!/usr/bin/env python3
import json
import os
import time
import argparse
from http.server import BaseHTTPRequestHandler, HTTPServer


def load_yaml(path):
    try:
        import yaml

        with open(path, "r") as f:
            return yaml.safe_load(f)
    except Exception:
        return {}


def ensure_header(path):
    if os.path.exists(path):
        return
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as f:
        f.write("ts,event,value,category\n")


class Handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.send_header("Access-Control-Allow-Methods", "POST,OPTIONS")
        self.end_headers()

    def do_POST(self):
        if self.path not in ("/event", "/v1/event"):
            self.send_response(404)
            self.end_headers()
            return
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length or 0)
        try:
            data = json.loads(body.decode("utf-8") or "{}")
        except Exception:
            data = {}
        cfg = (load_yaml("content/passive_actions.yaml") or {}).get("passive", {})
        evmap = cfg.get("map") or {}
        ts = int(data.get("ts") or time.time())
        event = str(data.get("event") or "")
        value = str(data.get("value") or "1")
        cat = str(data.get("category") or evmap.get(event, ""))
        ensure_header("out/passive_actions.csv")
        ok = False
        if ts and event:
            with open("out/passive_actions.csv", "a") as f:
                f.write(f"{ts},{event},{value},{cat}\n")
            ok = True
        resp = {"ok": ok, "ts": ts, "event": event, "category": cat}
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(resp).encode("utf-8"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    args = ap.parse_args()
    srv = HTTPServer(("0.0.0.0", args.port), Handler)
    print(json.dumps({"listening": args.port}))
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
