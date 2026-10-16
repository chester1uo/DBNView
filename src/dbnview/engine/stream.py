"""Streaming record decoder: runs of same-type records as numpy structured arrays."""
import threading

import numpy as np

from .records import record_type


def _prefetch(stream, chunk, depth=3):
    """Decompress on a background thread (zstd releases the GIL) while the caller parses."""
    import queue
    q = queue.Queue(maxsize=depth)
    stop = threading.Event()

    def work():
        try:
            while not stop.is_set():
                data = stream.read(chunk)
                q.put(data)
                if not data:
                    return
        except Exception as e:  # pragma: no cover
            q.put(e)

    threading.Thread(target=work, daemon=True).start()
    try:
        while True:
            data = q.get()
            if isinstance(data, Exception):
                raise data
            if not data:
                return
            yield data
    finally:
        stop.set()
        while not q.empty():
            q.get_nowait()


def iter_records(stream, version, ts_out, chunk=8 << 20, on_bytes=None, schema=None):
    """Yield (RecordType, ndarray) runs of same-type records from a decoded DBN body."""
    buf = b""
    for data in _prefetch(stream, chunk):
        buf = buf + data if buf else data
        if on_bytes:
            on_bytes()
        p, n = 0, len(buf)
        while n - p >= 16:
            L = buf[p] * 4
            if L < 16:
                raise ValueError("corrupt record header at decoded offset (length=%d)" % L)
            r = buf[p + 1]
            k = (n - p) // L
            if k == 0:
                break
            u8 = np.frombuffer(buf, np.uint8, count=k * L, offset=p).reshape(k, L)
            bad = (u8[:, 0] != buf[p]) | (u8[:, 1] != r)
            if bad.any():
                k = int(bad.argmax())
            rt = record_type(version, r, L, ts_out, schema)
            yield rt, np.frombuffer(buf, rt.dtype, count=k, offset=p)
            p += k * L
        buf = buf[p:]

