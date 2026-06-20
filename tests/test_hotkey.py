import sys

import pytest
from assertpy2 import assert_that

if sys.platform != "win32":
    pytest.skip("Windows-only tests", allow_module_level=True)

from unittest.mock import MagicMock, patch

# noinspection PyProtectedMember
from seekbar.hotkey import (
    MOD_ALT,
    MOD_CONTROL,
    VK_S,
    WM_HOTKEY,
    _HOTKEY_ID,
    register_hotkey,
    unregister_hotkey,
)


class TestConstants:
    def test_wm_hotkey(self):
        assert_that(WM_HOTKEY).is_equal_to(0x0312)

    def test_modifiers(self):
        assert_that(MOD_ALT).is_equal_to(0x0001)
        assert_that(MOD_CONTROL).is_equal_to(0x0002)

    def test_vk_s(self):
        assert_that(VK_S).is_equal_to(0x53)

    def test_hotkey_id(self):
        assert_that(_HOTKEY_ID).is_equal_to(1)


class TestRegisterHotkey:
    def test_success(self):
        with patch("seekbar.hotkey.user32.RegisterHotKey", return_value=1):
            assert_that(register_hotkey()).is_true()

    def test_failure(self):
        with patch("seekbar.hotkey.user32.RegisterHotKey", return_value=0):
            assert_that(register_hotkey()).is_false()

    def test_calls_with_correct_args(self):
        mock_register = MagicMock(return_value=1)
        with patch("seekbar.hotkey.user32.RegisterHotKey", mock_register):
            register_hotkey()
        mock_register.assert_called_once_with(None, _HOTKEY_ID, MOD_CONTROL | MOD_ALT, VK_S)


class TestUnregisterHotkey:
    def test_success(self):
        with patch("seekbar.hotkey.user32.UnregisterHotKey", return_value=1):
            assert_that(unregister_hotkey()).is_true()

    def test_failure(self):
        with patch("seekbar.hotkey.user32.UnregisterHotKey", return_value=0):
            assert_that(unregister_hotkey()).is_false()

    def test_calls_with_correct_args(self):
        mock_unregister = MagicMock(return_value=1)
        with patch("seekbar.hotkey.user32.UnregisterHotKey", mock_unregister):
            unregister_hotkey()
        mock_unregister.assert_called_once_with(None, _HOTKEY_ID)
