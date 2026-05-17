from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from seekbar.app import MainWindow

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot


@pytest.fixture
def window(qtbot: QtBot) -> MainWindow:
    w = MainWindow()
    qtbot.addWidget(w)
    return w
