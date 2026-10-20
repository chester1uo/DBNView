import os
import time

import numpy as np
import pytest

import dbn_writer as W
from conftest import SEC, T0, wait
from dbnview.analysis import replay
from dbnview.analysis.book import OrderBook
from dbnview.engine import Job

N_EVENTS = 30_000


def nasdaq_rows(n=N_EVENTS, seed=7):
    """A random single-instrument Nasdaq-style day: adds, partial/full cancels and trades, one event per record."""
    rng = np.random.default_rng(seed)
    rows, live, oid, t = [], {}, 1, T0
    for i in range(n):
        t += int(rng.integers(1_000, 2_000_000))
        r = rng.random()
        if r < 0.5 or len(live) < 20:
            side = "B" if rng.random() < 0.5 else "A"
            px = round(100 + (-1 if side == "B" else 1) * (0.01 + 0.01 * int(rng.integers(0, 15))), 2)
            sz = int(rng.integers(1, 20)) * 100
            live[oid] = (side, px, sz)
            rows.append(dict(action="A", side=side, price=px, size=sz, order_id=oid))
            oid += 1
        elif r < 0.9:
            k = list(live)[int(rng.integers(0, len(live)))]
            side, px, sz = live[k]
            cut = sz if rng.random() < 0.6 else int(rng.integers(1, max(2, sz)))
            live[k] = (side, px, sz - cut)
            if live[k][2] <= 0:
                del live[k]
            rows.append(dict(action="C", side=side, price=px, size=cut, order_id=k))
        else:
            rows.append(dict(action="T", side="B" if rng.random() < 0.5 else "A", price=100.0, size=100, order_id=0))
        rows[-1].update(ts_event=t - 500, ts_recv=t, instrument_id=7, publisher_id=2, flags=128, sequence=i)
    return rows


@pytest.fixture(scope="module")
def nasdaq_file(tmp_path_factory):
    p = tmp_path_factory.mktemp("replay") / "TEST.mbo.dbn.zst"
    return W.write(p, 3, "XNAS.ITCH", "mbo", T0, T0 + 86_400 * SEC, W.records("MBOMsg", 3, nasdaq_rows()),
                   symbols=["TEST"], mappings=[("TEST", [(20251015, 20251016, "7")])])


@pytest.fixture(scope="module")
def loaded(nasdaq_file):
    job = wait(Job(str(nasdaq_file), {"cap": 1_000_000}))
    return job, replay.LoadedReplay(job)


def reference(job, pos):
    book = OrderBook()
    recs = np.concatenate([p for _, p, _ in job.iter_instrument(7)])[:pos]
    book.apply_records(recs)
    return book.depth(5)


def levels(snap):
    return [(round(p, 6), s, c) for p, s, c, _ in snap["bids"]], [(round(p, 6), s, c) for p, s, c, _ in snap["asks"]]


def test_loaded_replay_matches_a_fresh_book_in_any_seek_order(loaded, monkeypatch):
    job, _ = loaded
    monkeypatch.setattr(replay.LoadedReplay, "CKPT", 1_000)  # many checkpoints: restore, continue and backward seeks
    lr2 = replay.LoadedReplay(job)
    assert len(lr2.ckpts) == N_EVENTS // 1_000
    positions = list(np.random.default_rng(3).integers(0, N_EVENTS + 1, 25)) + [0, 1, N_EVENTS, N_EVENTS, 5]
    for pos in positions:
        snap = lr2.seek_pos(int(pos), depth=5)
        assert snap["pos"] == pos
        bids, asks = reference(job, int(pos))
        assert levels(snap) == ([(round(p, 6), s, c) for p, s, c in bids], [(round(p, 6), s, c) for p, s, c in asks])


def test_seek_by_time_is_the_state_after_all_events_up_to_then(loaded):
    _, lr = loaded
    t = int(lr.ts[12_345])
    assert lr.seek(t)["pos"] == 12_346
    assert lr.seek(t - 1)["pos"] == 12_345
    assert lr.seek(lr.t0 - 10)["pos"] == 0 and lr.seek(lr.t1 + 10)["pos"] == N_EVENTS
    tr = lr.trades(lr.t0, lr.t1)
    assert len(tr["t"]) == int((lr.recs["action"] == b"T").sum())
    assert len(lr.events(100, 40)) == 40 and len(lr.events(3, 40)) == 3


def test_queues_list_resting_orders_in_arrival_order(loaded):
    _, lr = loaded
    snap = lr.seek_pos(20_000, depth=3, queues=True)
    for p, size, count, orders in snap["bids"] + snap["asks"]:
        assert len(orders) == count and sum(s for _, s in orders) == size
        assert [o for o, _ in orders] == sorted(o for o, _ in orders)  # Nasdaq: no modifies, so arrival order


def test_wasr_backend_agrees_exactly_and_reuses_its_index(nasdaq_file, loaded, tmp_path, monkeypatch):
    pytest.importorskip("wasr")
    monkeypatch.setenv("DBNVIEW_CACHE_DIR", str(tmp_path))
    stages = []
    wr, note = replay.open_replay(str(nasdaq_file), progress=lambda *a: stages.append(a[0]))
    assert isinstance(wr, replay.WasrReplay) and note == "" and "index" in stages
    _, lr = loaded
    assert (wr.n_events, wr.t0, wr.t1) == (lr.n_events, lr.t0, lr.t1)
    for pos in list(np.random.default_rng(5).integers(0, N_EVENTS + 1, 30)) + [N_EVENTS, 0]:
        a, b = wr.seek_pos(int(pos), depth=5, queues=True), lr.seek_pos(int(pos), depth=5, queues=True)
        assert a["pos"] == b["pos"] and a["n_orders"] == b["n_orders"]
        assert levels(a) == levels(b)
        assert [lv[3] for lv in a["bids"] + a["asks"]] == [lv[3] for lv in b["bids"] + b["asks"]]  # same queues
    t = int(lr.ts[777])
    assert wr.seek(t)["pos"] == lr.seek(t)["pos"]
    assert np.array_equal(wr.events(500, 10)["order_id"], lr.events(500, 10)["order_id"])
    assert len(wr.trades(lr.t0, lr.t1)["t"]) == len(lr.trades(lr.t0, lr.t1)["t"])
    files = os.listdir(tmp_path)
    mtime = os.path.getmtime(os.path.join(tmp_path, files[0]))
    again, _ = replay.open_replay(str(nasdaq_file))
    assert os.listdir(tmp_path) == files and os.path.getmtime(os.path.join(tmp_path, files[0])) == mtime


def test_without_wasr_the_loaded_rows_are_used(nasdaq_file, loaded, monkeypatch):
    monkeypatch.setattr(replay, "wasr_available", lambda: False)
    job, _ = loaded
    r, note = replay.open_replay(str(nasdaq_file), job)
    assert isinstance(r, replay.LoadedReplay) and "not installed" in note
    with pytest.raises(RuntimeError):
        replay.open_replay(str(nasdaq_file), None)


def test_replay_window(nasdaq_file, monkeypatch):
    pytest.importorskip("PySide6")
    pytest.importorskip("pyqtgraph")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6 import QtWidgets
    from dbnview.gui.app import apply_lang
    from dbnview.gui.main_window import MainWindow
    monkeypatch.setattr(replay, "wasr_available", lambda: False)  # same code path everywhere, no index build
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    apply_lang("en")
    win = MainWindow()
    win.open_path(str(nasdaq_file))
    t0 = time.time()
    while (win.job is None or not win.job.done or not win.a_replay.isEnabled()) and time.time() - t0 < 30:
        app.processEvents()
        time.sleep(0.01)
    assert win.a_replay.isEnabled()
    win.open_replay()
    rw = win._replays[-1]
    while rw.r is None and time.time() - t0 < 60:
        app.processEvents()
        time.sleep(0.01)
    assert rw.r is not None and rw.snap is not None and rw.ladder.snap is rw.snap
    pos = rw.snap["pos"]
    rw.step_event(1)
    assert rw.snap["pos"] == pos + 1
    rw.step_event(-1)
    assert rw.snap["pos"] == pos
    rw.queues.setChecked(True)
    assert all(lv[3] is not None for lv in rw.snap["bids"])
    rw.time_edit.setText(win.tsfmt.fmt(rw.r.t1, "dt"))
    rw.jump()
    assert rw.snap["pos"] == N_EVENTS and rw.tape.rowCount() == 40
    rw.seek(rw.r.t0)
    rw.play()
    rw._last -= 1.0  # one second of wall time at 10x
    rw.speed.setCurrentIndex(rw.speed.findData(10))
    rw._frame()
    assert rw.t > rw.r.t0 + 9 * SEC
    rw.pause()
    assert not rw.ladder.grab().isNull()
    rw.close()
    win.close()
    app.processEvents()
