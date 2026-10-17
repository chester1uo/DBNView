# PyInstaller spec for macOS, Windows and Linux:
#     pyinstaller --noconfirm packaging/dbnview.spec
# macOS  -> dist/DBNView.app   (then: xattr -cr dist/DBNView.app && codesign -s - --force --deep dist/DBNView.app)
# others -> dist/DBNView/DBNView(.exe)
import os
import sys

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

_init = open(os.path.join(SPECPATH, "..", "src", "dbnview", "__init__.py"), encoding="utf-8").read()
VERSION = _init.split('__version__ = "', 1)[1].split('"', 1)[0]

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
ICON = {"darwin": "dbnview.icns", "win32": "dbnview.ico"}.get(sys.platform, "icon.png")

a = Analysis(
    [os.path.join(SPECPATH, "launcher.py")],
    pathex=[os.path.join(ROOT, "src")],
    datas=collect_data_files("dbnview") + collect_data_files("pyqtgraph"),
    hiddenimports=collect_submodules("dbnview.gui") + collect_submodules("dbnview.reference")
    + collect_submodules("pyqtgraph.opengl") + collect_submodules("OpenGL"),
    excludes=["tkinter", "matplotlib", "PyQt5", "PyQt6", "IPython", "pandas", "scipy", "textual", "plotext",
              "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.Qt3DCore",
              "PySide6.QtMultimedia", "PySide6.QtPdf"],
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="DBNView", console=False,
          icon=os.path.join(SPECPATH, ICON), argv_emulation=False)
coll = COLLECT(exe, a.binaries, a.datas, name="DBNView")

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="DBNView.app",
        icon=os.path.join(SPECPATH, "dbnview.icns"),
        bundle_identifier="io.github.chester1uo.dbnview",
        version=VERSION,
        info_plist={
            "CFBundleVersion": VERSION,
            "CFBundleName": "DBNView",
            "CFBundleDisplayName": "DBNView",
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
