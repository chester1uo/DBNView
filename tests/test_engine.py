import struct

import numpy as np
import pytest

import dbn_writer as W
from conftest import SEC, T0, mbo_rows
from dbnview.engine import FileInfo, metadata_layout, parse_metadata, parse_time
from dbnview.engine.sources import open_stream


def test_metadata_roundtrip(mbo_file):
    fh, st = open_stream(str(mbo_file))
    md = parse_metadata(st)
    fh.close()
    assert md["dataset"] == "GLBX.MDP3" and md["schema"] == "mbo"
    assert md["start"] == T0 and md["end"] == T0 + 60 * SEC
    assert md["stype_in"] == "continuous" and md["stype_out"] == "instrument_id"
    assert md["symbols"] == ["ES.v.0"]
    assert md["_mappings"] == [("ES.v.0", [(20251015, 20251016, "17077")])]
    lay = metadata_layout(md)
    assert lay[-1][1] == md["header_bytes"]          # byte map ends exactly where records start


def test_decode_all_rows(mbo_file, run_job):
    job = run_job(mbo_file, cap=1000)
    assert job.n == len(mbo_rows())
    res = job.rows(0, 3)
    o = dict(zip(res["columns"], res["rows"][1]))
    assert o["symbol"] == "ES.v.0" and o["action"] == "A" and o["side"] == "B"
    assert o["price"] == pytest.approx(4999.75) and o["size"] == 5
    clear = dict(zip(res["columns"], res["rows"][0]))
    assert clear["price"] is None                      # INT64_MAX sentinel -> None


def test_uncompressed_and_v4_rejected(tmp_path):
    p = W.write(tmp_path / "a.dbn", 3, "GLBX.MDP3", "mbo", T0, T0 + SEC, W.records("MBOMsg", 3, mbo_rows()[:2]),
                compress=False)
    assert FileInfo.get(str(p)).md["schema"] == "mbo"
    raw = bytearray(open(p, "rb").read())
    raw[3] = 4
    bad = tmp_path / "v4.dbn"
    bad.write_bytes(bytes(raw))
    with pytest.raises(ValueError, match="v4"):
        FileInfo.get(str(bad))


@pytest.mark.parametrize("query,expected", [
    ({"actions": ["A"]}, 5),
    ({"sides": ["A"]}, 4),
    ({"where": "size >= 5 and side == 'B'"}, 3),
    ({"where": "price > 5000"}, 1),
    ({"symbols": ["ES.v.0$"]}, 10),
    ({"symbols": ["NOPE"]}, 0),
    ({"iids": "17077"}, 10),
])
def test_filters(mbo_file, run_job, query, expected):
    assert run_job(mbo_file, cap=1000, **query).n == expected


def test_time_filter_and_seek(mbo_file, run_job):
    t0 = "2025-10-15 14:00:00.35"
    job = run_job(mbo_file, t0=t0, tz="UTC", cap=1000)
    assert job.n == len([r for r in mbo_rows() if r["ts_recv"] >= parse_time(t0, "UTC", None)])
    full = run_job(mbo_file, cap=1000)
    assert full.seek(parse_time("14:00:00.5", "UTC", T0)) == 4  # first row with ts_recv >= .5s


def test_cap_truncates(mbo_file, run_job):
    job = run_job(mbo_file, cap=4)
    assert job.n == 4 and job.truncated


def test_raw_layout(mbo_file, run_job):
    job = run_job(mbo_file, cap=10)
    raw = job.raw(1)
    data = bytes.fromhex(raw["hex"])
    assert data[0] * 4 == len(data) and data[1] == 0xA0
    fields = {f[0]: f for f in raw["layout"]}
    off = fields["price"][1]
    assert struct.unpack_from("<q", data, off)[0] == int(4999.75 * 1e9)


def test_counts_and_stats(trades_file, run_job):
    job = run_job(trades_file, cap=10_000)
    st = job.status(with_stats=True)
    assert st["matched"] == 600 and st["stats"]["top"][0][:2] == [7, 600]
    assert sum(c for _, c in st["stats"]["minutes"]) == 600
    assert np.isclose(sum(st["stats"]["side"].values()), 600)
