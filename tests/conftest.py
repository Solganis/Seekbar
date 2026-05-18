from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from PySide6.QtCore import QSettings

from seekbar.app import MainWindow, _SETTINGS_APP, _SETTINGS_ORG

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot


@pytest.fixture(autouse=True)
def _clear_settings():
    settings = QSettings(_SETTINGS_ORG, _SETTINGS_APP)
    settings.clear()
    yield
    settings.clear()


@pytest.fixture
def window(qtbot: QtBot) -> MainWindow:
    main_window = MainWindow()
    qtbot.addWidget(main_window)
    return main_window
