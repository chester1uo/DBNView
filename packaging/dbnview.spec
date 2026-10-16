# PyInstaller spec — build with:  .venv/bin/pyinstaller --noconfirm packaging/dbnview.spec
import os
from PyInstaller.utils.hooks import collect_data_files, collect_submodules
ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
SRC = os.path.join(ROOT, "src")

a = Analysis(
    [os.path.join(SRC, "app.py")],
    pathex=[SRC],
    datas=[(os.path.join(SRC, "spec.json"), "."), (os.path.join(SRC, "ui.html"), ".")]
          + collect_data_files("pyqtgraph"),
    hiddenimports=["locales", "locales.zh_Hant", "locales.zh_Hans", "locales.en", "locales.ja",
                   "locales.de", "locales.ko", "locales.es", "ui_strings", "i18n", "docs", "enum_values",
                   "charts", "analytics", "options", "ivsurface", "core"]
                  + collect_submodules("pyqtgraph.opengl") + collect_submodules("OpenGL"),
    excludes=["tkinter", "matplotlib", "PyQt5", "PyQt6", "IPython", "pandas", "scipy",
              "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.Qt3DCore",
              "PySide6.QtMultimedia", "PySide6.QtPdf"],
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="dbnview", console=False,
          argv_emulation=False, target_arch=None)
coll = COLLECT(exe, a.binaries, a.datas, name="dbnview")
app = BUNDLE(
    coll,
    name="dbnview.app",
    icon=os.path.join(SPECPATH, "dbnview.icns"),
    bundle_identifier="local.dbnview",
    info_plist={
        "CFBundleName": "dbnview",
        "CFBundleDisplayName": "dbnview",
        "CFBundleShortVersionString": "0.3.0",
        "NSHighResolutionCapable": True,
        "LSApplicationCategoryType": "public.app-category.finance",
        "CFBundleDocumentTypes": [{
            "CFBundleTypeName": "Databento DBN file",
            "CFBundleTypeRole": "Viewer",
            "LSHandlerRank": "Alternate",
            "CFBundleTypeExtensions": ["dbn", "zst"],
        }],
    },
)
