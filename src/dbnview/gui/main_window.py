"""Main window: menus/toolbar, the panels, and the open → scan → poll lifecycle.

Panels receive the window as `win` and read shared state from it:
    win.fi / win.meta      opened file (engine.FileInfo) and its JSON summary
    win.job / win.status   current scan job and its latest status dict
    win.stats              latest statistics (top instruments, minute histogram, ...)
    win.tsfmt, win.colors, win.mono, win.settings, win.run_bg(), win.show_error()
"""
import os
import time

from PySide6 import QtCore, QtGui, QtWidgets
from PySide6.QtCore import Qt

from .. import i18n
from ..engine import FileInfo, Job, is_remote
from ..i18n import T
from .charts import ChartPanel
from .common import APP_NAME, TZS, TsFmt, display_name, native_shortcuts, run_bg, theme
from .detail_panel import DetailPanel
from .filter_panel import FilterPanel
from .format_view import FormatView
from .iv_panel import IVPanel
from .remote_dialog import RemoteDialog
from .stats_view import StatsView
from .table_panel import TablePanel


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = QtCore.QSettings("dbnview", "dbnview")
        self.tsfmt = TsFmt()
        self.tsfmt.set(self.settings.value("tz", "America/New_York"), self.settings.value("tsmode", "dt"))
        self.colors = theme()
        self.fi = self.meta = self.job = self.status = self.stats = None
        self.last_stats = 0
        self.run_bg = run_bg
        self.mono = QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.FixedFont)
        self.mono.setPointSize(11)

        self.setWindowTitle(APP_NAME)
        self.resize(1500, 900)
        self.setAcceptDrops(True)
        self._build_actions()
        self._build_ui()
        self.timer = QtCore.QTimer(self)
        self.timer.setInterval(200)
        self.timer.timeout.connect(self.poll)
        if self.settings.value("geometry") is not None:
            self.restoreGeometry(self.settings.value("geometry"))
        if self.settings.value("splitter") is not None:
            self.split.restoreState(self.settings.value("splitter"))
        self.update_actions()

    # ---- construction ---------------------------------------------------------------
    def _build_actions(self):
        A = QtGui.QAction
        self.a_open = A(T("開啟檔案…"), self, shortcut=QtGui.QKeySequence.Open, triggered=self.open_local)
        self.a_remote = A(T("開啟遠端檔案（ssh）…"), self, shortcut="Ctrl+Shift+O", triggered=self.open_remote)
        self.a_scan = A(T("掃描"), self, shortcut="Ctrl+R", triggered=self.start_scan)
        self.a_stop = A(T("停止"), self, shortcut="Ctrl+.", triggered=self.stop_scan)
        self.a_export = A(T("匯出 CSV…"), self, shortcut="Ctrl+E", triggered=lambda: self.table.export_csv())
        self.a_detail = A(T("明細面板"), self, shortcut="Ctrl+I", checkable=True, checked=True,
                          triggered=lambda on: self.detail.setVisible(on))
        self.a_filters = A(T("檔案與篩選面板"), self, shortcut="Ctrl+L", checkable=True, checked=True,
                           triggered=lambda on: self.left.setVisible(on))
        self.a_quit = A(T("結束"), self, shortcut=QtGui.QKeySequence.Quit, triggered=self.close)
        self.recent_menu = QtWidgets.QMenu(T("最近開啟"), self)
        mb = self.menuBar()
        m = mb.addMenu(T("檔案"))
        m.addActions([self.a_open, self.a_remote])
        m.addMenu(self.recent_menu)
        m.addSeparator()
        m.addAction(self.a_export)
        m.addSeparator()
        m.addAction(self.a_quit)
        mb.addMenu(T("資料")).addActions([self.a_scan, self.a_stop])
        self.col_menu = mb.addMenu(T("欄位"))
        self.col_menu.aboutToShow.connect(lambda: self.table.fill_col_menu(menu=self.col_menu))
        mb.addMenu(T("檢視")).addActions([self.a_filters, self.a_detail])
        lm = mb.addMenu(T("語言") + ("" if i18n.get_lang() == "en" else " / Language"))
        grp = QtGui.QActionGroup(self)
        for code, label in i18n.LANGS:
            a = lm.addAction(label)
            a.setCheckable(True)
            a.setChecked(code == i18n.get_lang())
            grp.addAction(a)
            a.triggered.connect(lambda _=False, code=code: QtWidgets.QApplication.instance().switch_lang(code))
        self.rebuild_recent()

    def _build_ui(self):
        tb = self.addToolBar("main")
        tb.setMovable(False)
        tb.setToolButtonStyle(Qt.ToolButtonTextOnly)
        tb.addActions([self.a_open, self.a_remote])
        rb = QtWidgets.QToolButton()
        rb.setText(T("最近"))
        rb.setMenu(self.recent_menu)
        rb.setPopupMode(QtWidgets.QToolButton.InstantPopup)
        tb.addWidget(rb)
        tb.addSeparator()
        tb.addActions([self.a_scan, self.a_stop])
        tb.addSeparator()
        tb.addWidget(QtWidgets.QLabel(T(" 時區 ")))
        self.tz_box = QtWidgets.QComboBox()
        for label, tz in TZS:
            self.tz_box.addItem(label, tz)
        self.tz_box.setCurrentIndex(max(0, self.tz_box.findData(self.tsfmt.tz)))
        self.tz_box.currentIndexChanged.connect(self.on_tz)
        tb.addWidget(self.tz_box)
        tb.addWidget(QtWidgets.QLabel(T(" 時間 ")))
        self.mode_box = QtWidgets.QComboBox()
        for label, m in ((T("日期+時間"), "dt"), (T("只顯示時間"), "t"), (T("原始 ns"), "ns")):
            self.mode_box.addItem(label, m)
        self.mode_box.setCurrentIndex(max(0, self.mode_box.findData(self.tsfmt.mode)))
        self.mode_box.currentIndexChanged.connect(self.on_tz)
        tb.addWidget(self.mode_box)
        tb.addSeparator()
        tb.addAction(self.a_export)
        spacer = QtWidgets.QWidget()
        spacer.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
        tb.addWidget(spacer)
        tb.addAction(self.a_detail)

        self.left = FilterPanel(self)
        self.left.scanRequested.connect(self.start_scan)
        self.left.stopRequested.connect(self.stop_scan)
        self.table = TablePanel(self)
        self.detail = DetailPanel(self)
        self.table.rowSelected.connect(self.detail.show_row)
        self.chart = ChartPanel(self)
        self.stats_view = StatsView(self)
        self.stats_view.filterRequested.connect(self.filter_instrument)
        self.stats_view.chartRequested.connect(self.chart_instrument)
        self.format_view = FormatView(self)
        self.iv = IVPanel(self)

        self.tabs = QtWidgets.QTabWidget()
        self.tabs.setDocumentMode(True)
        for w, label in ((self.table, T("表格")), (self.chart, T("圖表")), (self.stats_view, T("統計")),
                         (self.format_view, T("格式說明")), (self.iv, T("IV 曲面"))):
            self.tabs.addTab(w, label)
        self.tabs.currentChanged.connect(self.on_tab)

        self.split = QtWidgets.QSplitter(Qt.Horizontal)
        for w in (self.left, self.tabs, self.detail):
            self.split.addWidget(w)
        self.split.setStretchFactor(1, 1)
        self.split.setSizes([310, 900, 380])
        self.split.setCollapsible(1, False)
        self.setCentralWidget(self.split)
        self.statusBar().showMessage(native_shortcuts(T("拖一個 .dbn / .dbn.zst 檔進來，或用 ⌘O / ⇧⌘O 開啟")))

    # ---- opening files ---------------------------------------------------------------
    def open_local(self):
        start = self.settings.value("lastdir", os.path.expanduser("~"))
        p, _ = QtWidgets.QFileDialog.getOpenFileName(self, T("開啟 DBN 檔"), start,
                                                     T("DBN 檔 (*.dbn *.zst *.dbn.zst);;所有檔案 (*)"))
        if p:
            self.settings.setValue("lastdir", os.path.dirname(p))
            self.open_path(p)

    def open_remote(self):
        d = RemoteDialog(self, self.settings)
        if d.exec() and d.result_path:
            self.open_path(d.result_path)

    def open_path(self, path):
        self.show_error(None)
        self.statusBar().showMessage(T("讀取檔頭… %s") % path)
        QtWidgets.QApplication.setOverrideCursor(Qt.BusyCursor)

        def done(fi):
            QtWidgets.QApplication.restoreOverrideCursor()
            self.on_file(fi)

        def fail(e):
            QtWidgets.QApplication.restoreOverrideCursor()
            self.show_error(e)
            self.statusBar().showMessage(T("開啟失敗"))

        run_bg(FileInfo.get, path, done=done, fail=fail)

    def on_file(self, fi):
        self.fi = fi
        self.meta = fi.to_json()
        self.add_recent(fi.path)
        self.setWindowTitle("%s — %s" % (display_name(fi.path), APP_NAME))
        if not is_remote(fi.path):
            self.setWindowFilePath(fi.path)
        self.left.set_file(fi, self.meta)
        self.format_view.render(fi, self.meta)
        self.start_scan()

    # ---- scanning --------------------------------------------------------------------
    def start_scan(self):
        if self.fi is None:
            return
        self.show_error(None)
        if self.job is not None:
            self.job.cancelled = True
        try:
            job = Job(self.fi.path, self.left.query())
        except Exception as e:  # noqa: BLE001
            self.show_error("%s: %s" % (type(e).__name__, e))
            return
        self.job, self.status, self.stats, self.last_stats = job, None, None, 0
        self.table.reset(job)
        self.detail.clear()
        self.timer.start()
        self.update_actions()
        self.poll()

    def stop_scan(self):
        if self.job is not None:
            self.job.cancelled = True

    def poll(self):
        job = self.job
        if job is None:
            return
        want_stats = job.done or time.time() - self.last_stats > 1.0
        st = job.status(with_stats=want_stats)
        if st.get("stats"):
            self.stats = st["stats"]
            self.last_stats = time.time()
        self.status = st
        self.table.update_from_status(st)
        self.left.render_progress(st)
        self.statusBar().showMessage("%s · %s" % (FilterPanel.state_text(st), self.fi.path if self.fi else ""))
        if want_stats and self.tabs.currentWidget() is self.stats_view:
            self.stats_view.render(self.status, self.stats)
        if st["done"]:
            self.timer.stop()
            if st["error"]:
                self.show_error(st["error"])
            self.chart.fill_inst()
            self.iv.prepare()
            self.stats_view.render(self.status, self.stats)
            if self.tabs.currentWidget() is self.chart:
                self.chart.on_instrument()
            self.update_actions()
            self.table.select_first_if_none()

    def update_actions(self):
        running = self.job is not None and not self.job.done
        self.a_stop.setEnabled(running)
        self.a_scan.setEnabled(self.fi is not None)
        self.a_export.setEnabled(self.job is not None and self.job.n > 0)
        self.left.set_running(self.fi is not None, running)

    def show_error(self, e):
        self.left.show_error(e)

    # ---- cross-panel actions ---------------------------------------------------------
    def filter_instrument(self, iid):
        self.left.filter_instrument(iid)
        self.tabs.setCurrentWidget(self.table)
        self.start_scan()

    def chart_instrument(self, iid):
        self.tabs.setCurrentWidget(self.chart)
        self.chart.show_iid(iid)

    def on_tz(self):
        self.tsfmt.set(self.tz_box.currentData(), self.mode_box.currentData())
        self.settings.setValue("tz", self.tsfmt.tz)
        self.settings.setValue("tsmode", self.tsfmt.mode)
        if self.meta:
            self.left.render_info(self.meta)
            self.format_view.render(self.fi, self.meta)
        self.table.refresh()
        if self.detail.row is not None:
            self.detail.render()
        self.stats_view.render(self.status, self.stats)
        if self.tabs.currentWidget() is self.chart:
            self.chart.draw()

    def on_tab(self, _):
        w = self.tabs.currentWidget()
        if w is self.chart and self.chart.main is None:
            self.chart.on_instrument()
        elif w is self.stats_view:
            self.stats_view.render(self.status, self.stats)
        elif w is self.format_view:
            self.format_view.render(self.fi, self.meta)

    # ---- recent files / drag & drop / lifecycle -------------------------------------
    def add_recent(self, path):
        rec = [p for p in (self.settings.value("recent", []) or []) if p != path]
        self.settings.setValue("recent", [path] + rec[:14])
        self.rebuild_recent()

    def rebuild_recent(self):
        self.recent_menu.clear()
        rec = self.settings.value("recent", []) or []
        rec = [rec] if isinstance(rec, str) else rec
        for p in rec:
            self.recent_menu.addAction(p).triggered.connect(lambda _=False, p=p: self.open_path(p))
        if not rec:
            self.recent_menu.addAction(T("（沒有）")).setEnabled(False)

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        for u in e.mimeData().urls():
            if u.isLocalFile():
                self.open_path(u.toLocalFile())
                break

    def changeEvent(self, e):
        if e.type() in (QtCore.QEvent.PaletteChange, QtCore.QEvent.ApplicationPaletteChange):
            self.colors = theme()
            if hasattr(self, "chart") and self.chart.main is not None:
                self.chart.draw()
        super().changeEvent(e)

    def closeEvent(self, e):
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("splitter", self.split.saveState())
        if self.job is not None:
            self.job.cancelled = True
        super().closeEvent(e)
