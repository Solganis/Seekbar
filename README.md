<h1 align="center">Seekbar</h1>

<p align="center">
  <b>Instant cross-platform file search. One bar, every drive.</b><br>
  Native per-OS backends, with an <code>os.scandir</code> walk as universal fallback.
</p>

<p align="center">
  <a href="https://github.com/Solganis/Seekbar/releases"><img src="https://img.shields.io/github/v/release/Solganis/Seekbar" alt="Version"></a>
  <a href="https://github.com/Solganis/Seekbar/actions/workflows/ci.yml"><img src="https://github.com/Solganis/Seekbar/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/python-3.14-blue.svg" alt="Python 3.14"></a>
  <a href="https://github.com/astral-sh/uv"><img src="https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json" alt="uv"></a>
  <a href="https://github.com/astral-sh/ruff"><img src="https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json" alt="Ruff"></a>
  <a href="https://github.com/astral-sh/ty"><img src="https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ty/main/assets/badge/v0.json" alt="ty"></a>
</p>

---

## Quick start

Download the latest build from [Releases](https://github.com/Solganis/Seekbar/releases) and run it.

To run from source:

```bash
uv sync
uv run seekbar
```

## Features

- **Native backends** - NTFS MFT on Windows, Spotlight on macOS, `plocate`/`locate` on Linux, `os.scandir` fallback everywhere
- **Fuzzy matching** - underscores, hyphens, and spaces are interchangeable; token order doesn't matter
- **Smart ranking** - results scored by match quality and recency, streamed as they are found
- **Dark / light / auto theme** with system detection
- **Keyboard-driven**, frameless, with a global hotkey (Ctrl+Alt+S) and system tray

## Keyboard shortcuts

| Shortcut     | Action                               |
|--------------|--------------------------------------|
| Ctrl+Alt+S   | Show/hide window (global)            |
| F1           | Toggle shortcuts help                |
| Enter        | Open selected file                   |
| Esc          | Clear search text, then close window |
| Ctrl+T       | Cycle theme (auto/light/dark)        |
| Ctrl+Q       | Quit application                     |
| Up/Down      | Navigate results                     |
| Page Up/Down | Jump by page                         |
| F2           | Donate links                         |
