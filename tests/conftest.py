from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtCore import QSettings

from seekbar.app import MainWindow, SETTINGS_APP, SETTINGS_ORG

if TYPE_CHECKING:
    from collections.abc import Iterator

    from pytestqt.qtbot import QtBot

_QT_TEST_FILES = {"test_app.py", "test_theme.py"}


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Run Qt-heavy test files last to avoid coverage overhead from QApplication event loop."""
    items.sort(key=lambda item: item.path.name in _QT_TEST_FILES)


@pytest.fixture(autouse=True)
def _clear_settings():
    settings = QSettings(SETTINGS_ORG, SETTINGS_APP)
    settings.clear()
    yield
    settings.clear()


# noinspection PyProtectedMember
@pytest.fixture
def window(qtbot: QtBot) -> Iterator[MainWindow]:
    with patch("seekbar.app._hotkey") as mock_hk:
        mock_hk.register_hotkey.return_value = False
        main_window = MainWindow()
    main_window._worker = MagicMock()
    qtbot.addWidget(main_window)
    yield main_window
    main_window._debounce_timer.stop()
    main_window._searching_timer.stop()
    main_window._help_hide_timer.stop()
    main_window._temp_status_timer.stop()
    main_window._height_anim.stop()
    main_window._tray.hide()
