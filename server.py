#!/usr/bin/env python3
"""
mac-computer-use-mcp — native macOS computer-use MCP server for Claude Code.

Exposes screenshot, click, type, key_press, scroll, drag, find_elements,
open_app, and get_screen_size as MCP tools backed by osascript + cliclick.
All coordinates are in logical screen points (same space as the macOS
accessibility tree and System Events).
"""
import subprocess
import base64
import json
import os
import asyncio
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp import types

app = Server("mac-computer-use")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run(cmd, **kwargs):
    return subprocess.run(cmd, capture_output=True, text=True, **kwargs)


def _osascript(script):
    result = _run(["osascript", "-e", script])
    return result.stdout.strip(), result.stderr.strip()


def _cliclick(*args):
    subprocess.run(["/opt/homebrew/bin/cliclick", *args], capture_output=True)


def _take_screenshot():
    path = f"/tmp/mcu_{os.getpid()}.png"
    # shell=True inherits the terminal's Screen Recording TCC permission
    subprocess.run(f"screencapture -x {path}", shell=True, capture_output=True)
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        subprocess.run(
            ["osascript", "-e", f'do shell script "screencapture -x {path}"'],
            capture_output=True,
        )
    # Read image dimensions to compute the pixel→logical scale factor
    sips = _run(["sips", "-g", "pixelWidth", "-g", "pixelHeight", path])
    img_w = img_h = None
    for line in sips.stdout.splitlines():
        if "pixelWidth" in line:
            img_w = int(line.split(":")[1].strip())
        elif "pixelHeight" in line:
            img_h = int(line.split(":")[1].strip())

    with open(path, "rb") as f:
        data = base64.b64encode(f.read()).decode()
    os.unlink(path)

    logical = _get_screen_size()
    scale = round(img_w / logical["width"], 2) if img_w else None

    return {
        "data": data,
        "img_w": img_w,
        "img_h": img_h,
        "logical_w": logical["width"],
        "logical_h": logical["height"],
        "scale": scale,
    }


def _click(x, y, button="left"):
    if button == "left":
        _osascript(f'tell application "System Events" to click at {{{x}, {y}}}')
    elif button == "right":
        _cliclick(f"rc:{x},{y}")
    elif button == "double":
        _cliclick(f"dc:{x},{y}")


def _drag(x1, y1, x2, y2):
    _cliclick(f"dd:{x1},{y1}", f"dm:{x2},{y2}", f"du:{x2},{y2}")


def _move(x, y):
    _cliclick(f"m:{x},{y}")


def _type_text(text):
    escaped = text.replace("\\", "\\\\").replace('"', '\\"')
    _osascript(f'tell application "System Events" to keystroke "{escaped}"')


# macOS key codes for special keys
_KEY_CODES = {
    "return": 36, "escape": 53, "tab": 48, "space": 49,
    "delete": 51, "backspace": 51, "forward-delete": 117,
    "arrow-up": 126, "arrow-down": 125, "arrow-left": 123, "arrow-right": 124,
    "home": 115, "end": 119, "pageup": 116, "pagedown": 121,
    "f1": 122, "f2": 120, "f3": 99, "f4": 118, "f5": 96,
    "f6": 97, "f7": 98, "f8": 100, "f9": 101, "f10": 109,
    "f11": 103, "f12": 111,
}

_MOD_MAP = {
    "cmd": "command down",
    "shift": "shift down",
    "opt": "option down",
    "ctrl": "control down",
}


def _key_press(key):
    """
    Press a key, with optional modifier prefix(es).
    Examples: "return", "escape", "cmd-c", "cmd-shift-z", "ctrl-tab"
    """
    parts = key.split("-")
    mods = []
    while parts and parts[0] in _MOD_MAP:
        mods.append(_MOD_MAP[parts.pop(0)])
    char = "-".join(parts)  # remaining part is the key

    mod_clause = ", ".join(mods)
    using = f" using {{{mod_clause}}}" if mods else ""

    if char.lower() in _KEY_CODES:
        _osascript(
            f'tell application "System Events" to key code {_KEY_CODES[char.lower()]}{using}'
        )
    else:
        _osascript(
            f'tell application "System Events" to keystroke "{char}"{using}'
        )


def _scroll(x, y, direction, amount=3):
    _cliclick(f"m:{x},{y}")
    cmd = "su" if direction == "up" else "sd"
    for _ in range(amount):
        _cliclick(f"{cmd}:{x},{y}")


def _get_screen_size():
    out, _ = _osascript('tell application "Finder" to get bounds of window of desktop')
    parts = out.strip().split(", ")
    if len(parts) == 4:
        return {"width": int(parts[2]), "height": int(parts[3])}
    return {"width": 1920, "height": 1080}


def _open_app(name):
    result = _run(["open", "-a", name])
    if result.returncode != 0:
        return result.stderr.strip() or f"Could not open '{name}'"
    return f"Opened {name}"


# Walk the macOS accessibility tree up to 3 levels deep.
_FIND_ELEMENTS_SCRIPT = '''\
set output to {{}}
tell application "System Events"
    tell process "{app_name}"
        set w to front window
        set winPos to position of w
        set winSz to size of w
        set end of output to "window|" & (item 1 of winPos) & "," & (item 2 of winPos) & "|" & (item 1 of winSz) & "x" & (item 2 of winSz) & "|" & (name of w)
        repeat with e1 in (every UI element of w)
            try
                set p to position of e1
                set s to size of e1
                set end of output to "1:" & (class of e1 as string) & "|" & (item 1 of p) & "," & (item 2 of p) & "|" & (item 1 of s) & "x" & (item 2 of s) & "|" & (name of e1) & "|" & my safeVal(e1)
            end try
            try
                repeat with e2 in (every UI element of e1)
                    try
                        set p to position of e2
                        set s to size of e2
                        set end of output to "2:" & (class of e2 as string) & "|" & (item 1 of p) & "," & (item 2 of p) & "|" & (item 1 of s) & "x" & (item 2 of s) & "|" & (name of e2) & "|" & my safeVal(e2)
                    end try
                    try
                        repeat with e3 in (every UI element of e2)
                            try
                                set p to position of e3
                                set s to size of e3
                                set end of output to "3:" & (class of e3 as string) & "|" & (item 1 of p) & "," & (item 2 of p) & "|" & (item 1 of s) & "x" & (item 2 of s) & "|" & (name of e3) & "|" & my safeVal(e3)
                            end try
                        end repeat
                    end try
                end repeat
            end try
        end repeat
    end tell
end tell
return output

on safeVal(elem)
    try
        return value of elem as string
    on error
        return ""
    end try
end safeVal
'''


def _find_elements(app_name, query=None):
    script = _FIND_ELEMENTS_SCRIPT.replace("{app_name}", app_name)
    out, err = _osascript(script)
    if err and not out:
        return [{"error": err}]

    elements = []
    for line in out.split(", "):
        line = line.strip()
        if not line:
            continue
        depth = 0
        if len(line) >= 2 and line[0].isdigit() and line[1] == ":":
            depth = int(line[0])
            line = line[2:]
        parts = line.split("|")
        if len(parts) < 3:
            continue
        elem_class = parts[0]
        try:
            px, py = parts[1].split(",")
            sw, sh = parts[2].split("x")
            x, y, w, h = int(px), int(py), int(sw), int(sh)
        except (ValueError, IndexError):
            continue
        name = parts[3] if len(parts) > 3 else ""
        value = parts[4] if len(parts) > 4 else ""
        cx, cy = x + w // 2, y + h // 2
        elem = {
            "depth": depth,
            "type": elem_class,
            "name": name or None,
            "value": value or None,
            "position": {"x": x, "y": y},
            "size": {"w": w, "h": h},
            "center": {"x": cx, "y": cy},
        }
        if query:
            q = query.lower()
            if not (
                (name and q in name.lower())
                or (value and q in value.lower())
                or q in elem_class.lower()
            ):
                continue
        elements.append(elem)
    return elements


# ---------------------------------------------------------------------------
# MCP tool definitions
# ---------------------------------------------------------------------------

@app.list_tools()
async def list_tools():
    return [
        types.Tool(
            name="screenshot",
            description="Take a screenshot of the entire screen. Returns a base64-encoded PNG.",
            inputSchema={"type": "object", "properties": {}},
        ),
        types.Tool(
            name="find_elements",
            description=(
                "Walk the accessibility tree of a running Mac app (up to 3 levels deep) and return "
                "UI elements with their screen positions, sizes, and center coordinates. "
                "Use center x/y for click targets. Optionally filter by a text query matched against "
                "element name, value, or type. Call this before clicking to get accurate coordinates."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "app_name": {
                        "type": "string",
                        "description": "Name of the running process (e.g. 'Safari', 'Mail', 'iPhone Mirroring').",
                    },
                    "query": {
                        "type": "string",
                        "description": "Optional filter — only return elements whose name, value, or type contains this string (case-insensitive).",
                    },
                },
                "required": ["app_name"],
            },
        ),
        types.Tool(
            name="click",
            description=(
                "Click at a screen coordinate. All coordinates are logical screen points "
                "(same space returned by find_elements and get_screen_size)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "x": {"type": "integer"},
                    "y": {"type": "integer"},
                    "button": {
                        "type": "string",
                        "enum": ["left", "right", "double"],
                        "default": "left",
                    },
                },
                "required": ["x", "y"],
            },
        ),
        types.Tool(
            name="drag",
            description=(
                "Click-and-drag from one screen coordinate to another. "
                "Useful for sliders, reordering items, or swipe gestures in iPhone Mirroring."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "x1": {"type": "integer", "description": "Start x"},
                    "y1": {"type": "integer", "description": "Start y"},
                    "x2": {"type": "integer", "description": "End x"},
                    "y2": {"type": "integer", "description": "End y"},
                },
                "required": ["x1", "y1", "x2", "y2"],
            },
        ),
        types.Tool(
            name="move_mouse",
            description="Move the mouse cursor to a screen coordinate without clicking.",
            inputSchema={
                "type": "object",
                "properties": {
                    "x": {"type": "integer"},
                    "y": {"type": "integer"},
                },
                "required": ["x", "y"],
            },
        ),
        types.Tool(
            name="type_text",
            description="Type a string of text at the current cursor position.",
            inputSchema={
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
            },
        ),
        types.Tool(
            name="key_press",
            description=(
                "Press a key or key combination. "
                "Special keys: return, escape, tab, space, delete, backspace, forward-delete, "
                "arrow-up, arrow-down, arrow-left, arrow-right, home, end, pageup, pagedown, f1–f12. "
                "Modifier prefixes: cmd, shift, opt, ctrl. "
                "Chain multiple modifiers: cmd-shift-z, cmd-opt-esc, ctrl-shift-tab, etc."
            ),
            inputSchema={
                "type": "object",
                "properties": {"key": {"type": "string"}},
                "required": ["key"],
            },
        ),
        types.Tool(
            name="scroll",
            description="Scroll up or down at a screen coordinate.",
            inputSchema={
                "type": "object",
                "properties": {
                    "x": {"type": "integer"},
                    "y": {"type": "integer"},
                    "direction": {"type": "string", "enum": ["up", "down"]},
                    "amount": {"type": "integer", "default": 3, "description": "Number of scroll steps (default 3)."},
                },
                "required": ["x", "y", "direction"],
            },
        ),
        types.Tool(
            name="open_app",
            description="Open a macOS application by name (equivalent to `open -a AppName`).",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "App name as it appears in /Applications (e.g. 'Safari', 'Finder', 'Notes')."}
                },
                "required": ["name"],
            },
        ),
        types.Tool(
            name="get_screen_size",
            description="Return the screen dimensions in logical points.",
            inputSchema={"type": "object", "properties": {}},
        ),
    ]


# ---------------------------------------------------------------------------
# MCP tool dispatch
# ---------------------------------------------------------------------------

@app.call_tool()
async def call_tool(name: str, arguments: dict):
    if name == "screenshot":
        s = _take_screenshot()
        note = (
            f"Screenshot is {s['img_w']}×{s['img_h']} pixels "
            f"(logical screen: {s['logical_w']}×{s['logical_h']} pts, scale: {s['scale']}×). "
            f"To get the logical coordinate to pass to click/drag/scroll, "
            f"divide image pixel coordinates by {s['scale']}. "
            f"Example: image pixel (1000, 500) → click at ({round(1000/s['scale'])}, {round(500/s['scale'])})."
        ) if s["scale"] else ""
        result = [types.ImageContent(type="image", data=s["data"], mimeType="image/png")]
        if note:
            result.append(types.TextContent(type="text", text=note))
        return result

    if name == "find_elements":
        result = _find_elements(arguments["app_name"], arguments.get("query"))
        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]

    if name == "click":
        _click(arguments["x"], arguments["y"], arguments.get("button", "left"))
        return [types.TextContent(type="text", text=f"Clicked ({arguments['x']}, {arguments['y']})")]

    if name == "drag":
        _drag(arguments["x1"], arguments["y1"], arguments["x2"], arguments["y2"])
        return [types.TextContent(type="text", text=f"Dragged ({arguments['x1']},{arguments['y1']}) → ({arguments['x2']},{arguments['y2']})")]

    if name == "move_mouse":
        _move(arguments["x"], arguments["y"])
        return [types.TextContent(type="text", text=f"Moved to ({arguments['x']}, {arguments['y']})")]

    if name == "type_text":
        _type_text(arguments["text"])
        return [types.TextContent(type="text", text=f"Typed: {arguments['text']}")]

    if name == "key_press":
        _key_press(arguments["key"])
        return [types.TextContent(type="text", text=f"Pressed: {arguments['key']}")]

    if name == "scroll":
        _scroll(arguments["x"], arguments["y"], arguments["direction"], arguments.get("amount", 3))
        return [types.TextContent(type="text", text=f"Scrolled {arguments['direction']} at ({arguments['x']}, {arguments['y']})")]

    if name == "open_app":
        msg = _open_app(arguments["name"])
        return [types.TextContent(type="text", text=msg)]

    if name == "get_screen_size":
        return [types.TextContent(type="text", text=json.dumps(_get_screen_size()))]

    raise ValueError(f"Unknown tool: {name}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def main():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
