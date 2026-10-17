"""Managed SSH connection profiles and OpenSSH command construction."""
from __future__ import annotations

import atexit
import json
import os
import re
import shutil
import stat
import sys
import tempfile
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path


PROFILE_PREFIX = "dbnview-"
AUTH_METHODS = ("key", "password")
PROXY_TYPES = ("none", "jump", "socks5", "http", "command")
LOG_LEVELS = ("ERROR", "INFO", "VERBOSE", "DEBUG1", "DEBUG2", "DEBUG3")
_JUMP_RE = re.compile(r"[A-Za-z0-9_.@:\[\]%-]+(,[A-Za-z0-9_.@:\[\]%-]+)*")
_HOSTPORT_RE = re.compile(r"(\[[0-9A-Fa-f:.]+\]|[A-Za-z0-9_.-]+):(\d{1,5})")
_SECRETS = {}
_ASKPASS_DIR = None


def _config_dir():
    override = os.environ.get("DBNVIEW_CONFIG_DIR")
    if override:
        return Path(override).expanduser()
    if os.name == "nt":
        root = os.environ.get("APPDATA") or os.path.expanduser("~")
        return Path(root) / "dbnview"
    return Path(os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))) / "dbnview"


def profiles_path():
    return _config_dir() / "ssh_profiles.json"


def default_log_path():
    if sys.platform == "darwin":
        return str(Path.home() / "Library" / "Logs" / "DBNView" / "ssh.log")
    if os.name == "nt":
        root = Path(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"))
        return str(root / "dbnview" / "ssh.log")
    root = Path(os.environ.get("XDG_STATE_HOME", os.path.expanduser("~/.local/state")))
    return str(root / "dbnview" / "ssh.log")


@dataclass(frozen=True)
class SSHProfile:
    id: str
    name: str
    address: str
    username: str
    port: int = 22
    auth: str = "key"
    key_path: str = ""
    proxy: str = ""
    log_enabled: bool = False
    log_path: str = ""
    proxy_type: str = ""          # "" = infer: "jump" when proxy is set (profiles saved before proxy types)
    log_level: str = "DEBUG1"
    accept_new_host_key: bool = True

    @property
    def token(self):
        return PROFILE_PREFIX + self.id

    @property
    def proxy_kind(self):
        if self.proxy_type:
            return self.proxy_type
        return "jump" if self.proxy else "none"

    def validate(self):
        if not re.fullmatch(r"[A-Za-z0-9_-]+", self.id):
            raise ValueError("invalid SSH profile id")
        for label, value in (("name", self.name), ("address", self.address), ("username", self.username)):
            if not value.strip():
                raise ValueError("SSH profile %s is required" % label)
        for label, value in (("address", self.address), ("username", self.username)):
            if value.startswith("-") or any(ch.isspace() for ch in value):
                raise ValueError("invalid SSH profile %s" % label)
        if not 1 <= int(self.port) <= 65535:
            raise ValueError("invalid SSH port")
        if self.auth not in AUTH_METHODS:
            raise ValueError("invalid SSH authentication method")
        kind = self.proxy_kind
        if kind not in PROXY_TYPES:
            raise ValueError("invalid SSH proxy type")
        proxy = self.proxy.strip()
        if kind != "none" and not proxy:
            raise ValueError("SSH proxy is required for this proxy type")
        if kind == "jump" and (proxy.startswith("-") or not _JUMP_RE.fullmatch(proxy)):
            raise ValueError("invalid SSH proxy: use host aliases or user@host:port, separated by commas")
        if kind in ("socks5", "http"):
            m = _HOSTPORT_RE.fullmatch(proxy)
            if not m or not 1 <= int(m.group(2)) <= 65535:
                raise ValueError("invalid SSH proxy: use host:port")
        if kind == "command" and ("\n" in proxy or proxy.startswith("-")):
            raise ValueError("invalid SSH proxy command")
        if self.log_level not in LOG_LEVELS:
            raise ValueError("invalid SSH log level")
        return self

    @classmethod
    def create(cls, **values):
        values.setdefault("id", uuid.uuid4().hex)
        return cls(**values).validate()

    @classmethod
    def from_dict(cls, values):  # tolerant of older / newer files: unknown keys are dropped
        known = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in values.items() if k in known}).validate()

    def to_dict(self):
        return asdict(self)


def load_profiles():
    try:
        raw = json.loads(profiles_path().read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return []
    profiles = []
    for item in raw if isinstance(raw, list) else []:
        try:
            profiles.append(SSHProfile.from_dict(item))
        except (TypeError, ValueError):
            continue
    return profiles


def save_profiles(profiles):
    profiles = [p.validate() for p in profiles]
    ids = [p.id for p in profiles]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate SSH profile id")
    path = profiles_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.parent.chmod(0o700)
    except OSError:
        pass
    fd, tmp = tempfile.mkstemp(prefix=".ssh_profiles-", suffix=".json", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump([p.to_dict() for p in profiles], f, ensure_ascii=False, indent=2)
            f.write("\n")
        try:
            os.chmod(tmp, 0o600)
        except OSError:
            pass
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def profile_for_token(token):
    """Profile for 'dbnview-<id>' or, so `ssh://NAME/path` works on the command line, an exact profile name."""
    profiles = load_profiles()
    if token.startswith(PROFILE_PREFIX):
        found = next((p for p in profiles if p.id == token[len(PROFILE_PREFIX):]), None)
        if found:
            return found
    return next((p for p in profiles if p.name == token), None)


def set_password(profile_id, password):
    if password:
        _SECRETS[profile_id] = password
    else:
        _SECRETS.pop(profile_id, None)


def has_password(profile_id):
    return bool(_SECRETS.get(profile_id))


def _askpass_program():
    global _ASKPASS_DIR
    if _ASKPASS_DIR:
        return str(Path(_ASKPASS_DIR) / ("askpass.cmd" if os.name == "nt" else "askpass"))
    _ASKPASS_DIR = tempfile.mkdtemp(prefix="dbnview-askpass-")
    path = Path(_ASKPASS_DIR) / ("askpass.cmd" if os.name == "nt" else "askpass")
    if os.name == "nt":
        path.write_text("@echo off\r\n<nul set /p=\"%DBNVIEW_SSH_PASSWORD%\"\r\n", encoding="utf-8")
    else:
        path.write_text("#!/bin/sh\nprintf '%s\\n' \"$DBNVIEW_SSH_PASSWORD\"\n", encoding="utf-8")
        path.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
    atexit.register(shutil.rmtree, _ASKPASS_DIR, ignore_errors=True)
    return str(path)


def _base_options(batch_mode=True, control_path="~/.ssh/dbnview-%r@%h:%p", share=True):
    opts = ["-o", "BatchMode=%s" % ("yes" if batch_mode else "no"),
            "-o", "ConnectTimeout=10"]
    if os.name != "nt" and share:
        opts += ["-o", "ControlMaster=auto", "-o", "ControlPath=" + control_path,
                 "-o", "ControlPersist=120"]
    elif os.name != "nt":
        opts += ["-o", "ControlMaster=no", "-o", "ControlPath=none"]
    return opts


def proxy_command(profile):
    """The OpenSSH ProxyCommand for a SOCKS5 / HTTP CONNECT / custom proxy (None for none / jump hosts)."""
    kind = profile.proxy_kind
    if kind == "socks5":
        return "nc -X 5 -x %s %%h %%p" % profile.proxy.strip()
    if kind == "http":
        return "nc -X connect -x %s %%h %%p" % profile.proxy.strip()
    if kind == "command":
        return profile.proxy.strip()
    return None


def profile_invocation(profile, remote_command, share=True):
    """Return ``(argv, env)`` running `remote_command` through a managed profile."""
    password_auth = profile.auth == "password"
    # one shared connection per profile: two profiles may reach the same host:port through different proxies
    args = ["ssh"] + _base_options(batch_mode=not password_auth, share=share,
                                   control_path="~/.ssh/dbnview-%s-%%C" % profile.id[:8])
    args += ["-p", str(profile.port), "-l", profile.username]
    if password_auth:
        password = _SECRETS.get(profile.id)
        if not password:
            raise OSError("SSH password is required; reopen the remote-file dialog")
        args += ["-o", "PubkeyAuthentication=no", "-o", "PreferredAuthentications=password,keyboard-interactive",
                 "-o", "PasswordAuthentication=yes", "-o", "KbdInteractiveAuthentication=yes",
                 "-o", "NumberOfPasswordPrompts=1"]
    elif profile.key_path:
        args += ["-i", os.path.expanduser(profile.key_path), "-o", "IdentitiesOnly=yes"]
    if profile.accept_new_host_key:
        args += ["-o", "StrictHostKeyChecking=accept-new"]
    if profile.proxy_kind == "jump":
        args += ["-J", profile.proxy.strip()]
    elif proxy_command(profile):
        args += ["-o", "ProxyCommand=" + proxy_command(profile)]
    if profile.log_enabled:
        log_path = Path(os.path.expanduser(profile.log_path or default_log_path()))
        log_path.parent.mkdir(parents=True, exist_ok=True)
        args += ["-E", str(log_path), "-o", "LogLevel=" + profile.log_level]
    args += [profile.address, remote_command]

    env = None
    if password_auth:
        env = os.environ.copy()
        env["SSH_ASKPASS"] = _askpass_program()
        env["SSH_ASKPASS_REQUIRE"] = "force"
        env["DBNVIEW_SSH_PASSWORD"] = password
        env.setdefault("DISPLAY", ":0")
    return args, env


def ssh_invocation(host, remote_command):
    """Return ``(argv, env)`` for an OpenSSH call, resolving managed profiles."""
    profile = profile_for_token(host)
    if profile is None:
        return ["ssh"] + _base_options() + [host, remote_command], None
    return profile_invocation(profile, remote_command)


def test_connection(profile, timeout=30):
    """Connect once without connection sharing and run a tiny command: (ok, message, seconds)."""
    import subprocess
    import time
    t0 = time.time()
    try:
        argv, env = profile_invocation(profile, "echo DBNVIEW_OK; uname -srm", share=False)
        r = subprocess.run(argv, capture_output=True, timeout=timeout, env=env, stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        return False, "timed out after %d s" % timeout, time.time() - t0
    except OSError as e:
        return False, str(e), time.time() - t0
    out = r.stdout.decode("utf-8", "replace")
    if r.returncode == 0 and "DBNVIEW_OK" in out:
        return True, out.replace("DBNVIEW_OK", "").strip(), time.time() - t0
    err = r.stderr.decode("utf-8", "replace").strip()
    return False, err or "ssh exited with status %d" % r.returncode, time.time() - t0
