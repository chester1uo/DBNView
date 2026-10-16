"""DBN metadata header: parsing (v1-v3) and a byte map for the format guide."""
import struct

from .constants import SCHEMAS, STYPES, UNDEF_TS


def _readn(f, n):
    out = bytearray()
    while len(out) < n:
        b = f.read(n - len(out))
        if not b:
            break
        out += b
    return bytes(out)


def _cstr(b):
    return b.split(b"\0", 1)[0].decode("utf-8", "replace")


def parse_metadata(f):
    head = _readn(f, 8)
    if len(head) < 8 or head[:3] != b"DBN":
        raise ValueError("not a DBN stream (missing 'DBN' magic)")
    ver = head[3]
    if ver > 3:
        raise ValueError("DBN v%d is not supported yet (this viewer reads v1-v3)" % ver)
    (n,) = struct.unpack("<I", head[4:8])
    b = _readn(f, n)
    md = {"version": ver, "dataset": _cstr(b[0:16])}
    (schema,) = struct.unpack_from("<H", b, 16)
    start, end, limit = struct.unpack_from("<QQQ", b, 18)
    p = 42
    if ver == 1:
        (md["record_count"],) = struct.unpack_from("<Q", b, p)
        p += 8
    stype_in, stype_out, ts_out = b[p], b[p + 1], b[p + 2]
    p += 3
    if ver >= 2:
        (cl,) = struct.unpack_from("<H", b, p)
        p += 2 + 53
    else:
        cl = 22
        p += 47
    (sdl,) = struct.unpack_from("<I", b, p)
    p += 4 + sdl

    def strs():
        nonlocal p
        (cnt,) = struct.unpack_from("<I", b, p)
        p += 4
        out = [_cstr(b[p + i * cl:p + (i + 1) * cl]) for i in range(cnt)]
        p += cnt * cl
        return out

    md["symbols"], md["partial"], md["not_found"] = strs(), strs(), strs()
    (cnt,) = struct.unpack_from("<I", b, p)
    p += 4
    mappings = []
    for _ in range(cnt):
        raw = _cstr(b[p:p + cl])
        p += cl
        (icnt,) = struct.unpack_from("<I", b, p)
        p += 4
        ivs = []
        for _ in range(icnt):
            sd, ed = struct.unpack_from("<II", b, p)
            p += 8
            ivs.append((sd, ed, _cstr(b[p:p + cl])))
            p += cl
        mappings.append((raw, ivs))
    md.update(
        schema=None if schema == 0xFFFF else (SCHEMAS[schema] if schema < len(SCHEMAS) else str(schema)),
        start=start, end=None if end == UNDEF_TS else end,
        limit=limit, stype_in=None if stype_in == 255 else STYPES[stype_in] if stype_in < len(STYPES) else stype_in,
        stype_out=STYPES[stype_out] if stype_out < len(STYPES) else stype_out,
        ts_out=bool(ts_out), symbol_cstr_len=cl, header_bytes=8 + n)
    md["_mappings"] = mappings
    return md


def metadata_layout(md, t=lambda s: s):
    """Byte map of the DBN metadata header for this file (offsets from file start, decoded)."""
    v, cl = md["version"], md["symbol_cstr_len"]
    L = [["magic", 0, 3, "char[3]", "DBN"], ["version", 3, 1, "u8", v],
         ["length", 4, 4, "u32", md["header_bytes"] - 8],
         ["dataset", 8, 16, "char[16]", md["dataset"]], ["schema", 24, 2, "u16", md["schema"] or "mixed (0xFFFF)"],
         ["start", 26, 8, "u64", str(md["start"])],
         ["end", 34, 8, "u64", str(md["end"]) if md["end"] is not None else "UNDEF"],
         ["limit", 42, 8, "u64", md["limit"]]]
    p = 50
    if v == 1:
        L.append(["record_count", 50, 8, "u64", md.get("record_count")])
        p = 58
    L += [["stype_in", p, 1, "u8", md["stype_in"]], ["stype_out", p + 1, 1, "u8", md["stype_out"]],
          ["ts_out", p + 2, 1, "u8", int(md["ts_out"])]]
    p += 3
    if v >= 2:
        L.append(["symbol_cstr_len", p, 2, "u16", cl])
        p += 2
        L.append(["_reserved", p, 53, "bytes", ""])
        p += 53
    else:
        L.append(["_reserved", p, 47, "bytes", t("(v1: symbol length fixed at 22)")])
        p += 47
    L.append(["schema_definition_length", p, 4, "u32", 0])
    p += 4
    for name in ("symbols", "partial", "not_found"):
        n = len(md[name])
        L.append([name, p, 4 + n * cl, "u32 + %d×char[%d]" % (n, cl),
                  ", ".join(md[name][:5]) + (" …" if n > 5 else "")])
        p += 4 + n * cl
    mb = 4 + sum(cl + 4 + len(ivs) * (8 + cl) for _, ivs in md["_mappings"])
    ex = md["_mappings"][0] if md["_mappings"] else None
    L.append(["mappings", p, mb, t("u32 + each: char[{cl}] raw_symbol, u32 n, n×(u32 start_date, u32 end_date, char[{cl}])").format(cl=cl),
              t("{n} entries").format(n=len(md["_mappings"])) +
              (t("; e.g. {a} → {b}").format(a=ex[0], b=ex[1][0][2]) if ex and ex[1] else "")])
    p += mb
    if p < md["header_bytes"]:
        L.append(["(padding)", p, md["header_bytes"] - p, "bytes", t("padded to 8-byte alignment")])
        p = md["header_bytes"]
    L.append(["(records start)", p, 0, "", t("first record starts at byte {p} (decompressed)").format(p=p)])
    return L

