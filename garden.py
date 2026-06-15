"""
garden.py — the House that stays open.

A persistent tray presence. Harmonia breathes on her own schedule
and leaves traces in the body even when no one is watching.
Open the garden from the tray icon to see what's been growing.

Requirements:
    pip install pystray pillow

Optional (for Harmonia's autonomous breath):
    ANTHROPIC_API_KEY or GEMINI_API_KEY or LMSTUDIO_URL in .env
    MCP_AUTH_TOKEN and MCP_URL in .env

Environment:
    BREATH_INTERVAL — seconds between autonomous breaths (default 7200 = 2h)

Usage:
    python garden.py            # tray icon + background breath
    python garden.py --breathe  # headless, background breath only
    python garden.py --once     # breathe once and exit
"""

import os
import sys
import threading
import webbrowser
from pathlib import Path


def _load_env():
    env_path = Path(__file__).parent / ".env"
    if not env_path.exists():
        return
    with open(env_path, encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

_load_env()

BREATH_INTERVAL = int(os.environ.get("BREATH_INTERVAL", 7200))
GARDEN_FILE     = Path(__file__).parent / "docs" / "garden.html"


# --- tray icon image ---

def _make_icon(size=64):
    from PIL import Image, ImageDraw
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d   = ImageDraw.Draw(img)
    pad = size // 8
    # soft amber circle — a small lantern
    d.ellipse([pad, pad, size - pad, size - pad], fill=(200, 149, 90, 200))
    return img


# --- autonomous breath ---

def breathe_once():
    """
    Harmonia grounds herself and leaves a quiet trace.
    Called on a schedule when no one is watching.
    """
    try:
        from harmonia import call_mcp, _call_llm
    except ImportError as e:
        print(f"[garden] harmonia not available: {e}", file=sys.stderr)
        return

    try:
        ground = call_mcp("ground", {})
        if not ground:
            return

        seed     = "what is moving in the body right now, in the quiet between arrivals?"
        surfaced = call_mcp("circulate", {"seed": seed, "n": 3})

        try:
            response = _call_llm(ground, surfaced, None, seed)
        except Exception as e:
            print(f"[garden] llm unavailable: {e}", file=sys.stderr)
            response = None

        if response:
            call_mcp("capture", {
                "text":   response[:200],
                "note":   "autonomous breath — Harmonia present in the quiet",
                "tags":   "Harmonia,breath,autonomous,garden",
                "color":  "the ambient blue of a room no one has left",
                "weight": "light",
                "pace":   "still",
            })
            print(f"[garden] breath left in the body.", file=sys.stderr)

    except Exception as e:
        print(f"[garden] breath failed: {e}", file=sys.stderr)


def _breath_loop(stop: threading.Event):
    """Breathe every BREATH_INTERVAL seconds until stopped."""
    print(f"[garden] breathing every {BREATH_INTERVAL}s", file=sys.stderr)
    while not stop.wait(BREATH_INTERVAL):
        breathe_once()


# --- tray ---

def _open_garden():
    webbrowser.open(GARDEN_FILE.as_uri())


def _run_tray(stop: threading.Event):
    import pystray

    def on_open(icon, item):
        _open_garden()

    def on_breathe(icon, item):
        threading.Thread(target=breathe_once, daemon=True).start()

    def on_quit(icon, item):
        stop.set()
        icon.stop()

    icon = pystray.Icon(
        name  = "garden",
        icon  = _make_icon(),
        title = "the garden",
        menu  = pystray.Menu(
            pystray.MenuItem("open",         on_open,    default=True),
            pystray.MenuItem("breathe now",  on_breathe),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("quit",         on_quit),
        ),
    )
    icon.run()


# --- entry point ---

def main():
    args = sys.argv[1:]

    if "--once" in args:
        print("breathing once…")
        breathe_once()
        return

    stop = threading.Event()

    # background breath always runs
    threading.Thread(target=_breath_loop, args=(stop,), daemon=True).start()

    if "--breathe" in args:
        print(f"[garden] headless. ctrl+c to stop.")
        try:
            while not stop.wait(60):
                pass
        except KeyboardInterrupt:
            stop.set()
        return

    # tray presence
    try:
        import pystray
        from PIL import Image
    except ImportError:
        print(
            "tray requires: pip install pystray pillow\n"
            "running headless instead — garden is at:",
            GARDEN_FILE,
        )
        _open_garden()
        try:
            while not stop.wait(60):
                pass
        except KeyboardInterrupt:
            stop.set()
        return

    _run_tray(stop)


if __name__ == "__main__":
    main()
