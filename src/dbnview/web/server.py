"""Lightweight browser UI: a local HTTP server that serves static/ui.html and a JSON API over the engine.

Runs anywhere numpy + zstandard are installed (no Qt), which makes it handy on remote servers:

    dbnview-web /data/databento            # or: python -m dbnview.web /data/databento
    ssh -N -L 8765:localhost:8765 server    # then open the printed URL locally
    dbnview-web file.dbn.zst --head 20      # print the first rows in the terminal
"""
import argparse
import csv
import io
import json
import os
import secrets
import sys
import time
import urllib.parse
import webbrowser
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources

from .. import __version__
from ..analysis.book import book_at
from ..analysis.market import price_series
from ..engine import PUBLISHERS, FileInfo, Job, fmt_ts, get_tz, is_remote, list_dir, parse_time, split_remote


class App:
    def __init__(self, roots, token, open_path=None):
        self.roots = roots
        self.token = token
        self.open_path = open_path
        self.html = resources.files("dbnview.web").joinpath("static/ui.html").read_text(encoding="utf-8")


def _json(obj):
    return json.dumps(obj, separators=(",", ":"), default=str, allow_nan=False).encode()


class Handler(BaseHTTPRequestHandler):
    app: App = None
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):  # quiet
        pass

    def _send(self, code, body, ctype="application/json", extra=None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _authed(self, qs):
        tok = self.app.token
        if not tok:
            return True
        if qs.get("token", [None])[0] == tok:
            return True
        if self.headers.get("X-Token") == tok:
            return True
        c = SimpleCookie(self.headers.get("Cookie", ""))
        return "dbnview" in c and c["dbnview"].value == tok

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(u.query)
        if not self._authed(qs):
            return self._send(403, b"forbidden: open the URL with ?token=... printed in the terminal",
                              "text/plain")
        try:
            if u.path in ("/", "/index.html"):
                cookie = {"Set-Cookie": "dbnview=%s; HttpOnly; SameSite=Strict; Path=/" % self.app.token} \
                    if self.app.token else {}
                return self._send(200, self.app.html.encode(), "text/html; charset=utf-8", cookie)
            if u.path == "/favicon.ico":
                return self._send(204, b"", "image/x-icon")
            if u.path == "/api/export":
                return self._export(qs)
            fn = getattr(self, "api_" + u.path[5:], None) if u.path.startswith("/api/") else None
            if fn is None:
                return self._send(404, b'{"error":"not found"}')
            return self._send(200, _json(fn({k: v[0] for k, v in qs.items()})))
        except Exception as e:
            import traceback
            traceback.print_exc()
            return self._send(400, _json({"error": "%s: %s" % (type(e).__name__, e)}))

    def do_POST(self):
        u = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(u.query)
        if not self._authed(qs):
            return self._send(403, b'{"error":"forbidden"}')
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n) or b"{}")
        try:
            fn = getattr(self, "post_" + u.path[5:], None)
            if fn is None:
                return self._send(404, b'{"error":"not found"}')
            return self._send(200, _json(fn(body)))
        except Exception as e:
            import traceback
            traceback.print_exc()
            return self._send(400, _json({"error": "%s: %s" % (type(e).__name__, e)}))

    # --- api ---
    def api_init(self, q):
        return {"roots": self.app.roots, "open": self.app.open_path, "version": __version__,
                "cwd": os.getcwd(), "home": os.path.expanduser("~"), "publishers": PUBLISHERS}

    def api_ls(self, q):
        d = q.get("dir") or self.app.roots[0]
        if not is_remote(d):
            d = os.path.abspath(os.path.expanduser(d))
            if os.path.isfile(d):
                d = os.path.dirname(d)
        parent = d.rsplit("/", 1)[0] or "/"
        if is_remote(d) and len(split_remote(d)[1]) <= 1:
            parent = d
        return {"dir": d, "parent": parent, "entries": list_dir(d)}

    def api_meta(self, q):
        return FileInfo.get(q["path"]).to_json()

    def api_symbols(self, q):
        fi = FileInfo.get(q["path"])
        res = fi.symmap.search(q.get("q", ""))
        lim = int(q.get("limit", 50))
        return {"total": len(res), "items": [[n, ids[:5], len(ids)] for n, ids in res[:lim]]}

    def post_scan(self, body):
        old = body.get("cancel")
        if old and old in Job.jobs:
            Job.jobs[old].cancelled = True
        job = Job(body["path"], body.get("query") or {})
        return job.status()

    def _job(self, q):
        j = Job.jobs.get(q.get("id"))
        if j is None:
            raise KeyError("scan expired, run it again")
        return j

    def api_job(self, q):
        return self._job(q).status(with_stats=q.get("stats") == "1")

    def api_cancel(self, q):
        j = self._job(q)
        j.cancelled = True
        return j.status()

    def api_rows(self, q):
        j = self._job(q)
        cols = q.get("cols")
        return j.rows(int(q.get("offset", 0)), min(int(q.get("limit", 200)), 5000),
                      cols.split(",") if cols else None)

    def api_seek(self, q):
        j = self._job(q)
        ns = parse_time(q["t"], q.get("tz", "UTC"), j.tmin or j.fi.md["start"])
        return {"row": j.seek(ns)}

    def api_chart(self, q):
        j = self._job(q)
        iid = q.get("iid")
        if not iid:
            top = j.iid_counts.top(1)
            if not top:
                return {"x": [], "series": {}}
            iid = top[0][0]
        res = price_series(j, int(iid), int(q.get("max", 6000)))
        res["instrument_id"] = int(iid)
        res["symbol"] = j.fi.symmap.lookup(int(iid))
        return res

    def api_raw(self, q):
        return self._job(q).raw(int(q["row"]))

    def api_book(self, q):
        return book_at(self._job(q), int(q["row"]), int(q.get("depth", 20)))

    def _export(self, qs):
        j = self._job({k: v[0] for k, v in qs.items()})
        tzname = qs.get("tz", ["UTC"])[0]
        tz = get_tz(tzname)
        name = os.path.basename(j.fi.path).replace(".dbn.zst", "").replace(".dbn", "") + ".csv"
        self.send_response(200)
        self.send_header("Content-Type", "text/csv; charset=utf-8")
        self.send_header("Content-Disposition", 'attachment; filename="%s"' % name)
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()
        cols = j.columns

        def chunk(s):
            b = s.encode()
            self.wfile.write(b"%x\r\n%s\r\n" % (len(b), b))

        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(cols)
        for off in range(0, j.n, 20000):
            res = j.rows(off, 20000)
            for r in res["rows"]:
                w.writerow([fmt_ts(v, tz) if j.kinds.get(c) == "ts" and v is not None else
                            ("" if v is None else v) for c, v in zip(cols, r)])
            chunk(buf.getvalue())
            buf.seek(0)
            buf.truncate()
        chunk(buf.getvalue()) if buf.getvalue() else None
        self.wfile.write(b"0\r\n\r\n")


def print_head(path, n, tz):
    fi = FileInfo.get(path)
    md = fi.md
    print("%s  DBN v%d  %s  %s  %s -> %s  stype %s->%s  %d mappings" % (
        os.path.basename(path), md["version"], md["dataset"], md["schema"],
        fmt_ts(md["start"]), fmt_ts(md["end"]) if md["end"] else "?", md["stype_in"],
        md["stype_out"], len(md["_mappings"])))
    j = Job(path, {"cap": n})
    while not j.done:
        time.sleep(0.02)
    if j.error:
        sys.exit(j.error)
    res = j.rows(0, n)
    z = get_tz(tz)
    cols = [c for c in res["columns"]]
    table = [[fmt_ts(v, z) if j.kinds.get(c) == "ts" and v is not None else
              ("" if v is None else str(v)) for c, v in zip(cols, r)] for r in res["rows"]]
    w = [max([len(c)] + [len(r[i]) for r in table]) for i, c in enumerate(cols)]
    print("  ".join(c.rjust(w[i]) for i, c in enumerate(cols)))
    for r in table:
        print("  ".join(v.rjust(w[i]) for i, v in enumerate(r)))


def main(argv=None):
    ap = argparse.ArgumentParser(description="Databento DBN (.dbn/.dbn.zst) viewer")
    ap.add_argument("paths", nargs="*", help="file(s) or directories")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--host", default="127.0.0.1",
                    help="bind address (default localhost; use an ssh tunnel for remote boxes)")
    ap.add_argument("--no-token", action="store_true", help="disable the access token")
    ap.add_argument("--open", action="store_true", help="open a browser tab")
    ap.add_argument("--head", type=int, metavar="N", help="print the first N records and exit")
    ap.add_argument("--tz", default="America/New_York", help="timezone for --head output")
    a = ap.parse_args(argv)

    paths = [os.path.abspath(os.path.expanduser(p)) for p in a.paths] or [os.getcwd()]
    files = [p for p in paths if os.path.isfile(p)]
    if a.head:
        for p in files:
            print_head(p, a.head, a.tz)
        return
    roots = [p if os.path.isdir(p) else os.path.dirname(p) for p in paths]
    token = None if a.no_token else secrets.token_urlsafe(12)
    Handler.app = App(roots, token, files[0] if files else None)
    srv = None
    for port in range(a.port, a.port + 20):
        try:
            srv = ThreadingHTTPServer((a.host, port), Handler)
            break
        except OSError:
            continue
    if srv is None:
        sys.exit("no free port near %d" % a.port)
    srv.daemon_threads = True
    url = "http://%s:%d/%s" % ("localhost" if a.host in ("127.0.0.1", "0.0.0.0") else a.host,
                               srv.server_address[1], "?token=" + token if token else "")
    print("dbnview %s  ->  %s" % (__version__, url), flush=True)
    if a.host == "127.0.0.1" and os.environ.get("SSH_CONNECTION"):
        print("remote? on your laptop:  ssh -N -L %d:localhost:%d <this-host>  then open the URL"
              % (srv.server_address[1], srv.server_address[1]), flush=True)
    if a.open:
        webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass

