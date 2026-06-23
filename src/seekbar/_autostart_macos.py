import sys

if sys.platform != "darwin":  # pragma: no cover - macOS-only module
    msg = "This module is only available on macOS"
    raise ImportError(msg)

import plistlib
from pathlib import Path

from seekbar.autostart import _launch_argv

_LABEL = "com.seekbar.autostart"


def _plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{_LABEL}.plist"


def is_enabled() -> bool:
    return _plist_path().exists()


def set_enabled(enabled: bool) -> None:  # noqa: FBT001 - simple on/off toggle
    path = _plist_path()
    if enabled:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as plist_file:
            plistlib.dump({"Label": _LABEL, "ProgramArguments": _launch_argv(), "RunAtLoad": True}, plist_file)
    else:
        path.unlink(missing_ok=True)
