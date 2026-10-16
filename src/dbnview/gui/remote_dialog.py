"""Dialog for browsing and opening DBN files on a remote host over ssh."""
import datetime as dt

from PySide6 import QtCore, QtWidgets
from PySide6.QtCore import Qt

from ..engine import list_dir
from ..i18n import T
from .common import fmt_bytes, run_bg, ssh_hosts


class RemoteDialog(QtWidgets.QDialog):
    def __init__(self, parent, settings):
        super().__init__(parent)
        self.setWindowTitle(T("開啟遠端檔案（ssh）"))
        self.resize(760, 520)
        self.settings = settings
        self.result_path = None
        self.host = QtWidgets.QComboBox()
        self.host.setEditable(True)
        hosts = ssh_hosts()
        self.host.addItems(hosts)
        self.host.setCurrentText(settings.value("remote/host", hosts[0] if hosts else ""))
        self.path = QtWidgets.QLineEdit(settings.value("remote/dir", "/data/databento"))
        up = QtWidgets.QPushButton(T("↑ 上一層"))
        go = QtWidgets.QPushButton(T("前往"))
        go.setDefault(True)
        top = QtWidgets.QHBoxLayout()
        top.addWidget(QtWidgets.QLabel(T("主機")))
        top.addWidget(self.host, 1)
        top.addWidget(QtWidgets.QLabel(T("路徑")))
        top.addWidget(self.path, 3)
        top.addWidget(up)
        top.addWidget(go)
        self.tree = QtWidgets.QTreeWidget()
        self.tree.setHeaderLabels([T("名稱"), T("大小"), T("修改時間")])
        self.tree.setRootIsDecorated(False)
        self.tree.setAlternatingRowColors(True)
        self.tree.header().setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
        self.status = QtWidgets.QLabel(T("使用 ~/.ssh/config 的設定與金鑰（BatchMode，不會問密碼）。"))
        self.status.setStyleSheet("color:gray")
        btns = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Open | QtWidgets.QDialogButtonBox.Cancel)
        btns.button(QtWidgets.QDialogButtonBox.Open).setText(T("開啟"))
        btns.button(QtWidgets.QDialogButtonBox.Cancel).setText(T("取消"))
        lay = QtWidgets.QVBoxLayout(self)
        lay.addLayout(top)
        lay.addWidget(self.tree, 1)
        lay.addWidget(self.status)
        lay.addWidget(btns)
        go.clicked.connect(self.load)
        self.path.returnPressed.connect(self.load)
        up.clicked.connect(self.up)
        self.tree.itemDoubleClicked.connect(self.activate)
        btns.accepted.connect(lambda: self.activate(self.tree.currentItem()))
        btns.rejected.connect(self.reject)
        QtCore.QTimer.singleShot(0, self.load)

    def url(self, p=None):
        return "ssh://%s%s" % (self.host.currentText().strip(), p or self.path.text().strip())

    def load(self):
        self.tree.clear()
        self.status.setText(T("連線中… %s") % self.url())
        url = self.url()
        run_bg(list_dir, url, done=lambda ents: self.fill(url, ents),
               fail=lambda e: self.status.setText(T("錯誤：") + e))

    def fill(self, url, ents):
        if url != self.url():
            return
        self.settings.setValue("remote/host", self.host.currentText().strip())
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

