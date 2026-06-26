from typing import TYPE_CHECKING

from seekbar.constants import _FONT_FAMILY

if TYPE_CHECKING:
    from seekbar.theme import Theme


def menu_qss(theme: Theme) -> str:
    return f"""
            QMenu {{
                background-color: {theme.surface_variant};
                color: {theme.on_surface};
                border: 1px solid {theme.outline};
                border-radius: 8px;
                padding: 4px;
                font-family: "{_FONT_FAMILY}", sans-serif;
                font-size: 9pt;
            }}
            QMenu::item {{
                padding: 8px 16px;
                border-radius: 4px;
            }}
            QMenu::item:selected {{
                background-color: {theme.hover};
            }}
        """


def accent_swatch_qss(theme: Theme, selected: str, primary: str) -> str:
    # Two-tone chip: left half is the result-row fill, right half is the bar/scroll accent.
    return f"""
            QPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {selected}, stop:0.5 {selected}, stop:0.5 {primary}, stop:1 {primary});
                border: 2px solid transparent;
                border-radius: 7px;
            }}
            QPushButton:hover {{ border: 2px solid {theme.on_surface_variant}; }}
            QPushButton:checked {{ border: 2px solid {theme.on_surface}; }}
        """


def window_qss(theme: Theme, radius: int, search_height: int, menu: str) -> str:
    return f"""
            #card {{
                background-color: {theme.surface};
                border: 1px solid {theme.outline};
                border-radius: {radius}px;
            }}
            #searchInput {{
                background-color: transparent;
                border: none;
                color: {theme.on_surface};
                font-size: 11pt;
                font-family: "{_FONT_FAMILY}", sans-serif;
                padding: 0 16px;
                selection-background-color: {theme.primary};
                selection-color: {theme.surface};
            }}
            #separator {{
                background-color: {theme.outline};
                border: none;
            }}
            #statusLabel {{
                color: {theme.on_surface_variant};
                font-size: 8pt;
                font-family: "{_FONT_FAMILY}", sans-serif;
                padding: 0;
                background-color: transparent;
            }}
            #closeButton {{
                background-color: transparent;
                border: none;
                border-radius: {(search_height - 12) // 2}px;
            }}
            #closeButton:hover {{
                background-color: {theme.hover};
            }}
            #closeButton:pressed {{
                background-color: {theme.outline};
            }}
            #resultList {{
                background-color: transparent;
                border: none;
                outline: none;
            }}
            #resultList::item {{
                border: none;
                padding: 0;
            }}
            QScrollBar:vertical {{
                background: transparent;
                width: 14px;
                margin: 4px 2px;
            }}
            QScrollBar::handle:vertical {{
                background: {theme.outline};
                border-radius: 5px;
                min-height: 24px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {theme.on_surface_variant};
            }}
            QScrollBar::handle:vertical:pressed {{
                background: {theme.primary};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
            {menu}
            #helpPopup, #donatePopup {{
                background-color: {theme.surface_variant};
                color: {theme.on_surface};
                border: none;
                padding: 12px 16px;
                font-family: "{_FONT_FAMILY}", sans-serif;
                font-size: 9pt;
            }}
            #settingsPopup {{
                background-color: {theme.surface_variant};
                border: none;
            }}
            #settingsPopup QLabel {{
                color: {theme.on_surface_variant};
                background: transparent;
                font-family: "{_FONT_FAMILY}", sans-serif;
                font-size: 9pt;
            }}
            #settingsPopup QPushButton#trayButton {{
                background-color: {theme.outline};
                color: {theme.on_surface};
                border: none;
                border-radius: 6px;
                padding: 3px 12px;
                font-family: "{_FONT_FAMILY}", sans-serif;
                font-size: 8pt;
            }}
            #settingsPopup QPushButton#trayButton:hover {{
                background-color: {theme.hover};
            }}
            #settingsPopup QPushButton#trayButton:checked {{
                background-color: {theme.primary};
                color: {theme.surface};
            }}
        """
