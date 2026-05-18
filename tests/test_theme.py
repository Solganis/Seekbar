from __future__ import annotations

import dataclasses
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtCore import Qt

from seekbar.theme import DARK_THEME, LIGHT_THEME, Theme, ThemeMode, resolve_theme


class TestThemeMode:
    def test_values(self):
        assert ThemeMode.AUTO.value == "auto"
        assert ThemeMode.DARK.value == "dark"
        assert ThemeMode.LIGHT.value == "light"

    def test_from_string(self):
        assert ThemeMode("auto") == ThemeMode.AUTO
        assert ThemeMode("dark") == ThemeMode.DARK
        assert ThemeMode("light") == ThemeMode.LIGHT

    def test_invalid_value(self):
        with pytest.raises(ValueError, match="invalid"):
            ThemeMode("invalid")


class TestTheme:
    def test_frozen(self):
        with pytest.raises(dataclasses.FrozenInstanceError):
            DARK_THEME.surface = "#000000"

    def test_slots(self):
        assert hasattr(DARK_THEME, "__slots__")

    def test_dark_theme_fields(self):
        assert DARK_THEME.surface == "#1E1E1E"
        assert DARK_THEME.surface_variant == "#2C2C2C"
        assert DARK_THEME.on_surface == "#E0E0E0"
        assert DARK_THEME.on_surface_variant == "#888888"
        assert DARK_THEME.primary == "#BB86FC"
        assert DARK_THEME.outline == "#333333"
        assert DARK_THEME.hover == "#252525"
        assert DARK_THEME.selected == "#332D41"
        assert DARK_THEME.folder_color == "#B39B6E"
        assert DARK_THEME.file_color == "#707070"
        assert DARK_THEME.file_fold_color == "#808080"

    def test_light_theme_fields(self):
        assert LIGHT_THEME.surface == "#F5F5F5"
        assert LIGHT_THEME.surface_variant == "#E8E8E8"
        assert LIGHT_THEME.on_surface == "#1C1C1C"
        assert LIGHT_THEME.on_surface_variant == "#6B6B6B"
        assert LIGHT_THEME.primary == "#6750A4"
        assert LIGHT_THEME.outline == "#C8C8C8"
        assert LIGHT_THEME.hover == "#ECECEC"
        assert LIGHT_THEME.selected == "#E8DEF8"
        assert LIGHT_THEME.folder_color == "#8B7340"
        assert LIGHT_THEME.file_color == "#808080"
        assert LIGHT_THEME.file_fold_color == "#909090"

    def test_dark_and_light_differ(self):
        assert DARK_THEME != LIGHT_THEME

    def test_all_fields_are_strings(self):
        for field in dataclasses.fields(Theme):
            assert isinstance(getattr(DARK_THEME, field.name), str)
            assert isinstance(getattr(LIGHT_THEME, field.name), str)


class TestResolveTheme:
    @staticmethod
    def _patch_scheme(scheme: Qt.ColorScheme):
        mock_app = MagicMock()
        mock_app.styleHints.return_value.colorScheme.return_value = scheme
        return patch("seekbar.theme.QGuiApplication.instance", return_value=mock_app)

    def test_dark_mode(self):
        assert resolve_theme(ThemeMode.DARK) is DARK_THEME

    def test_light_mode(self):
        assert resolve_theme(ThemeMode.LIGHT) is LIGHT_THEME

    def test_auto_light_system(self):
        with self._patch_scheme(Qt.ColorScheme.Light):
            assert resolve_theme(ThemeMode.AUTO) is LIGHT_THEME

    def test_auto_dark_system(self):
        with self._patch_scheme(Qt.ColorScheme.Dark):
            assert resolve_theme(ThemeMode.AUTO) is DARK_THEME

    def test_auto_unknown_system(self):
        with self._patch_scheme(Qt.ColorScheme.Unknown):
            assert resolve_theme(ThemeMode.AUTO) is DARK_THEME

    def test_auto_no_app(self):
        with patch("seekbar.theme.QGuiApplication.instance", return_value=None):
            assert resolve_theme(ThemeMode.AUTO) is DARK_THEME
