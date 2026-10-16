#!/usr/bin/env python3
"""Build dist/dbnview-web.pyz: a single-file browser UI for servers (needs only numpy + zstandard).

    python tools/build_web_pyz.py
    scp dist/dbnview-web.pyz server: && ssh server python3 dbnview-web.pyz /data/databento
"""
import os
import shutil
import tempfile
import zipapp

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKG = os.path.join(ROOT, "src", "dbnview")
SKIP = {"gui", "tui", "__pycache__"}  # Qt / Textual front ends are not needed on a server


def main():
    out = os.path.join(ROOT, "dist", "dbnview-web.pyz")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        shutil.copytree(PKG, os.path.join(tmp, "dbnview"),
                        ignore=lambda d, names: [n for n in names if n in SKIP or n.endswith(".pyc")])
        with open(os.path.join(tmp, "__main__.py"), "w") as f:
            f.write("from dbnview.web.server import main\n\nmain()\n")
        zipapp.create_archive(tmp, out, interpreter="/usr/bin/env python3", compressed=True)
    print("wrote", out, os.path.getsize(out), "bytes")


if __name__ == "__main__":
    main()
