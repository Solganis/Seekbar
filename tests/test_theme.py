import dataclasses
from unittest.mock import MagicMock, patch

import pytest
from assertpy2 import assert_that
from PySide6.QtCore import Qt

from seekbar.theme import DARK_THEME, LIGHT_THEME, Theme, ThemeMode, contrast_ratio, resolve_theme


class TestThemeMode:
    def test_values(self):
        assert_that(ThemeMode.AUTO.value).is_equal_to("auto")
        assert_that(ThemeMode.DARK.value).is_equal_to("dark")
        assert_that(ThemeMode.LIGHT.value).is_equal_to("light")

    def test_from_string(self):
        assert_that(ThemeMode("auto")).is_equal_to(ThemeMode.AUTO)
        assert_that(ThemeMode("dark")).is_equal_to(ThemeMode.DARK)
        assert_that(ThemeMode("light")).is_equal_to(ThemeMode.LIGHT)

    def test_invalid_value(self):
        assert_that(ThemeMode).raises(ValueError).when_called_with("invalid").matches("invalid")


class TestTheme:
    def test_frozen(self):
        assert_that(setattr).raises(dataclasses.FrozenInstanceError).when_called_with(DARK_THEME, "surface", "#000000")

    def test_slots(self):
        assert_that(hasattr(DARK_THEME, "__slots__")).is_true()

    def test_dark_theme_fields(self):
        assert_that(DARK_THEME.surface).is_equal_to("#1E1E1E")
        assert_that(DARK_THEME.surface_variant).is_equal_to("#2C2C2C")
        assert_that(DARK_THEME.on_surface).is_equal_to("#E0E0E0")
        assert_that(DARK_THEME.on_surface_variant).is_equal_to("#959595")
        assert_that(DARK_THEME.primary).is_equal_to("#BB86FC")
        assert_that(DARK_THEME.outline).is_equal_to("#333333")
        assert_that(DARK_THEME.hover).is_equal_to("#252525")
        assert_that(DARK_THEME.selected).is_equal_to("#332D41")
        assert_that(DARK_THEME.folder_color).is_equal_to("#B39B6E")
        assert_that(DARK_THEME.file_color).is_equal_to("#707070")
        assert_that(DARK_THEME.file_fold_color).is_equal_to("#808080")

    def test_light_theme_fields(self):
        assert_that(LIGHT_THEME.surface).is_equal_to("#F5F5F5")
        assert_that(LIGHT_THEME.surface_variant).is_equal_to("#E8E8E8")
        assert_that(LIGHT_THEME.on_surface).is_equal_to("#1C1C1C")
        assert_that(LIGHT_THEME.on_surface_variant).is_equal_to("#595959")
        assert_that(LIGHT_THEME.primary).is_equal_to("#6750A4")
        assert_that(LIGHT_THEME.outline).is_equal_to("#C8C8C8")
        assert_that(LIGHT_THEME.hover).is_equal_to("#ECECEC")
        assert_that(LIGHT_THEME.selected).is_equal_to("#E8DEF8")
        assert_that(LIGHT_THEME.folder_color).is_equal_to("#8B7340")
        assert_that(LIGHT_THEME.file_color).is_equal_to("#808080")
        assert_that(LIGHT_THEME.file_fold_color).is_equal_to("#909090")

    def test_dark_and_light_differ(self):
        assert_that(DARK_THEME).is_not_equal_to(LIGHT_THEME)

    def test_all_fields_are_strings(self):
        for field in dataclasses.fields(Theme):
            assert_that(getattr(DARK_THEME, field.name)).is_instance_of(str)
            assert_that(getattr(LIGHT_THEME, field.name)).is_instance_of(str)


class TestResolveTheme:
    @staticmethod
    def _patch_scheme(scheme: Qt.ColorScheme):
        mock_app = MagicMock()
        mock_app.styleHints.return_value.colorScheme.return_value = scheme
        return patch("seekbar.theme.QGuiApplication.instance", return_value=mock_app)

    def test_dark_mode(self):
        assert_that(resolve_theme(ThemeMode.DARK)).is_same_as(DARK_THEME)

    def test_light_mode(self):
        assert_that(resolve_theme(ThemeMode.LIGHT)).is_same_as(LIGHT_THEME)

    def test_auto_light_system(self):
        with self._patch_scheme(Qt.ColorScheme.Light):
            assert_that(resolve_theme(ThemeMode.AUTO)).is_same_as(LIGHT_THEME)

    def test_auto_dark_system(self):
        with self._patch_scheme(Qt.ColorScheme.Dark):
            assert_that(resolve_theme(ThemeMode.AUTO)).is_same_as(DARK_THEME)

    def test_auto_unknown_system(self):
        with self._patch_scheme(Qt.ColorScheme.Unknown):
            assert_that(resolve_theme(ThemeMode.AUTO)).is_same_as(DARK_THEME)

    def test_auto_no_app(self):
        with patch("seekbar.theme.QGuiApplication.instance", return_value=None):
            assert_that(resolve_theme(ThemeMode.AUTO)).is_same_as(DARK_THEME)


class TestContrastRatio:
    def test_same_color(self):
        assert_that(contrast_ratio("#000000", "#000000")).is_close_to(1.0, 1e-6)

    def test_black_on_white(self):
        assert_that(contrast_ratio("#000000", "#FFFFFF")).is_close_to(21.0, 1e-6)

    def test_order_independent(self):
        ratio_ab = contrast_ratio("#000000", "#FFFFFF")
        ratio_ba = contrast_ratio("#FFFFFF", "#000000")
        assert_that(ratio_ab).is_close_to(ratio_ba, 1e-6)

    def test_known_boundary(self):
        assert_that(contrast_ratio("#767676", "#FFFFFF")).is_close_to(4.54, 0.1)


class TestWcagContrast:
    _AA_RATIO = 4.5

    @pytest.mark.parametrize("theme", [DARK_THEME, LIGHT_THEME], ids=["dark", "light"])
    @pytest.mark.parametrize(
        ("text_attr", "bg_attr"),
        [
            ("on_surface", "surface"),
            ("on_surface", "surface_variant"),
            ("on_surface_variant", "surface"),
            ("on_surface_variant", "surface_variant"),
        ],
    )
    def test_text_on_background(self, theme: Theme, text_attr: str, bg_attr: str):
        text = getattr(theme, text_attr)
        background = getattr(theme, bg_attr)
        assert_that(contrast_ratio(text, background)).is_greater_than_or_equal_to(self._AA_RATIO)
