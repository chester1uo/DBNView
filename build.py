#!/usr/bin/env python3
"""Inline src/spec.json + src/ui.html into a single self-contained dbnview.py."""
import base64, os, zlib

here = os.path.dirname(os.path.abspath(__file__))
src = open(os.path.join(here, "src", "core.py"), encoding="utf-8").read()


def blob(name):
    raw = open(os.path.join(here, "src", name), "rb").read()
    return base64.b64encode(zlib.compress(raw, 9)).decode()


for marker, name in (("_SPEC_B64 = None  # @@SPEC@@", "spec.json"), ("_HTML_B64 = None  # @@HTML@@", "ui.html")):
    assert marker in src, marker
    src = src.replace(marker, marker.split(" = ")[0] + ' = "' + blob(name) + '"')
out = os.path.join(here, "dbnview.py")
open(out, "w", encoding="utf-8").write(src)
os.chmod(out, 0o755)
print("wrote", out, os.path.getsize(out), "bytes")
