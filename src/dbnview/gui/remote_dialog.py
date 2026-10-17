"""Dialog for managing SSH profiles and opening remote DBN files."""
import datetime as dt
import html
import os
import subprocess

from PySide6 import QtCore, QtGui, QtWidgets
from PySide6.QtCore import Qt

from ..engine import list_dir
from ..engine.ssh_profiles import (LOG_LEVELS, SSHProfile, default_log_path, has_password, load_profiles,
                                   profile_for_token, save_profiles, set_password, test_connection)
from ..i18n import T
from .common import fmt_bytes, run_bg, ssh_hosts


def _system_profile(host):
    """Resolve an OpenSSH config alias (via `ssh -G`) into an editable managed profile."""
    values = {}
    try:
        r = subprocess.run(["ssh", "-G", host], capture_output=True, text=True, timeout=5,
                           stdin=subprocess.DEVNULL)
        if r.returncode == 0:
            for line in r.stdout.splitlines():
                key, _, value = line.partition(" ")
                if key in ("hostname", "user", "port", "proxyjump", "proxycommand", "loglevel") and key not in values:
                    values[key] = value.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    jump = values.get("proxyjump", "")
    command = values.get("proxycommand", "")
    kind, proxy = "none", ""
    if jump and jump.lower() != "none":
        kind, proxy = "jump", jump
    elif command and command.lower() != "none":
        kind, proxy = "command", command
    level = values.get("loglevel", "INFO").upper()
    return SSHProfile.create(name=host, address=values.get("hostname", host),
                             username=values.get("user", os.environ.get("USER", "")),
                             port=int(values.get("port", 22)), proxy_type=kind, proxy=proxy,
                             log_enabled=level.startswith("DEBUG"), log_level=level if level in LOG_LEVELS else "DEBUG1",
                             log_path=default_log_path())


PROXY_KINDS = [  # (data, label key, placeholder key)
    ("none", "不使用", ""),
    ("jump", "跳板機（ProxyJump）", "~/.ssh/config 的主機別名，或 user@host:port；多個跳板用逗號串接"),
    ("socks5", "SOCKS5 代理", "host:port，例如 127.0.0.1:7890"),
    ("http", "HTTP CONNECT 代理", "host:port，例如 127.0.0.1:7890"),
    ("command", "自訂 ProxyCommand", "例如 ssh -W %h:%p bastion（%h、%p 由 ssh 代入）"),
]


def _form():
    """A form whose fields fill the width on every platform (macOS keeps them at their size hint by default)."""
    form = QtWidgets.QFormLayout()
    form.setFieldGrowthPolicy(QtWidgets.QFormLayout.AllNonFixedFieldsGrow)
    return form


def _row(*widgets, stretch_first=True):
    w = QtWidgets.QWidget()
    lay = QtWidgets.QHBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    for i, x in enumerate(widgets):
        lay.addWidget(x, 1 if (i == 0 and stretch_first) else 0)
    return w


class SSHProfileDialog(QtWidgets.QDialog):
    """Add / edit one SSH profile: login, authentication, proxy, logging; with a connection test."""

    def __init__(self, parent, profile=None):
        super().__init__(parent)
        self.original = profile
        self.result_profile = None
        self.setWindowTitle(T("編輯 SSH 設定") if profile else T("新增 SSH 設定"))
        self.resize(680, 640)

        # -- connection
        self.name = QtWidgets.QLineEdit(profile.name if profile else "")
        self.name.setPlaceholderText(T("例如 研究伺服器"))
        self.address = QtWidgets.QLineEdit(profile.address if profile else "")
        self.address.setPlaceholderText(T("主機名稱或 IP"))
        self.port = QtWidgets.QSpinBox()
        self.port.setRange(1, 65535)
        self.port.setValue(profile.port if profile else 22)
        self.username = QtWidgets.QLineEdit(profile.username if profile else os.environ.get("USER", ""))
        conn = _form()
        conn.addRow(T("設定名稱"), self.name)
        conn.addRow(T("位址"), _row(self.address, QtWidgets.QLabel(T("連接埠")), self.port))
        conn.addRow(T("使用者名稱"), self.username)
        g_conn = QtWidgets.QGroupBox(T("登入"))
        g_conn.setLayout(conn)

        # -- authentication
        self.auth = QtWidgets.QComboBox()
        self.auth.addItem(T("金鑰"), "key")
        self.auth.addItem(T("密碼"), "password")
        self.auth.setCurrentIndex(1 if profile and profile.auth == "password" else 0)
        self.key_path = QtWidgets.QLineEdit(profile.key_path if profile else "")
        self.key_path.setPlaceholderText(T("使用預設金鑰或 ssh-agent"))
        key_pick = QtWidgets.QPushButton(T("選擇…"))
        key_pick.clicked.connect(self.pick_key)
        self.key_row = _row(self.key_path, key_pick)
        self.password = QtWidgets.QLineEdit()
        self.password.setEchoMode(QtWidgets.QLineEdit.Password)
        self.password.setPlaceholderText(T("已輸入（留空則保留）") if profile and has_password(profile.id)
                                          else T("密碼只保留到程式結束，不會寫入磁碟。"))
        auth = _form()
        auth.addRow(T("方式"), self.auth)
        auth.addRow(T("金鑰檔案"), self.key_row)
        auth.addRow(T("密碼"), self.password)
        g_auth = QtWidgets.QGroupBox(T("認證"))
        g_auth.setLayout(auth)

        # -- proxy
        self.proxy_type = QtWidgets.QComboBox()
        for data, label, _ in PROXY_KINDS:
            self.proxy_type.addItem(T(label), data)
        kind = profile.proxy_kind if profile else "none"
        self.proxy_type.setCurrentIndex(max(0, self.proxy_type.findData(kind)))
        self.proxy = QtWidgets.QComboBox()  # editable; offers ~/.ssh/config hosts as jump hosts
        self.proxy.setEditable(True)
        self.proxy.setInsertPolicy(QtWidgets.QComboBox.NoInsert)
        self.proxy.setCurrentText(profile.proxy if profile else "")
        self.proxy_hint = QtWidgets.QLabel()
        self.proxy_hint.setWordWrap(True)
        self.proxy_hint.setStyleSheet("color:gray")
        proxy = _form()
        proxy.addRow(T("類型"), self.proxy_type)
        proxy.addRow(T("代理"), self.proxy)
        g_proxy = QtWidgets.QGroupBox(T("代理"))
        proxy_box = QtWidgets.QVBoxLayout(g_proxy)  # the wrapped hint sits below the form so its height is honoured
        proxy_box.addLayout(proxy)
        proxy_box.addWidget(self.proxy_hint)

        # -- logging / security
        self.log_enabled = QtWidgets.QCheckBox(T("記錄 SSH 日誌"))
        self.log_enabled.setChecked(profile.log_enabled if profile else False)
        self.log_level = QtWidgets.QComboBox()
        for lv in LOG_LEVELS:
            self.log_level.addItem(lv, lv)
        self.log_level.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        self.log_level.setCurrentIndex(max(0, self.log_level.findData(profile.log_level if profile else "DEBUG1")))
        self.log_path = QtWidgets.QLineEdit(profile.log_path if profile and profile.log_path else default_log_path())
        log_pick = QtWidgets.QPushButton(T("選擇…"))
        log_pick.clicked.connect(self.pick_log)
        log_open = QtWidgets.QPushButton(T("開啟日誌"))
        log_open.clicked.connect(self.open_log)
        self.log_row = _row(self.log_path, log_pick, log_open)
        self.accept_new = QtWidgets.QCheckBox(T("首次連線自動信任主機金鑰（金鑰變更時仍會拒絕）"))
        self.accept_new.setChecked(profile.accept_new_host_key if profile else True)
        log = _form()
        log.addRow(self.log_enabled, _row(self.log_level, QtWidgets.QWidget(), stretch_first=False))
        log.addRow(T("日誌檔案"), self.log_row)
        log.addRow(self.accept_new)
        g_log = QtWidgets.QGroupBox(T("日誌與安全"))
        g_log.setLayout(log)

        # -- test + buttons
        self.test_button = QtWidgets.QPushButton(T("測試連線"))
        self.test_button.clicked.connect(self.run_test)
        self.test_result = QtWidgets.QLabel()
        self.test_result.setWordWrap(True)
        self.test_result.setTextInteractionFlags(Qt.TextSelectableByMouse)
        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Save | QtWidgets.QDialogButtonBox.Cancel)
        buttons.button(QtWidgets.QDialogButtonBox.Save).setText(T("儲存"))
        buttons.button(QtWidgets.QDialogButtonBox.Cancel).setText(T("取消"))
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        bottom = QtWidgets.QHBoxLayout()
        bottom.addWidget(self.test_button)
        bottom.addWidget(self.test_result, 1)

        layout = QtWidgets.QVBoxLayout(self)
        for g in (g_conn, g_auth, g_proxy, g_log):
            layout.addWidget(g)
        layout.addLayout(bottom)
        layout.addStretch(1)
        layout.addWidget(buttons)

        self.auth.currentIndexChanged.connect(self.update_fields)
        self.proxy_type.currentIndexChanged.connect(self.update_fields)
        self.log_enabled.toggled.connect(self.update_fields)
        self.update_fields()

    def update_fields(self):
        password = self.auth.currentData() == "password"
        self.key_row.setEnabled(not password)
        self.password.setEnabled(password)
        kind = self.proxy_type.currentData()
        text = self.proxy.currentText()
        self.proxy.clear()
        if kind == "jump":
            self.proxy.addItems(ssh_hosts())
        self.proxy.setCurrentText(text)
        self.proxy.setEnabled(kind != "none")
        key = next(h for d, _, h in PROXY_KINDS if d == kind)
        hint = T(key) if key else ""
        self.proxy.lineEdit().setPlaceholderText(hint)
        if kind in ("socks5", "http"):
            hint += "  " + T("（透過 nc 連線，Windows 需另行安裝）")
        self.proxy_hint.setText(hint)
        self.log_level.setEnabled(self.log_enabled.isChecked())
        self.log_row.setEnabled(self.log_enabled.isChecked())

    def pick_key(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, T("選擇金鑰檔案"),
                                                        os.path.expanduser(self.key_path.text() or "~/.ssh"))
        if path:
            self.key_path.setText(path)

    def pick_log(self):
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, T("選擇 SSH 日誌檔案"),
                                                        os.path.expanduser(self.log_path.text()))
        if path:
            self.log_path.setText(path)

    def open_log(self):
        path = os.path.expanduser(self.log_path.text().strip() or default_log_path())
        if not os.path.exists(path):
            self.test_result.setText(T("日誌檔案尚不存在。"))
            return
        QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(path))

    def build(self):
        """The profile described by the form (raises ValueError when a field is invalid)."""
        if not all(w.text().strip() for w in (self.name, self.address, self.username)):
            raise ValueError(T("名稱、位址和使用者名稱為必填。"))
        kind = self.proxy_type.currentData()
        return SSHProfile(
            id=self.original.id if self.original else SSHProfile.create(
                name="temporary", address="temporary", username="temporary").id,
            name=self.name.text().strip(),
            address=self.address.text().strip(),
            username=self.username.text().strip(),
            port=self.port.value(),
            auth=self.auth.currentData(),
            key_path=self.key_path.text().strip(),
            proxy_type=kind,
            proxy="" if kind == "none" else self.proxy.currentText().strip(),
            log_enabled=self.log_enabled.isChecked(),
            log_level=self.log_level.currentData(),
            log_path=self.log_path.text().strip(),
            accept_new_host_key=self.accept_new.isChecked(),
        ).validate()

    def run_test(self):
        try:
            profile = self.build()
        except ValueError as e:
            self.test_result.setText("<span style='color:#e5534b'>%s</span>" % html.escape(str(e)))
            return
        if profile.auth == "password":
            if self.password.text():
                set_password(profile.id, self.password.text())
            elif not has_password(profile.id):
                self.test_result.setText("<span style='color:#e5534b'>%s</span>" % T("請先輸入密碼。"))
                return
        self.test_button.setEnabled(False)
        self.test_result.setText(T("連線中…"))

        def done(res):
            self.test_button.setEnabled(True)
            ok, msg, secs = res
            color = "#3fb950" if ok else "#e5534b"
            head = T("連線成功（%.1f 秒）") % secs if ok else T("連線失敗（%.1f 秒）") % secs
            tail = msg.strip().splitlines()[-3:] if msg else []
            self.test_result.setText("<span style='color:%s'><b>%s</b></span><br><span style='color:gray'>%s</span>"
                                     % (color, head, "<br>".join(html.escape(x) for x in tail)))

        def fail(e):
            self.test_button.setEnabled(True)
            self.test_result.setText("<span style='color:#e5534b'>%s</span>" % html.escape(str(e)))

        run_bg(test_connection, profile, done=done, fail=fail)

    def save(self):
        try:
            profile = self.build()
        except ValueError as e:
            QtWidgets.QMessageBox.warning(self, T("SSH 設定"), str(e))
            return
        if profile.auth == "password" and self.password.text():
            set_password(profile.id, self.password.text())
        self.result_profile = profile
        self.accept()


class RemoteDialog(QtWidgets.QDialog):
    def __init__(self, parent, settings):
        super().__init__(parent)
        self.setWindowTitle(T("開啟遠端檔案（ssh）"))
        self.resize(900, 590)
        self.settings = settings
        self.result_path = None
        self.profiles = load_profiles()

        self.host = QtWidgets.QComboBox()
        self.host.setEditable(True)
        self.add_button = QtWidgets.QPushButton("+")
        self.add_button.setToolTip(T("新增 SSH 設定"))
        self.edit_button = QtWidgets.QPushButton(T("編輯"))
        self.delete_button = QtWidgets.QPushButton(T("刪除"))
        self.path = QtWidgets.QLineEdit(settings.value("remote/dir", "/data/databento"))
        up = QtWidgets.QPushButton(T("↑ 上一層"))
        go = QtWidgets.QPushButton(T("前往"))
        go.setDefault(True)

        connection_row = QtWidgets.QHBoxLayout()
        connection_row.addWidget(QtWidgets.QLabel(T("SSH 設定")))
        connection_row.addWidget(self.host, 1)
        connection_row.addWidget(self.add_button)
        connection_row.addWidget(self.edit_button)
        connection_row.addWidget(self.delete_button)
        path_row = QtWidgets.QHBoxLayout()
        path_row.addWidget(QtWidgets.QLabel(T("路徑")))
        path_row.addWidget(self.path, 1)
        path_row.addWidget(up)
        path_row.addWidget(go)

        self.tree = QtWidgets.QTreeWidget()
        self.tree.setHeaderLabels([T("名稱"), T("大小"), T("修改時間")])
        self.tree.setRootIsDecorated(False)
        self.tree.setAlternatingRowColors(True)
        self.tree.header().setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
        self.status = QtWidgets.QLabel(T("選擇 SSH 設定或 ~/.ssh/config 的主機；按 + 新增設定。"))
        self.status.setStyleSheet("color:gray")
        btns = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Open | QtWidgets.QDialogButtonBox.Cancel)
        btns.button(QtWidgets.QDialogButtonBox.Open).setText(T("開啟"))
        btns.button(QtWidgets.QDialogButtonBox.Cancel).setText(T("取消"))
        lay = QtWidgets.QVBoxLayout(self)
        lay.addLayout(connection_row)
        lay.addLayout(path_row)
        lay.addWidget(self.tree, 1)
        lay.addWidget(self.status)
        lay.addWidget(btns)

        self.populate_hosts(settings.value("remote/host", ""))
        go.clicked.connect(self.load)
        self.path.returnPressed.connect(self.load)
        up.clicked.connect(self.up)
        self.tree.itemDoubleClicked.connect(self.activate)
        btns.accepted.connect(lambda: self.activate(self.tree.currentItem()))
        btns.rejected.connect(self.reject)
        self.add_button.clicked.connect(self.add_profile)
        self.edit_button.clicked.connect(self.edit_profile)
        self.delete_button.clicked.connect(self.delete_profile)
        self.host.currentIndexChanged.connect(self.update_profile_buttons)
        self.update_profile_buttons()
        QtCore.QTimer.singleShot(0, self.load)

    def populate_hosts(self, selected=""):
        self.host.clear()
        for profile in self.profiles:
            self.host.addItem(profile.name, profile.token)
        managed_names = {p.name for p in self.profiles}
        for host in ssh_hosts():
            if host not in managed_names:
                self.host.addItem(host, host)
        selected = selected or (self.profiles[0].token if self.profiles else "")
        index = self.host.findData(selected)
        if index < 0:
            index = self.host.findText(selected)
        if index >= 0:
            self.host.setCurrentIndex(index)
        else:
            self.host.setCurrentText(selected)

    def selected_host(self):
        data = self.host.currentData()
        return data if data and self.host.currentIndex() >= 0 else self.host.currentText().strip()

    def selected_profile(self):
        return profile_for_token(self.selected_host())

    def update_profile_buttons(self):
        managed = self.selected_profile() is not None
        self.edit_button.setEnabled(bool(self.host.currentText().strip()))
        self.delete_button.setEnabled(managed)

    def save_profile(self, profile):
        profiles = [p for p in self.profiles if p.id != profile.id] + [profile]
        try:
            save_profiles(profiles)
        except (OSError, ValueError) as e:
            QtWidgets.QMessageBox.warning(self, T("SSH 設定"), T("錯誤：") + str(e))
            return
        self.profiles = profiles
        self.populate_hosts(profile.token)
        self.status.setText(T("SSH 設定已儲存。"))

    def add_profile(self):
        dialog = SSHProfileDialog(self)
        if dialog.exec() and dialog.result_profile:
            self.save_profile(dialog.result_profile)

    def edit_profile(self):
        profile = self.selected_profile()
        if profile is None:
            host = self.host.currentText().strip()
            if not host:
                return
            profile = _system_profile(host)
        dialog = SSHProfileDialog(self, profile)
        if dialog.exec() and dialog.result_profile:
            self.save_profile(dialog.result_profile)

    def delete_profile(self):
        profile = self.selected_profile()
        if profile is None:
            return
        answer = QtWidgets.QMessageBox.question(
            self, T("確認刪除"), T("刪除 SSH 設定「%s」？") % profile.name,
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
        )
        if answer != QtWidgets.QMessageBox.Yes:
            return
        profiles = [p for p in self.profiles if p.id != profile.id]
        try:
            save_profiles(profiles)
        except (OSError, ValueError) as e:
            QtWidgets.QMessageBox.warning(self, T("SSH 設定"), T("錯誤：") + str(e))
            return
        self.profiles = profiles
        self.populate_hosts()

    def ensure_password(self):
        profile = self.selected_profile()
        if profile is None or profile.auth != "password" or has_password(profile.id):
            return True
        password, ok = QtWidgets.QInputDialog.getText(
            self, T("需要密碼"), T("請輸入 SSH 密碼：%s") % profile.name, QtWidgets.QLineEdit.Password,
        )
        if not ok or not password:
            self.status.setText(T("已取消連線。"))
            return False
        set_password(profile.id, password)
        return True

    def url(self, p=None):
        return "ssh://%s%s" % (self.selected_host(), p or self.path.text().strip())

    def load(self):
        if not self.selected_host() or not self.ensure_password():
            return
        self.tree.clear()
        self.status.setText(T("連線中… %s") % self.url())
        url = self.url()
        run_bg(list_dir, url, done=lambda ents: self.fill(url, ents),
               fail=lambda e: self.status.setText(T("錯誤：") + e))

    def fill(self, url, ents):
        if url != self.url():
            return
        self.settings.setValue("remote/host", self.selected_host())
        self.settings.setValue("remote/dir", self.path.text().strip())
        style = self.style()
        for e in ents:
            it = QtWidgets.QTreeWidgetItem([e["name"], "" if e["dir"] else fmt_bytes(e["size"]),
                                            "" if e["dir"] else dt.datetime.fromtimestamp(e["mtime"]).strftime("%Y-%m-%d %H:%M")])
            it.setIcon(0, style.standardIcon(QtWidgets.QStyle.SP_DirIcon if e["dir"] else QtWidgets.QStyle.SP_FileIcon))
            it.setData(0, Qt.UserRole, e)
            it.setTextAlignment(1, Qt.AlignRight | Qt.AlignVCenter)
            self.tree.addTopLevelItem(it)
        self.status.setText(T("%d 項 · 雙擊資料夾進入，雙擊檔案開啟") % len(ents))

    def up(self):
        p = self.path.text().rstrip("/")
        self.path.setText(p.rsplit("/", 1)[0] or "/")
        self.load()

    def activate(self, it):
        if it is None:
            return
        e = it.data(0, Qt.UserRole)
        p = self.path.text().rstrip("/") + "/" + e["name"]
        if e["dir"]:
            self.path.setText(p)
            self.load()
        else:
            self.result_path = self.url(p)
            self.accept()
