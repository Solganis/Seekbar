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
        assert WM_HOTKEY == 0x0312

    def test_modifiers(self):
        assert MOD_ALT == 0x0001
        assert MOD_CONTROL == 0x0002

    def test_vk_s(self):
        assert VK_S == 0x53

    def test_hotkey_id(self):
        assert _HOTKEY_ID == 1


class TestRegisterHotkey:
    def test_success(self):
        with patch("seekbar.hotkey.user32.RegisterHotKey", return_value=1):
            assert register_hotkey() is True

    def test_failure(self):
        with patch("seekbar.hotkey.user32.RegisterHotKey", return_value=0):
            assert register_hotkey() is False

    def test_calls_with_correct_args(self):
        mock_register = MagicMock(return_value=1)
        with patch("seekbar.hotkey.user32.RegisterHotKey", mock_register):
            register_hotkey()
        mock_register.assert_called_once_with(None, _HOTKEY_ID, MOD_CONTROL | MOD_ALT, VK_S)


class TestUnregisterHotkey:
    def test_success(self):
        with patch("seekbar.hotkey.user32.UnregisterHotKey", return_value=1):
            assert unregister_hotkey() is True

    def test_failure(self):
        with patch("seekbar.hotkey.user32.UnregisterHotKey", return_value=0):
            assert unregister_hotkey() is False

    def test_calls_with_correct_args(self):
        mock_unregister = MagicMock(return_value=1)
        with patch("seekbar.hotkey.user32.UnregisterHotKey", mock_unregister):
            unregister_hotkey()
        mock_unregister.assert_called_once_with(None, _HOTKEY_ID)
