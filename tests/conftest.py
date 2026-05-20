from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest
from PySide6.QtCore import QSettings

from seekbar.app import MainWindow, SETTINGS_APP, SETTINGS_ORG

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot


@pytest.fixture(autouse=True)
def _clear_settings():
    settings = QSettings(SETTINGS_ORG, SETTINGS_APP)
    settings.clear()
    yield
    settings.clear()


@pytest.fixture
def window(qtbot: QtBot) -> MainWindow:
    main_window = MainWindow()
    main_window._worker = MagicMock()
    qtbot.addWidget(main_window)
    return main_window
