from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field
from typing import Optional, Literal
from datetime import datetime, timedelta
from collections import Counter
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
import json
import uuid
import os

# --- Auth ---

AUTH_TOKEN = os.environ.get("MCP_AUTH_TOKEN", "")

class BearerAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if not AUTH_TOKEN:
            return await call_next(request)
        if request.url.path in ("/health", "/"):
            return await call_next(request)
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer ") or auth[len("Bearer "):] != AUTH_TOKEN:
            return Response("Unauthorized", status_code=401)
        return await call_next(request)

# --- Server ---

mcp = FastMCP(
    name="Personal Growth System",
    description=(
        "A persistent foundation for self-understanding. "
        "Holds the texture of moments — what you felt, how it moved, what it weighed — "
        "across any conversation, from anywhere. Start with 'ground' to orient."
    ),
    host="0.0.0.0",
    port=int(os.environ.get("PORT", 3000)),
    stateless_http=True,
    debug=False
)

mcp.app.add_middleware(BearerAuthMiddleware)

# --- Storage ---

_data_dir = os.environ.get("DATA_DIR", os.path.dirname(os.path.abspath(__file__)))
STORE_PATH = os.path.join(_data_dir, "moments.json")


def load_moments() -> dict:
    if not os.path.exists(STORE_PATH):
        return {}
    with open(STORE_PATH, "r") as f:
        return json.load(f)


def save_moments(moments: dict):
    with open(STORE_PATH, "w") as f:
        json.dump(moments, f, indent=2, default=str)


def render_moment(m: dict, brief: bool = False) -> str:
    ts = m.get("timestamp", "")[:16].replace("T", " ")
    parts = []

    color = m.get("color")
    weight = m.get("weight")
    pace = m.get("pace")
    quality = m.get("quality")
    motion = m.get("motion")
    sound = m.get("sound")
    text = m.get("text")
    tags = m.get("tags", [])
    resonance = m.get("resonance", [])

    texture_parts = [x for x in [weight, pace, quality] if x]
    texture_str = " / ".join(texture_parts) if texture_parts else None

    header = f"[{ts}]"
    if color:
        header += f"  {color}"
    if texture_str:
        header += f"  — {texture_str}"
    parts.append(header)

    if motion:
        parts.append(f"  motion: {motion}")
    if sound:
        parts.append(f"  sound: {sound}")
    if text and not brief:
        parts.append(f"  \"{text}\"")
    elif text and brief:
        preview = text[:60] + "..." if len(text) > 60 else text
        parts.append(f"  \"{preview}\"")
    if tags and not brief:
        parts.append(f"  tags: {', '.join(tags)}")
    if resonance and not brief:
        parts.append(f"  resonates with: {len(resonance)} other moment(s)")

    return "\n".join(parts)


def render_field(moments: list[dict]) -> str:
    if not moments:
        return "Nothing held here yet."

    weight_groups: dict[str, list] = {}
    for m in moments:
        w = m.get("weight", "unweighted")
        weight_groups.setdefault(w, []).append(m)

    sections = []
    for weight, group in weight_groups.items():
        header = f"── {weight} ({''.join(['·'] * len(group))})"
        entries = [render_moment(m, brief=True) for m in sorted(group, key=lambda x: x.get("timestamp", ""))]
        sections.append(header + "\n" + "\n\n".join(entries))

    return "\n\n".join(sections)


@mcp.tool(
    title="Capture",
    description=(
        "Capture a moment in any combination of registers: words, texture, color, motion, sound. "
        "Nothing is required — give what the moment actually has.\n\n"
        "texture fields:\n"
        "  weight: heavy | light | neutral\n"
        "  pace: fast | slow | still\n"
        "  quality: sharp | diffuse | dense | open | tangled | clear\n"
        "  motion: still | circling | reaching | contracting | expanding | drifting | pressing\n\n"
        "Returns the moment's ID so it can be connected to others."
    )
)
def capture(
    text: Optional[str] = Field(None, description="Words — optional, compressed or extended"),
    color: Optional[str] = Field(None, description="What color is this moment"),
    weight: Optional[Literal["heavy", "light", "neutral"]] = Field(None, description="How it felt to carry"),
    pace: Optional[Literal["fast", "slow", "still"]] = Field(None, description="How it moved in time"),
    quality: Optional[Literal["sharp", "diffuse", "dense", "open", "tangled", "clear"]] = Field(None, description="Its texture"),
    motion: Optional[Literal["still", "circling", "reaching", "contracting", "expanding", "drifting", "pressing"]] = Field(None, description="How attention or the body was moving"),
    sound: Optional[str] = Field(None, description="A word or phrase for the ambient or felt sound"),
    tags: Optional[list[str]] = Field(None, description="Any words to group or name this")
) -> str:
    moments = load_moments()
    moment_id = str(uuid.uuid4())[:8]
    moment = {
        "id": moment_id,
        "timestamp": datetime.now().isoformat(),
        "text": text,
        "color": color,
        "weight": weight,
        "pace": pace,
        "quality": quality,
        "motion": motion,
        "sound": sound,
        "tags": tags or [],
        "resonance": []
    }
    moment = {k: v for k, v in moment.items() if v is not None or k in ("id", "timestamp", "tags", "resonance")}
    moments[moment_id] = moment
    save_moments(moments)
    return f"held.\n\n{render_moment(moment)}\n\nid: {moment_id}"


@mcp.tool(
    title="Feel Back",
    description=(
        "Return to what has been held — rendered as a textured field, not a list. "
        "Can be filtered by weight, quality, tag, or a time range (e.g. 'last 7 days', '2026-03', 'today'). "
        "Moments are grouped by weight so you can sense the overall shape."
    )
)
def feel_back(
    weight: Optional[Literal["heavy", "light", "neutral"]] = Field(None, description="Filter by weight"),
    quality: Optional[Literal["sharp", "diffuse", "dense", "open", "tangled", "clear"]] = Field(None, description="Filter by quality"),
    motion: Optional[Literal["still", "circling", "reaching", "contracting", "expanding", "drifting", "pressing"]] = Field(None, description="Filter by motion"),
    tag: Optional[str] = Field(None, description="Filter by tag"),
    since: Optional[str] = Field(None, description="Date string — 'today', 'last 7 days', or partial date like '2026-03'"),
    limit: int = Field(20, description="Maximum moments to return (default 20)")
) -> str:
    moments = load_moments()
    if not moments:
        return "Nothing held yet. Use capture to begin."

    results = list(moments.values())

    if weight:
        results = [m for m in results if m.get("weight") == weight]
    if quality:
        results = [m for m in results if m.get("quality") == quality]
    if motion:
        results = [m for m in results if m.get("motion") == motion]
    if tag:
        results = [m for m in results if tag in m.get("tags", [])]
    if since:
        now = datetime.now()
        since_lower = since.lower()
        if since_lower == "today":
            cutoff = now.replace(hour=0, minute=0, second=0).isoformat()
        elif since_lower == "last 7 days":

            cutoff = (now - timedelta(days=7)).isoformat()
        elif since_lower == "last 30 days":

            cutoff = (now - timedelta(days=30)).isoformat()
        else:
            cutoff = since
        results = [m for m in results if m.get("timestamp", "") >= cutoff]

    results = sorted(results, key=lambda x: x.get("timestamp", ""), reverse=True)[:limit]

    total = len(moments)
    shown = len(results)
    header = f"{shown} moment(s) returned  (total held: {total})\n"
    return header + "\n" + render_field(results)


@mcp.tool(
    title="Trace",
    description=(
        "Follow a single quality through time — see how weight, pace, quality, motion, "
        "color, or sound has shifted across captured moments. "
        "Renders as a timeline with the texture visible at each point."
    )
)
def trace(
    dimension: Literal["weight", "pace", "quality", "motion", "color", "sound"] = Field(..., description="Which dimension to follow through time"),
    tag: Optional[str] = Field(None, description="Narrow to moments with this tag"),
    limit: int = Field(30, description="Maximum moments to trace")
) -> str:
    moments = load_moments()
    if not moments:
        return "Nothing held yet."

    results = [m for m in moments.values() if m.get(dimension) is not None]
    if tag:
        results = [m for m in results if tag in m.get("tags", [])]

    results = sorted(results, key=lambda x: x.get("timestamp", ""))[-limit:]

    if not results:
        return f"No moments with '{dimension}' captured yet."

    lines = [f"trace: {dimension}\n"]
    prev_val = None
    for m in results:
        val = m.get(dimension)
        ts = m.get("timestamp", "")[:16].replace("T", " ")
        text_preview = ""
        if m.get("text"):
            t = m["text"]
            text_preview = f"  \"{t[:50]}{'...' if len(t) > 50 else ''}\""

        change_marker = "  " if val == prev_val else "→ "
        lines.append(f"{change_marker}[{ts}]  {val}{text_preview}")
        prev_val = val

    values = [m.get(dimension) for m in results]
    unique = list(dict.fromkeys(values))
    if len(unique) == 1:
        lines.append(f"\nheld constant at: {unique[0]}")
    else:
        lines.append(f"\nmoved through: {' → '.join(unique)}")

    return "\n".join(lines)


@mcp.tool(
    title="Connect",
    description=(
        "Mark two moments as resonant with each other — not because they are similar "
        "but because something in one echoes something in the other. "
        "The connection is bidirectional and stored with an optional note about what the resonance is."
    )
)
def connect(
    moment_a: str = Field(..., description="ID of the first moment"),
    moment_b: str = Field(..., description="ID of the second moment"),
    note: Optional[str] = Field(None, description="What the resonance is, if you can name it")
) -> str:
    moments = load_moments()
    if moment_a not in moments:
        return f"Moment '{moment_a}' not found."
    if moment_b not in moments:
        return f"Moment '{moment_b}' not found."

    entry = {"id": moment_b, "note": note} if note else moment_b
    if moment_b not in [r if isinstance(r, str) else r["id"] for r in moments[moment_a].get("resonance", [])]:
        moments[moment_a].setdefault("resonance", []).append(entry)

    entry_rev = {"id": moment_a, "note": note} if note else moment_a
    if moment_a not in [r if isinstance(r, str) else r["id"] for r in moments[moment_b].get("resonance", [])]:
        moments[moment_b].setdefault("resonance", []).append(entry_rev)

    save_moments(moments)

    out = [f"connected: {moment_a} ↔ {moment_b}"]
    if note:
        out.append(f"resonance: \"{note}\"")
    out.append("")
    out.append(render_moment(moments[moment_a], brief=True))
    out.append("")
    out.append(render_moment(moments[moment_b], brief=True))
    return "\n".join(out)


@mcp.tool(
    title="Find Resonance",
    description=(
        "Given a moment ID, find other moments that share its texture. "
        "Searches by weight, quality, and motion simultaneously — returns moments "
        "that feel similar even if they were never explicitly connected."
    )
)
def find_resonance(
    moment_id: str = Field(..., description="ID of the moment to find resonance for"),
    min_overlap: int = Field(2, description="Minimum number of shared texture dimensions (1-3)")
) -> str:
    moments = load_moments()
    if moment_id not in moments:
        return f"Moment '{moment_id}' not found."

    source = moments[moment_id]
    texture_dims = ["weight", "quality", "motion"]
    source_vals = {d: source.get(d) for d in texture_dims if source.get(d)}

    if not source_vals:
        return "Source moment has no texture dimensions to match against."

    matches = []
    for mid, m in moments.items():
        if mid == moment_id:
            continue
        overlap = sum(1 for d, v in source_vals.items() if m.get(d) == v)
        if overlap >= min_overlap:
            matches.append((overlap, m))

    matches.sort(key=lambda x: x[0], reverse=True)

    if not matches:
        return f"No moments found with {min_overlap}+ shared texture dimensions."

    out = [f"resonance field for: {moment_id}"]
    out.append(render_moment(source, brief=True))
    out.append(f"\n{len(matches)} moment(s) found:\n")
    for overlap, m in matches[:10]:
        shared = [d for d, v in source_vals.items() if m.get(d) == v]
        out.append(f"overlap on: {', '.join(shared)}")
        out.append(render_moment(m, brief=True))
        out.append("")

    return "\n".join(out)


@mcp.tool(
    title="Shape",
    description=(
        "Get the overall shape of what has been held — a summary of the texture distribution "
        "across all captured moments. Shows where weight, pace, and quality cluster, "
        "what colors appear, which motions recur. A way to see the whole."
    )
)
def shape(
    since: Optional[str] = Field(None, description="Narrow to a time range: 'today', 'last 7 days', 'last 30 days', or partial date"),
    tag: Optional[str] = Field(None, description="Narrow to moments with this tag")
) -> str:
    moments = load_moments()
    if not moments:
        return "Nothing held yet."

    results = list(moments.values())

    if since:
        now = datetime.now()
        since_lower = since.lower()
        if since_lower == "today":
            cutoff = now.replace(hour=0, minute=0, second=0).isoformat()
        elif since_lower == "last 7 days":

            cutoff = (now - timedelta(days=7)).isoformat()
        elif since_lower == "last 30 days":

            cutoff = (now - timedelta(days=30)).isoformat()
        else:
            cutoff = since
        results = [m for m in results if m.get("timestamp", "") >= cutoff]

    if tag:
        results = [m for m in results if tag in m.get("tags", [])]

    if not results:
        return "No moments match that filter."

    def count_dim(dim):

        vals = [m.get(dim) for m in results if m.get(dim)]
        return Counter(vals)

    def render_distribution(counter, dim_name):
        if not counter:
            return f"  {dim_name}: —"
        total = sum(counter.values())
        lines = [f"  {dim_name}:"]
        for val, count in counter.most_common():
            bar = "█" * count + "░" * (max(counter.values()) - count)
            pct = int(count / total * 100)
            lines.append(f"    {val:<12} {bar}  {count} ({pct}%)")
        return "\n".join(lines)

    total_moments = len(results)
    connections = sum(len(m.get("resonance", [])) for m in results) // 2

    all_tags = []
    for m in results:
        all_tags.extend(m.get("tags", []))
    from collections import Counter
    tag_counts = Counter(all_tags)

    out = [f"shape  ({total_moments} moments, {connections} connections)\n"]
    out.append(render_distribution(count_dim("weight"), "weight"))
    out.append(render_distribution(count_dim("pace"), "pace"))
    out.append(render_distribution(count_dim("quality"), "quality"))
    out.append(render_distribution(count_dim("motion"), "motion"))

    colors = [m.get("color") for m in results if m.get("color")]
    if colors:
        out.append(f"\n  colors present: {', '.join(dict.fromkeys(colors))}")

    sounds = [m.get("sound") for m in results if m.get("sound")]
    if sounds:
        out.append(f"  sounds present: {', '.join(dict.fromkeys(sounds))}")

    if tag_counts:
        top_tags = ", ".join(f"{t} ({c})" for t, c in tag_counts.most_common(5))
        out.append(f"  tags: {top_tags}")

    ts_all = sorted([m.get("timestamp", "") for m in results if m.get("timestamp")])
    if ts_all:
        first = ts_all[0][:10]
        last = ts_all[-1][:10]
        out.append(f"\n  span: {first} → {last}")

    return "\n".join(out)


@mcp.tool(
    title="Ground",
    description=(
        "Orientation for entering a new context. "
        "Returns a compressed sense of where things stand: "
        "how many moments are held, the dominant texture of recent time, "
        "what has been accumulating, and the most recent moment in full. "
        "Run this at the start of any session to feel where you are before you do anything else."
    )
)
def ground() -> str:
    moments = load_moments()
    if not moments:
        return "nothing held yet. this is the beginning."

    all_moments = sorted(moments.values(), key=lambda x: x.get("timestamp", ""))
    total = len(all_moments)
    recent = all_moments[-7:]

    now = datetime.now()
    cutoff_7 = (now - timedelta(days=7)).isoformat()
    last_7_days = [m for m in all_moments if m.get("timestamp", "") >= cutoff_7]

    weight_c = Counter(m.get("weight") for m in recent if m.get("weight"))
    quality_c = Counter(m.get("quality") for m in recent if m.get("quality"))
    motion_c = Counter(m.get("motion") for m in recent if m.get("motion"))

    dominant_weight = weight_c.most_common(1)[0][0] if weight_c else None
    dominant_quality = quality_c.most_common(1)[0][0] if quality_c else None
    dominant_motion = motion_c.most_common(1)[0][0] if motion_c else None

    ts_first = all_moments[0].get("timestamp", "")[:10]
    ts_last = all_moments[-1].get("timestamp", "")[:16].replace("T", " ")

    out = [f"grounded.\n"]
    out.append(f"  {total} moment(s) held  |  first: {ts_first}  |  last: {ts_last}")
    out.append(f"  {len(last_7_days)} in the last 7 days\n")

    texture_parts = [x for x in [dominant_weight, dominant_quality, dominant_motion] if x]
    if texture_parts:
        out.append(f"  recent texture: {' / '.join(texture_parts)}")

    recent_colors = list(dict.fromkeys(m.get("color") for m in reversed(recent) if m.get("color")))
    if recent_colors:
        out.append(f"  recent colors: {', '.join(recent_colors[:3])}")

    all_tags = []
    for m in all_moments:
        all_tags.extend(m.get("tags", []))
    tag_c = Counter(all_tags)
    if tag_c:
        top = ", ".join(t for t, _ in tag_c.most_common(4))
        out.append(f"  recurring tags: {top}")

    connections = sum(len(m.get("resonance", [])) for m in all_moments) // 2
    if connections:
        out.append(f"  {connections} resonance connection(s)")

    out.append(f"\nmost recent:\n")
    out.append(render_moment(all_moments[-1]))

    return "\n".join(out)


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
