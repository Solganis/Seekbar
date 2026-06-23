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
    excludes=[],
    noarchive=False,
)

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
    strip=False,
    upx=False,
    upx_exclude=[],
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
