#!/usr/bin/env python3
"""Smoke-test a packaged DBNView: open a synthetic MBO file in self-test mode and check every tab was saved as a PNG.

    python tools/selftest_app.py dist/DBNView.app/Contents/MacOS/DBNView /tmp/smoke
    python tools/selftest_app.py "C:\\...\\DBNView\\DBNView.exe" smoke --tabs 6

Exits non-zero if the app fails, hangs past --timeout, or any of shot_0.png .. shot_<tabs-1>.png is missing or not a PNG.
"""
import argparse
import os
import struct
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import make_sample_dbn  # noqa: E402


def png_size(path):
    with open(path, "rb") as f:
        head = f.read(24)
    if len(head) < 24 or head[:8] != b"\x89PNG\r\n\x1a\n" or head[12:16] != b"IHDR":
        return None
    return struct.unpack(">II", head[16:24])


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("exe", help="the packaged DBNView executable")
    ap.add_argument("workdir", help="where the sample file and screenshots go")
    ap.add_argument("--tabs", type=int, default=6, help="number of tabs the main window has")
    ap.add_argument("--timeout", type=float, default=300)
    a = ap.parse_args()

    os.makedirs(a.workdir, exist_ok=True)
    sample = os.path.abspath(os.path.join(a.workdir, "sample.mbo.dbn.zst"))
    prefix = os.path.abspath(os.path.join(a.workdir, "shot"))
    make_sample_dbn.main(sample)
    for i in range(a.tabs):
        if os.path.exists("%s_%d.png" % (prefix, i)):
            os.remove("%s_%d.png" % (prefix, i))

    env = dict(os.environ, DBNVIEW_SELFTEST=prefix)
    print("running", a.exe, sample, flush=True)
    try:
        code = subprocess.run([a.exe, sample], env=env, timeout=a.timeout).returncode
    except subprocess.TimeoutExpired:
        sys.exit("FAIL: app did not quit within %.0f s" % a.timeout)
    ok = code == 0
    if not ok:
        print("FAIL: app exited with code %d" % code)
    for i in range(a.tabs):
        path = "%s_%d.png" % (prefix, i)
        size = png_size(path) if os.path.exists(path) else None
        if not size or 0 in size:
            ok = False
            print("FAIL: %s missing or not a valid PNG" % path)
        else:
            print("ok   %s %dx%d %d bytes" % (path, size[0], size[1], os.path.getsize(path)))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
