# Seekbar

[![Version](https://img.shields.io/github/v/release/Solganis/Seekbar)](https://github.com/Solganis/Seekbar/releases)
[![GitHub stars](https://img.shields.io/github/stars/Solganis/Seekbar)](https://github.com/Solganis/Seekbar/stargazers)
[![GitHub issues](https://img.shields.io/github/issues/Solganis/Seekbar)](https://github.com/Solganis/Seekbar/issues)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](https://opensource.org/licenses/MIT)

[![CI](https://github.com/Solganis/Seekbar/actions/workflows/ci.yml/badge.svg)](https://github.com/Solganis/Seekbar/actions/workflows/ci.yml)
[![Python 3.14+](https://img.shields.io/badge/python-3.14%2B-blue.svg)](https://www.python.org/)
[![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json)](https://github.com/astral-sh/uv)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![ty](https://img.shields.io/badge/type--checker-ty-D4AA00.svg)](https://github.com/astral-sh/ty)

**Instant cross-platform file search.** Native fast backends per OS, with `os.scandir` walk as universal fallback.

- **Windows**: NTFS MFT enumeration via `DeviceIoControl` for near-instant results
- **macOS**: Spotlight indexed search via `mdfind`
- **Linux**: `plocate`/`locate` indexed search

## Features

- **Native search backends**: MFT on Windows, Spotlight on macOS, locate on Linux, `os.scandir` fallback everywhere
- **Fuzzy matching**: underscores, hyphens, and spaces are interchangeable; token order doesn't matter
- **Smart scoring**: results ranked by match quality (exact > stem > prefix > suffix > contains > token)
- **Batch rendering**: results stream in batches for smooth UI even with thousands of hits
- **Dark/light/auto theme** with system detection (Ctrl+T to cycle)
- **WCAG AA contrast** and DPI-aware font scaling
- **Global hotkey** (Ctrl+Alt+S): show/hide from anywhere (Windows)
- **System tray**: minimizes to tray on close, double-click to restore
- **Context menu**: open file, open containing folder, copy path, copy filename
- **Frameless window** with title bar drag and Alt+Click drag anywhere
- **Keyboard-driven**: arrow keys, Page Up/Down, Enter to open, Esc to clear/close, F1 for shortcuts help

## Keyboard shortcuts

| Shortcut    | Action                                |
|-------------|---------------------------------------|
| Ctrl+Alt+S  | Show/hide window (global)             |
| Enter       | Open selected file                    |
| Esc         | Clear search text, then close window  |
| Ctrl+T      | Cycle theme (auto/light/dark)         |
| Ctrl+Q      | Quit application                      |
| Up/Down     | Navigate results                      |
| Page Up/Down| Jump by page                          |
| F1          | Toggle shortcuts help                 |
| F2          | Donate links                          |

## License

[MIT](LICENSE)
