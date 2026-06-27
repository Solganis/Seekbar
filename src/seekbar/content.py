import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from seekbar.theme import Theme

# The global hotkey is registered on Windows and macOS via OS APIs, and on Linux via X11 (XGrabKey,
# see _hotkey_linux.py). Under a pure Wayland session the X grab is unavailable; registration then
# fails gracefully and the tray remains the entry point.
_GLOBAL_HOTKEY_HELP: tuple[tuple[tuple[str, ...], str], ...] = (
    ((("Ctrl+Alt+S",), "Show / Hide"),) if sys.platform in ("win32", "darwin", "linux") else ()
)
_HELP_SHORTCUTS: tuple[tuple[tuple[str, ...], str] | None, ...] = (
    (("↑", "↓"), "Navigate"),
    (("PgUp", "PgDn"), "Jump page"),
    (("Home", "End"), "First / last"),
    (("Enter",), "Open selected"),
    (("Esc",), "Clear / Hide"),
    None,
    *_GLOBAL_HOTKEY_HELP,
    (("Ctrl+Q",), "Quit"),
    (("Ctrl+T",), "Toggle theme"),
    (("Alt+Drag",), "Move window"),
    None,
    (("F1",), "This help"),
    (("F2",), "Settings"),
    (("F3",), "About"),
)

_DONATE_WEB: tuple[tuple[str, str], ...] = (
    ("GitHub", "https://github.com/Solganis/Seekbar"),
    ("DonationAlerts", "https://www.donationalerts.com/r/Solganis"),
    ("Boosty", "https://boosty.to/solganis"),
)

_DONATE_CRYPTO: tuple[tuple[str, str], ...] = (
    ("TON", "UQAZDskr7UZE9Hn8Q8asCfmYIsicgL0KS9YNvRJ5NF53OPPo"),
    ("USDT (TRC-20)", "TG32fyLCxPcTCmtFXayDkvAvAF9goci9st"),
)


def help_html(theme: Theme) -> str:
    cap = f"background-color:{theme.outline}; color:{theme.on_surface};"
    key_sep = f'<span style="color:{theme.on_surface_variant};"> / </span>'
    desc_style = f"color:{theme.on_surface_variant};"
    groups: list[list[tuple[tuple[str, ...], str]]] = [[]]
    for entry in _HELP_SHORTCUTS:
        if entry is None:
            groups.append([])
        else:
            groups[-1].append(entry)
    left_group, right_group, bottom_group = [*groups, [], []][:3]

    def render_cells(group: list[tuple[tuple[str, ...], str]], index: int) -> str:
        if index >= len(group):
            return "<td></td><td></td>"
        cell_keys, cell_description = group[index]
        cell_caps = [f'<span style="{cap}">&nbsp;{k}&nbsp;</span>' for k in cell_keys]
        return (
            f'<td align="right" style="padding:3px 0;">{key_sep.join(cell_caps)}</td>'
            f'<td style="{desc_style} padding:3px 8px;">{cell_description}</td>'
        )

    divider_col = f'<td style="border-left:1px solid {theme.outline}; padding:0 8px;"></td>'
    max_rows = max(len(left_group), len(right_group))
    rows = [
        f"<tr>{render_cells(left_group, i)}{divider_col}{render_cells(right_group, i)}</tr>" for i in range(max_rows)
    ]
    if bottom_group:
        hr_style = f"border:none; border-top:1px solid {theme.outline};"
        divider_row = f'<tr><td colspan="5"><hr style="{hr_style}"></td></tr>'
        rows.append(divider_row)
        for keys, description in bottom_group:
            caps = [f'<span style="{cap}">&nbsp;{k}&nbsp;</span>' for k in keys]
            rows.append(
                f'<tr><td colspan="5" align="center" style="padding:3px 0;">'
                f"{key_sep.join(caps)}"
                f'<span style="{desc_style}"> {description}</span>'
                f"</td></tr>"
            )
    return f'<table cellspacing="2" align="center">{"".join(rows)}</table>'


def donate_html(theme: Theme) -> str:
    badge = f"background-color:{theme.outline}; color:{theme.on_surface}; text-decoration:none;"
    web_links = [f'<a href="{url}" style="{badge}">&nbsp;{label}&nbsp;</a>' for label, url in _DONATE_WEB]
    crypto_links = [
        f'<a href="copy:{address}" style="{badge}">&nbsp;{label}&nbsp;</a>' for label, address in _DONATE_CRYPTO
    ]
    return (
        '<table width="100%" cellspacing="4" cellpadding="0">'
        f'<tr><td align="center">{"&ensp;".join(web_links)}</td></tr>'
        f'<tr><td align="center">{"&ensp;".join(crypto_links)}</td></tr>'
        "</table>"
    )
