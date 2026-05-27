# mac-computer-use-mcp

A native macOS MCP server that gives Claude Code full computer-use capabilities — screenshots, clicks, typing, scrolling, drag, and accessibility-tree inspection — with no Docker, no VM, and no remote APIs. Everything runs locally via `osascript` and `cliclick`.

Works great for controlling any Mac app, including **iPhone Mirroring** to drive your iPhone from Claude.

## Tools

| Tool | Description |
|------|-------------|
| `screenshot` | Capture the full screen as a base64 PNG |
| `find_elements` | Walk the accessibility tree of any running app and return UI elements with exact screen coordinates |
| `click` | Left, right, or double-click at a screen coordinate |
| `drag` | Click-and-drag between two coordinates (swipe gestures, sliders, reordering) |
| `type_text` | Type a string at the current cursor position |
| `key_press` | Press keys and combos: `return`, `escape`, `cmd-c`, `cmd-shift-z`, `ctrl-tab`, etc. |
| `scroll` | Scroll up or down at a coordinate |
| `move_mouse` | Move the cursor without clicking |
| `open_app` | Open any macOS app by name |
| `get_screen_size` | Get screen dimensions in logical points |

## Requirements

- macOS (tested on Sonoma / Sequoia)
- Python 3.9+
- [cliclick](https://github.com/BlueM/cliclick) — `brew install cliclick`

## Installation

**1. Install dependencies**

```bash
brew install cliclick
pip3 install --break-system-packages mcp
```

**2. Clone the repo**

```bash
git clone https://github.com/bfreeman/mac-computer-use-mcp.git ~/.claude/mcp-servers/mac-computer-use
```

**3. Register with Claude Code**

```bash
claude mcp add mac-computer-use -- /opt/homebrew/bin/python3 ~/.claude/mcp-servers/mac-computer-use/server.py
```

Then restart Claude Code. The tools will appear automatically.

## macOS Permissions

The server needs two TCC permissions granted to your terminal app (Terminal, iTerm2, etc.):

- **Accessibility** — for `osascript` clicks, keystrokes, and the accessibility tree walker
- **Screen Recording** — for `screencapture`

Grant both in **System Settings → Privacy & Security**.

## Coordinate System

All coordinates are **logical screen points** — the same space reported by the macOS accessibility tree and `NSScreen`. On Retina displays the screenshot image is at 2× pixel density, so divide image pixel coordinates by 2 to get the logical point to pass to `click`.

Use `find_elements` to get accurate coordinates from the accessibility tree instead of measuring screenshots by hand.

## Usage Example

```
# In Claude Code:
Take a screenshot to see what's on screen.
Find the Save button in the Safari window.
Click the button at the coordinates find_elements returned.
```

## iPhone Mirroring

`find_elements` works on the `iPhone Mirroring` process itself (its window chrome), but the iPhone's internal UI isn't exposed via the Mac accessibility tree. For iPhone interaction:

1. Use `screenshot` to see the iPhone screen.
2. Calculate coordinates: iPhone Mirroring window position + offset within the iPhone screen.
3. `click` / `drag` / `type_text` / `key_press` work as expected once you have coordinates.
4. Use the iPhone Mirroring **View** menu (`View → Spotlight`, `View → Home Screen`, etc.) via `key_press` or AppleScript for reliable navigation.

## License

MIT
