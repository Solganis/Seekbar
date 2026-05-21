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

**Instant file search for Windows.** Finds files across all drives in milliseconds using direct NTFS MFT enumeration, with `os.scandir` fallback for non-NTFS volumes.

Inspired by [Everything](https://www.voidtools.com/), built from scratch in Python as a lightweight alternative with fuzzy matching and a modern UI.

**This is a personal passion project**: a way to sharpen my Python skills while trying to build something useful for others.

## Features

- **MFT search**: reads the NTFS Master File Table directly via `DeviceIoControl`, bypassing the filesystem for near-instant results
- **Fuzzy matching**: underscores, hyphens, and spaces are interchangeable; token order doesn't matter
- **Smart scoring**: results ranked by match quality (exact > stem > prefix > suffix > contains > token)
- **Batch rendering**: results stream in batches for smooth UI even with thousands of hits
- **Dark/light/auto theme** with system detection (Ctrl+T to cycle)
- **WCAG AA contrast** and DPI-aware font scaling
- **Global hotkey** (Ctrl+Alt+S): show/hide from anywhere
- **System tray**: minimizes to tray on close, double-click to restore
- **Context menu**: open file, open containing folder, copy path, copy filename
- **Frameless window** with title bar drag and Alt+Click drag anywhere
- **Keyboard-driven**: arrow keys, Page Up/Down, Enter to open, Esc to clear/close, F1 for shortcuts help

## Keyboard shortcuts

| Shortcut | Action |
|----------|--------|
| Ctrl+Alt+S | Show/hide window (global) |
| Enter | Open selected file |
| Esc | Clear search text, then close window |
| Ctrl+T | Cycle theme (auto/light/dark) |
| Ctrl+Q | Quit application |
| Up/Down | Navigate results |
| Page Up/Down | Jump by page |
| F1 | Toggle shortcuts help |

## Installation

### Download

Grab the latest `Seekbar.exe` from [Releases](https://github.com/Solganis/Seekbar/releases). No installation required, just run.

MFT search requires administrator privileges to read raw disk data. Without elevation, Seekbar falls back to `os.scandir` (slower but still functional).

### From source

```
git clone https://github.com/Solganis/Seekbar.git
cd Seekbar
uv sync
uv run seekbar
```

## Building

```
uv run python scripts/export_icon.py
uv run pyinstaller seekbar.spec --distpath dist --workpath build --clean
```

Output: `dist/Seekbar.exe` (~45 MB, includes PySide6 runtime).

## License

[MIT](LICENSE)
