"""Smoke tests for the three front ends (skipped when their optional dependencies are missing)."""
import asyncio
import json
import os
import threading
import time
import urllib.request

import pytest


def test_web_api(mbo_file):
    from http.server import ThreadingHTTPServer
    from dbnview.web.server import App, Handler
    Handler.app = App([str(mbo_file.parent)], None, None)
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = "http://127.0.0.1:%d" % srv.server_address[1]
    try:
        get = lambda p: json.loads(urllib.request.urlopen(base + p).read())
        assert get("/api/init")["version"]
        req = urllib.request.Request(base + "/api/scan", json.dumps({"path": str(mbo_file), "query": {}}).encode(),
                                     {"Content-Type": "application/json"})
        jid = json.loads(urllib.request.urlopen(req).read())["id"]
        for _ in range(100):
            st = get("/api/job?id=%s" % jid)
            if st["done"]:
                break
            time.sleep(0.05)
        assert st["rows"] == 10
        assert len(get("/api/rows?id=%s&offset=0&limit=5" % jid)["rows"]) == 5
        assert get("/api/book?id=%s&row=9" % jid)["orders"] == 4
        assert b"<html" in urllib.request.urlopen(base + "/").read()[:200].lower()
    finally:
        srv.shutdown()


def test_tui_headless(option_file):
    pytest.importorskip("textual")
    pytest.importorskip("plotext")
    from dbnview.tui.app import DBNViewTUI

    async def run():
        app = DBNViewTUI(str(option_file), "UTC")
        async with app.run_test(size=(160, 45)) as pilot:
            for _ in range(100):
                await pilot.pause(0.05)
                if app.job is not None and app.job.done and app._final_done:
                    break
            assert app.job.n == 42
            await pilot.press("down", "2")
            await pilot.pause(0.3)
            assert app.row == 1
            for key in "34567":
                await pilot.press(key)
                await pilot.pause(0.5)
            for _ in range(60):
                if app.iv_surface is not None:
                    break
                await pilot.pause(0.1)
            assert app.iv_surface is not None and len(app.iv_surface["iv"]) > 10
            for _ in range(60):
                if app.walls_result is not None:
                    break
                await pilot.pause(0.1)
            assert app.walls_result is not None and app.walls_result["has_vol"] is False

    asyncio.run(run())


def test_gui_offscreen(trades_file):
    pytest.importorskip("PySide6")
    pytest.importorskip("pyqtgraph")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6 import QtWidgets
    from dbnview.gui.app import apply_lang
    from dbnview.gui.main_window import MainWindow
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    apply_lang("en")
    win = MainWindow()
    win.open_path(str(trades_file))
    t0 = time.time()
    while (win.job is None or not win.job.done or win.timer.isActive()) and time.time() - t0 < 30:
        app.processEvents()
        time.sleep(0.01)
    assert win.job.n == 600
    for i in range(win.tabs.count()):
        win.tabs.setCurrentIndex(i)
        app.processEvents()
    win.table.view.selectRow(3)
    app.processEvents()
    assert win.detail.row == 3
    win.close()
