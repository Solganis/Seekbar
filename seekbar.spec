# -*- mode: python ; coding: utf-8 -*-
import sys

sys.path.insert(0, "src")
from seekbar import __version__

if sys.platform == "win32":
    icon = "assets/seekbar.ico"
elif sys.platform == "darwin":
    icon = "assets/seekbar.icns"
else:
    icon = None

# The app uses only QtCore/QtGui/QtWidgets/QtNetwork. Drop the unused Essentials modules from the freeze.
# QtDBus is intentionally kept: the Linux system-tray (StatusNotifierItem) needs it.
_EXCLUDES = [
    "PySide6.QtQml",
    "PySide6.QtQuick",
    "PySide6.QtQuickWidgets",
    "PySide6.QtQuickControls2",
    "PySide6.QtSql",
    "PySide6.QtSvg",
    "PySide6.QtSvgWidgets",
    "PySide6.QtPrintSupport",
    "PySide6.QtOpenGL",
    "PySide6.QtOpenGLWidgets",
    "PySide6.QtTest",
    "PySide6.QtXml",
    "PySide6.QtConcurrent",
    "PySide6.QtHelp",
    "PySide6.QtDesigner",
    "PySide6.QtUiTools",
    "PySide6.QtStateMachine",
    "PySide6.QtNetworkAuth",
]


def _windows_version_info():
    from PyInstaller.utils.win32.versioninfo import (
        FixedFileInfo,
        StringFileInfo,
        StringStruct,
        StringTable,
        VarFileInfo,
        VarStruct,
        VSVersionInfo,
    )

    parts = [int(part) for part in __version__.split(".")]
    vers = tuple((parts + [0, 0, 0, 0])[:4])
    return VSVersionInfo(
        ffi=FixedFileInfo(filevers=vers, prodvers=vers),
        kids=[
            StringFileInfo(
                [
                    StringTable(
                        "040904B0",
                        [
                            StringStruct("CompanyName", "Solganis"),
                            StringStruct("FileDescription", "Seekbar - cross-platform file search"),
                            StringStruct("FileVersion", __version__),
                            StringStruct("InternalName", "Seekbar"),
                            StringStruct("OriginalFilename", "Seekbar.exe"),
                            StringStruct("ProductName", "Seekbar"),
                            StringStruct("ProductVersion", __version__),
                        ],
                    )
                ]
            ),
            VarFileInfo([VarStruct("Translation", [1033, 1200])]),
        ],
    )


version = _windows_version_info() if sys.platform == "win32" else None

a = Analysis(
    ["src/seekbar/__main__.py"],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=_EXCLUDES,
    noarchive=False,
)

# The app never loads Qt translations; drop the ~300 bundled .qm files.
a.datas = [entry for entry in a.datas if "translations" not in entry[0].replace("\\", "/").split("/")]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="Seekbar",
    debug=False,
    bootloader_ignore_signals=False,
    strip=sys.platform != "win32",
    upx=False,  # PyInstaller disables UPX on Linux/macOS anyway, and on Windows it only risks AV false positives
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon,
    version=version,
)

if sys.platform == "darwin":
    app = BUNDLE(
        exe,
        name="Seekbar.app",
        icon=icon,
        bundle_identifier="com.solganis.seekbar",
        version=__version__,
    )
