import sys

_APP_NAME = "Seekbar"


def _launch_argv() -> list[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable]
    return [sys.executable, "-m", "seekbar"]


def is_enabled() -> bool:
    match sys.platform:
        case "win32":
            from seekbar._autostart_windows import is_enabled as impl  # noqa: PLC0415 - platform-specific backend
        case "darwin":
            from seekbar._autostart_macos import is_enabled as impl  # noqa: PLC0415 - platform-specific backend
        case "linux":
            from seekbar._autostart_linux import is_enabled as impl  # noqa: PLC0415 - platform-specific backend
        case _:
            return False
    return impl()


def set_enabled(enabled: bool) -> None:  # noqa: FBT001 - simple on/off toggle
    match sys.platform:
        case "win32":
            from seekbar._autostart_windows import set_enabled as impl  # noqa: PLC0415 - platform-specific backend
        case "darwin":
            from seekbar._autostart_macos import set_enabled as impl  # noqa: PLC0415 - platform-specific backend
        case "linux":
            from seekbar._autostart_linux import set_enabled as impl  # noqa: PLC0415 - platform-specific backend
        case _:
            return
    impl(enabled)
