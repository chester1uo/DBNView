import json
import os

import pytest

from dbnview.engine.ssh_profiles import (SSHProfile, load_profiles, profiles_path, save_profiles, set_password,
                                         ssh_invocation)


@pytest.fixture(autouse=True)
def isolated_profiles(tmp_path, monkeypatch):
    monkeypatch.setenv("DBNVIEW_CONFIG_DIR", str(tmp_path / "config"))


def profile(**overrides):
    values = dict(id="test1", name="Research server", address="data.example.test", username="analyst",
                  port=2222, auth="key", key_path="~/.ssh/research", proxy="jump@example.test:22",
                  log_enabled=True, log_path="")
    values.update(overrides)
    return SSHProfile(**values).validate()


def test_profiles_round_trip_without_secrets():
    saved = profile(auth="password", key_path="")
    save_profiles([saved])
    assert load_profiles() == [saved]
    raw = json.loads(profiles_path().read_text())
    assert raw[0]["auth"] == "password"
    assert "password" not in raw[0]
    if os.name != "nt":
        assert profiles_path().stat().st_mode & 0o077 == 0


def test_key_profile_builds_explicit_ssh_options(tmp_path):
    saved = profile(log_path=str(tmp_path / "logs" / "ssh.log"))
    save_profiles([saved])
    argv, env = ssh_invocation(saved.token, "true")
    assert env is None
    assert argv[-2:] == ["data.example.test", "true"]
    assert ["-p", "2222"] == argv[argv.index("-p"):argv.index("-p") + 2]
    assert ["-l", "analyst"] == argv[argv.index("-l"):argv.index("-l") + 2]
    assert os.path.expanduser("~/.ssh/research") in argv
    assert argv[argv.index("-J") + 1] == "jump@example.test:22"
    assert argv[argv.index("-E") + 1] == str(tmp_path / "logs" / "ssh.log")


def test_password_profile_uses_askpass_without_password_in_arguments():
    saved = profile(auth="password", key_path="", log_enabled=False)
    save_profiles([saved])
    with pytest.raises(OSError, match="password is required"):
        ssh_invocation(saved.token, "true")
    set_password(saved.id, "correct horse battery staple")
    try:
        argv, env = ssh_invocation(saved.token, "true")
        assert "correct horse battery staple" not in argv
        assert env["DBNVIEW_SSH_PASSWORD"] == "correct horse battery staple"
        assert env["SSH_ASKPASS_REQUIRE"] == "force"
        assert "BatchMode=no" in argv
        assert "PubkeyAuthentication=no" in argv
    finally:
        set_password(saved.id, "")


def test_plain_ssh_config_host_remains_supported():
    argv, env = ssh_invocation("existing-alias", "pwd")
    assert env is None
    assert argv[-2:] == ["existing-alias", "pwd"]
    assert "BatchMode=yes" in argv


@pytest.mark.parametrize("values", [
    {"address": "-oProxyCommand=bad"},
    {"username": "two words"},
    {"proxy": "jump host"},
    {"port": 0},
    {"auth": "agent"},
])
def test_profile_rejects_invalid_connection_fields(values):
    with pytest.raises(ValueError):
        profile(**values)


def _opt(argv, name):
    """Value of `-o Name=value` in an ssh argv (None when absent)."""
    for a in argv:
        if a.startswith(name + "="):
            return a.split("=", 1)[1]
    return None


@pytest.mark.parametrize("kind, proxy, expect", [
    ("socks5", "127.0.0.1:7890", "nc -X 5 -x 127.0.0.1:7890 %h %p"),
    ("http", "proxy.example.test:3128", "nc -X connect -x proxy.example.test:3128 %h %p"),
    ("command", "ssh -W %h:%p bastion", "ssh -W %h:%p bastion"),
])
def test_proxy_types_build_proxy_command(kind, proxy, expect):
    saved = profile(proxy_type=kind, proxy=proxy, log_enabled=False)
    save_profiles([saved])
    argv, _ = ssh_invocation(saved.token, "true")
    assert "-J" not in argv
    assert _opt(argv, "ProxyCommand") == expect


def test_jump_chain_like_the_ec2_route():
    # laptop -> tokyo-ec2 -> localhost:2222 (reverse tunnel to the lab) -> target, as in ~/.ssh/config
    saved = profile(address="cs740c.example.test", port=22, proxy_type="jump",
                    proxy="tokyo-ec2,hluo@localhost:2222", log_enabled=False)
    save_profiles([saved])
    argv, _ = ssh_invocation(saved.token, "true")
    assert argv[argv.index("-J") + 1] == "tokyo-ec2,hluo@localhost:2222"
    assert _opt(argv, "ProxyCommand") is None


def test_no_proxy_and_host_key_and_log_level(tmp_path):
    saved = profile(proxy_type="none", proxy="", log_level="VERBOSE", log_path=str(tmp_path / "l.log"))
    save_profiles([saved])
    argv, _ = ssh_invocation(saved.token, "true")
    assert "-J" not in argv and _opt(argv, "ProxyCommand") is None
    assert _opt(argv, "LogLevel") == "VERBOSE"
    assert _opt(argv, "StrictHostKeyChecking") == "accept-new"
    strict = profile(id="test2", accept_new_host_key=False, log_enabled=False)
    save_profiles([saved, strict])
    assert _opt(ssh_invocation(strict.token, "true")[0], "StrictHostKeyChecking") is None


def test_legacy_profile_without_proxy_type_is_a_jump_host():
    old = {"id": "old1", "name": "Old", "address": "h.example.test", "username": "u", "proxy": "bastion"}
    profiles_path().parent.mkdir(parents=True, exist_ok=True)
    profiles_path().write_text(json.dumps([old]))
    (p,) = load_profiles()
    assert p.proxy_kind == "jump"
    argv, _ = ssh_invocation(p.token, "true")
    assert argv[argv.index("-J") + 1] == "bastion"


def test_profiles_resolve_by_name_for_command_line_urls():
    saved = profile(name="lab", log_enabled=False)
    save_profiles([saved])
    argv, _ = ssh_invocation("lab", "true")
    assert argv[-2:] == ["data.example.test", "true"]


def test_each_profile_gets_its_own_shared_connection():
    a, b = profile(id="aaaaaaaa1", log_enabled=False), profile(id="bbbbbbbb2", log_enabled=False)
    save_profiles([a, b])
    if os.name != "nt":
        assert _opt(ssh_invocation(a.token, "true")[0], "ControlPath") != _opt(ssh_invocation(b.token, "true")[0],
                                                                                "ControlPath")


@pytest.mark.parametrize("values", [
    {"proxy_type": "socks5", "proxy": "127.0.0.1"},
    {"proxy_type": "http", "proxy": "host:99999"},
    {"proxy_type": "jump", "proxy": ""},
    {"proxy_type": "jump", "proxy": "-oProxyCommand=x"},
    {"proxy_type": "command", "proxy": "a\nb"},
    {"proxy_type": "vpn", "proxy": "x"},
    {"log_level": "LOUD"},
])
def test_profile_rejects_invalid_proxy_and_log_fields(values):
    with pytest.raises(ValueError):
        profile(**values)


def test_connection_failure_is_reported(tmp_path):
    from dbnview.engine.ssh_profiles import test_connection as check
    saved = profile(address="127.0.0.1", port=1, proxy_type="none", proxy="", key_path="", log_enabled=False)
    ok, msg, secs = check(saved, timeout=20)
    assert not ok and msg and secs >= 0


def test_profile_dialog_builds_profile():
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6 import QtWidgets
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from dbnview.gui.remote_dialog import SSHProfileDialog
    d = SSHProfileDialog(None)
    d.name.setText("lab")
    d.address.setText("cs740c.example.test")
    d.username.setText("hluo")
    d.proxy_type.setCurrentIndex(d.proxy_type.findData("jump"))
    d.proxy.setCurrentText("tokyo-ec2,hluo@localhost:2222")
    d.log_enabled.setChecked(True)
    d.log_level.setCurrentIndex(d.log_level.findData("DEBUG2"))
    p = d.build()
    assert (p.proxy_kind, p.proxy, p.log_level, p.log_enabled) == ("jump", "tokyo-ec2,hluo@localhost:2222", "DEBUG2", True)
    d.proxy_type.setCurrentIndex(d.proxy_type.findData("none"))
    assert d.build().proxy == "" and not d.proxy.isEnabled()
    d.username.setText("")
    with pytest.raises(ValueError):
        d.build()
    d.deleteLater()
    app.processEvents()
