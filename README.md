<h1 align="center">Seekbar</h1>

<p align="center">
  <b>Minimalist cross-platform file search. One bar, every drive.</b><br>
  Native per-OS backends, with an <code>os.scandir</code> walk as universal fallback.
</p>

<p align="center">
  <a href="https://github.com/Solganis/Seekbar/releases"><img src="https://img.shields.io/github/v/release/Solganis/Seekbar" alt="Version"></a>
  <a href="https://github.com/Solganis/Seekbar/actions/workflows/ci.yml"><img src="https://github.com/Solganis/Seekbar/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://codecov.io/github/Solganis/Seekbar"><img src="https://codecov.io/github/Solganis/Seekbar/graph/badge.svg" alt="codecov"></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/python-3.14-blue.svg" alt="Python 3.14"></a>
  <a href="https://github.com/astral-sh/uv"><img src="https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json" alt="uv"></a>
  <a href="https://github.com/astral-sh/ruff"><img src="https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json" alt="Ruff"></a>
  <a href="https://github.com/astral-sh/ty"><img src="https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ty/main/assets/badge/v0.json" alt="ty"></a>
</p>

<p align="center">
  <img src="assets/screenshot.png" alt="Seekbar - dark and light themes" width="75%">
</p>

---

<h2 align="center">Quick start</h2>

<p align="center">
  Download the latest build from <a href="https://github.com/Solganis/Seekbar/releases">Releases</a> and run it, or run from source:
</p>

<p align="center">
  <code>uv sync</code> &nbsp;then&nbsp; <code>uv run seekbar</code>
</p>

<h2 align="center">Features</h2>

<p align="center">
  <b>Native backends</b> - NTFS MFT on Windows, Spotlight on macOS, <code>plocate</code>/<code>locate</code> on Linux<br>
  <b>Flexible matching</b> - underscores, hyphens, and spaces are interchangeable; token order doesn't matter<br>
  <b>Smart ranking</b> - results scored by match quality and recency, streamed as they are found<br>
  <b>Keyboard-driven</b>, frameless, with a system tray and a global hotkey (Ctrl+Alt+S, Windows and macOS)<br>
  <b>Dark / light / auto theme</b> with system detection
</p>

<h2 align="center">Keyboard shortcuts</h2>

<div align="center">
<table>
<tr><td><kbd>Ctrl+Alt+S</kbd></td><td>Show / hide window (global, Windows and macOS)</td></tr>
<tr><td><kbd>F1</kbd></td><td>Toggle shortcuts help</td></tr>
<tr><td><kbd>Enter</kbd></td><td>Open selected file</td></tr>
<tr><td><kbd>Esc</kbd></td><td>Clear search text, then close window</td></tr>
<tr><td><kbd>Ctrl+T</kbd></td><td>Cycle theme (auto / light / dark)</td></tr>
<tr><td><kbd>Ctrl+Q</kbd></td><td>Quit application</td></tr>
<tr><td><kbd>Up</kbd> / <kbd>Down</kbd></td><td>Navigate results</td></tr>
<tr><td><kbd>Page Up</kbd> / <kbd>Page Down</kbd></td><td>Jump by page</td></tr>
<tr><td><kbd>Home</kbd> / <kbd>End</kbd></td><td>Jump to first / last result</td></tr>
<tr><td><kbd>F2</kbd></td><td>Donate links</td></tr>
</table>
</div>
