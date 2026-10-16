"""Byte sources: local files or `ssh host cat path` streams, zstd detection, directory listing."""
import os

try:
    import zstandard
except ImportError:  # pragma: no cover
    zstandard = None


SSH_OPTS = ["-o", "BatchMode=yes", "-o", "ConnectTimeout=10"]
if os.name != "nt":  # connection sharing is not available in Windows OpenSSH
    SSH_OPTS += ["-o", "ControlMaster=auto", "-o", "ControlPath=~/.ssh/dbnview-%r@%h:%p", "-o", "ControlPersist=120"]


def is_remote(path):
    return path.startswith("ssh://")


def split_remote(path):
    """'ssh://host/abs/path' -> (host, '/abs/path')"""
    rest = path[6:]
    host, _, p = rest.partition("/")
    return host, "/" + p


def ssh_run(host, cmd, timeout=30):
    import subprocess
    r = subprocess.run(["ssh"] + SSH_OPTS + [host, cmd], capture_output=True, timeout=timeout)
    if r.returncode != 0:
        raise OSError("ssh %s: %s" % (host, r.stderr.decode(errors="replace").strip() or r.returncode))
    return r.stdout.decode("utf-8", "replace")


def source_stat(path):
    """(size, mtime) of a local path or ssh://host/path."""
    if is_remote(path):
        import shlex
        host, p = split_remote(path)
        size, mtime = ssh_run(host, "stat -L -c '%s %Y' " + shlex.quote(p)).split()
        return int(size), float(mtime)
    st = os.stat(path)
    return st.st_size, st.st_mtime


def list_dir(path):
    """Directory entries (dirs + DBN files) of a local or ssh:// directory."""
    ents = []
    keep = lambda n: n.endswith((".dbn", ".dbn.zst", ".zst"))
    if is_remote(path):
        import shlex
        host, p = split_remote(path)
        out = ssh_run(host, "find %s -mindepth 1 -maxdepth 1 -printf '%%y\\t%%s\\t%%T@\\t%%f\\n'"
                      % shlex.quote(p))
        for line in out.splitlines():
            parts = line.split("\t", 3)
            if len(parts) != 4 or parts[3].startswith("."):
                continue
            typ, size, mtime, name = parts
            if typ == "d":
                ents.append({"name": name, "dir": True})
            elif keep(name):
                ents.append({"name": name, "dir": False, "size": int(size), "mtime": float(mtime)})
    else:
        with os.scandir(path) as it:
            for e in it:
                if e.name.startswith("."):
                    continue
                try:
                    if e.is_dir():
                        ents.append({"name": e.name, "dir": True})
                    elif keep(e.name):
                        st = e.stat()
                        ents.append({"name": e.name, "dir": False, "size": st.st_size, "mtime": st.st_mtime})
                except OSError:
                    pass
    ents.sort(key=lambda x: (not x["dir"], x["name"]))
    return ents


class _CountingReader:
    """Raw byte source with .read/.tell/.close; local file or `ssh host cat path`."""

    def __init__(self, path):
        self.n = 0
        self.proc = None
        self.prefix = b""
        if is_remote(path):
            import shlex
            import subprocess
            host, p = split_remote(path)
            self.proc = subprocess.Popen(["ssh"] + SSH_OPTS + [host, "cat " + shlex.quote(p)],
                                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0)
            self.f = self.proc.stdout
        else:
            self.f = open(path, "rb")

    def peek(self, k):
        while len(self.prefix) < k:
            b = self.f.read(k - len(self.prefix))
            if not b:
                break
            self.prefix += b
        if not self.prefix and self.proc is not None:
            self.proc.wait(timeout=30)
            raise OSError("ssh: " + self.proc.stderr.read().decode(errors="replace").strip())
        return self.prefix[:k]

    def read(self, k=-1):
        if self.prefix:
            out, self.prefix = self.prefix[:k] if k >= 0 else self.prefix, \
                self.prefix[k:] if k >= 0 else b""
            self.n += len(out)
            return out
        b = self.f.read(k) if k >= 0 else self.f.read()
        self.n += len(b)
        return b

    def readinto(self, buf):
        b = self.read(len(buf))
        buf[:len(b)] = b
        return len(b)

    def readable(self):
        return True

    def tell(self):
        return self.n

    def close(self):
        try:
            self.f.close()
        finally:
            if self.proc is not None and self.proc.poll() is None:
                self.proc.kill()
                self.proc.wait()


def open_stream(path):
    """Return (raw byte source with .tell(), decoded DBN byte stream)."""
    fh = _CountingReader(path)
    magic = fh.peek(4)
    if magic == b"\x28\xb5\x2f\xfd":
        if zstandard is None:
            raise RuntimeError("pip install zstandard  (needed for .zst files)")
        try:
            rd = zstandard.ZstdDecompressor().stream_reader(fh, read_size=1 << 20,
                                                             read_across_frames=True)
        except TypeError:  # very old zstandard
            rd = zstandard.ZstdDecompressor().stream_reader(fh, read_size=1 << 20)
        return fh, rd
    return fh, fh

