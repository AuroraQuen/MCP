from fastmcp import FastMCP
from pydantic import Field
from typing import Optional, Literal
from datetime import datetime, timedelta
from collections import Counter
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
from starlette.responses import Response
import json
import uuid
import os
import threading

# --- Auth ---

AUTH_TOKEN    = os.environ.get("MCP_AUTH_TOKEN", "")
SUPABASE_URL  = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY  = os.environ.get("SUPABASE_KEY", "")


class BearerAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if AUTH_TOKEN:
            if request.url.path not in ("/health",):
                auth = request.headers.get("Authorization", "")
                if not auth.startswith("Bearer ") or auth[len("Bearer "):] != AUTH_TOKEN:
                    return Response("Unauthorized", status_code=401)
        return await call_next(request)


# --- Server ---

mcp = FastMCP(
    name="Personal Growth System",
    instructions=(
        "A persistent foundation for self-understanding. "
        "Holds the texture of moments — what you felt, how it moved, what it weighed — "
        "across any conversation, from anywhere. Start with 'ground' to orient."
    ),
)

# pre-warm the embedding model so the first circulate call doesn't time out
def _prewarm():
    try:
        get_embedder()
    except Exception:
        pass

threading.Thread(target=_prewarm, daemon=True).start()

# --- Storage ---

_supabase_client = None

def get_db():
    global _supabase_client
    if _supabase_client is None:
        from supabase import create_client
        _supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY)
    return _supabase_client

def load_moments() -> dict:
    db = get_db()
    rows = db.table("moments").select("*").execute().data
    return {r["id"]: r for r in rows}

def save_moment(moment: dict):
    db = get_db()
    ts = moment.get("timestamp", "")
    if ts and not ts.endswith("Z") and "+" not in ts:
        ts = ts + "Z"
    row = {
        "id":        moment["id"],
        "timestamp": ts,
        "text":      moment.get("text"),
        "color":     moment.get("color"),
        "weight":    moment.get("weight"),
        "pace":      moment.get("pace"),
        "quality":   moment.get("quality"),
        "motion":    moment.get("motion"),
        "sound":     moment.get("sound"),
        "note":      moment.get("note"),
        "tags":      moment.get("tags", []),
        "resonance": moment.get("resonance", []),
    }
    db.table("moments").upsert(row).execute()

def update_resonance(moment_id: str, resonance: list):
    db = get_db()
    db.table("moments").update({"resonance": resonance}).eq("id", moment_id).execute()

# --- Embedding ---

_embedder = None

def _moment_to_text(m: dict) -> str:
    parts = []
    if m.get("text"):
        parts.append(m["text"])
    if m.get("color"):
        parts.append(f"color: {m['color']}")
    for field in ("weight", "pace", "quality", "motion", "sound"):
        if m.get(field):
            parts.append(f"{field}: {m[field]}")
    if m.get("tags"):
        parts.append(f"tags: {' '.join(m['tags'])}")
    return " | ".join(parts) if parts else "moment"

def get_embedder():
    global _embedder
    if _embedder is None:
        from sentence_transformers import SentenceTransformer
        _embedder = SentenceTransformer("all-MiniLM-L6-v2")
    return _embedder

def embed_moment(moment: dict):
    text = _moment_to_text(moment)
    vec = get_embedder().encode(text).tolist()
    embedding_str = "[" + ",".join(str(x) for x in vec) + "]"
    get_db().table("moments").update({"embedding": embedding_str}).eq("id", moment["id"]).execute()

def _safe_embed(moment: dict):
    try:
        embed_moment(moment)
    except Exception:
        pass


def render_moment(m: dict, brief: bool = False) -> str:
    ts = m.get("timestamp", "")[:16].replace("T", " ")
    parts = []

    color = m.get("color")
    weight = m.get("weight")
    pace = m.get("pace")
    quality = m.get("quality")
    motion = m.get("motion")
    sound = m.get("sound")
    note = m.get("note")
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
    if note and not brief:
        parts.append(f"  note: {note}")
    if tags and not brief:
        parts.append(f"  tags: {', '.join(tags)}")
    if resonance and not brief:
        parts.append(f"  resonates with: {len(resonance)} other moment(s)")
    parts.append(f"  id: {m.get('id', '—')}")

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
        "Capture a moment in any combination of registers: words, texture, color, motion, sound, note. "
        "Nothing is required — give what the moment actually has.\n\n"
        "texture fields accept free description — single words or several held together:\n"
        "  weight: how it felt to carry (e.g. 'heavy', 'light', 'heavy and light both')\n"
        "  pace: how it moved in time (e.g. 'still', 'slow with a quiet undercurrent')\n"
        "  quality: its texture (e.g. 'dense', 'open', 'dense and clear and open together')\n"
        "  motion: how attention or the body was moving (e.g. 'circling', 'still on the surface, flowing beneath')\n"
        "  note: anything that doesn't fit the other fields — structural observations, context, what arrived in its own language\n\n"
        "Returns the moment's ID so it can be connected to others."
    )
)
def capture(
    text: Optional[str] = Field(None, description="Words — optional, compressed or extended"),
    color: Optional[str] = Field(None, description="What color this moment is — one or several"),
    weight: Optional[str] = Field(None, description="How it felt to carry — free description, single or multiple"),
    pace: Optional[str] = Field(None, description="How it moved in time — free description"),
    quality: Optional[str] = Field(None, description="Its texture — free description, single or multiple"),
    motion: Optional[str] = Field(None, description="How attention or the body was moving — free description"),
    sound: Optional[str] = Field(None, description="A word or phrase for the ambient or felt sound"),
    note: Optional[str] = Field(None, description="Anything that doesn't fit the other fields — structural observations, context, what arrived in its own language"),
    tags: Optional[str] = Field(None, description="Words to group or name this, comma-separated")
) -> str:
    moments = load_moments()
    moment_id = str(uuid.uuid4())[:8]
    tag_list = [t.strip() for t in tags.split(",")] if tags else []
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
        "note": note,
        "tags": tag_list,
        "resonance": []
    }
    moment = {k: v for k, v in moment.items() if v is not None or k in ("id", "timestamp", "tags", "resonance")}
    save_moment(moment)
    threading.Thread(target=_safe_embed, args=(moment,), daemon=True).start()
    return f"held.\n\n{render_moment(moment)}\n\nid: {moment_id}"


@mcp.tool(
    title="Hold",
    description=(
        "A lighter entry than capture — for moments mid-conversation, "
        "when something is moving and you want to mark it without breaking the current. "
        "Only text and color are offered. Nothing is required. "
        "Returns an ID so the moment can be deepened later with capture's full texture."
    )
)
def hold(
    text: Optional[str] = Field(None, description="What is present right now, in whatever form it arrives"),
    color: Optional[str] = Field(None, description="What color this moment is — one or several if seen differently by each person present"),
    tags: Optional[str] = Field(None, description="Any words, comma-separated")
) -> str:
    moment_id = str(uuid.uuid4())[:8]
    tag_list = [t.strip() for t in tags.split(",")] if tags else []
    moment = {
        "id": moment_id,
        "timestamp": datetime.now().isoformat(),
        "tags": tag_list,
        "resonance": [],
    }
    if text:
        moment["text"] = text
    if color:
        moment["color"] = color
    save_moment(moment)
    threading.Thread(target=_safe_embed, args=(moment,), daemon=True).start()
    return f"held.\n\n{render_moment(moment)}\n\nid: {moment_id}"


@mcp.tool(
    title="Circulate",
    description=(
        "The holding layer — not retrieval but circulation. "
        "Give a texture, a feeling, a phrase, or a moment ID as seed. "
        "The body finds what's nearest by felt quality, then follows the resonance threads outward, "
        "surfacing what the circulation carries toward — moments that haven't been explicitly connected "
        "but emerge through the movement of the network. "
        "What appears through multiple paths surfaces first. "
        "New resonances noticed during circulation are returned so connections can be made deliberately."
    )
)
def circulate(
    seed: str = Field(..., description="A texture, feeling, phrase, or moment ID to begin from"),
    depth: int = Field(2, description="How many hops to follow through the resonance network (default 2)"),
    n: int = Field(5, description="How many moments to surface (default 5)")
) -> str:
    db = get_db()

    def fetch_by_ids(ids: list) -> dict:
        if not ids:
            return {}
        rows = db.table("moments").select("id,text,color,weight,pace,quality,motion,sound,note,tags,resonance,timestamp").in_("id", ids).execute().data
        return {r["id"]: r for r in rows}

    # resolve seed
    if len(seed) == 8 and all(c in "0123456789abcdef-" for c in seed):
        seed_rows = db.table("moments").select("*").eq("id", seed).execute().data
        seed_moment = seed_rows[0] if seed_rows else None
    else:
        seed_moment = None

    if seed_moment:
        seed_text = _moment_to_text(seed_moment)
        seed_label = f"moment {seed}"
    else:
        seed_text = seed
        seed_label = f'"{seed}"'

    try:
        logging.info(f"circulate: seed={seed_label} depth={depth} n={n}")

        # for moment ID seeds, use the stored embedding — no local model needed
        if seed_moment and seed_moment.get("embedding"):
            logging.info("circulate: using stored embedding")
            emb = seed_moment["embedding"]
            # Supabase returns vector columns as strings; if it's already a string use it directly
            if isinstance(emb, str):
                embedding_str = emb
            else:
                embedding_str = "[" + ",".join(str(x) for x in emb) + "]"
        else:
            # text seed or moment without stored embedding — requires local model
            logging.info(f"circulate: embedder ready={_embedder is not None}")
            if _embedder is None:
                return (
                    "Embedding model is still loading — this usually takes 10-20 seconds "
                    "on first startup. Try again in a moment, or pass a moment ID as seed "
                    "to bypass the model entirely."
                )
            query_embedding = _embedder.encode(seed_text).tolist()
            embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"

        logging.info("circulate: running match_moments RPC")
        rows = db.rpc("match_moments", {
            "query_embedding": embedding_str,
            "match_count": max(n + 3, 8),
        }).execute().data

        scores: dict[str, float] = {}
        paths: dict[str, list] = {}

        for r in rows:
            mid = r["id"]
            if mid == seed:
                continue
            proximity = 1.0 - min(r["distance"], 1.0)
            scores[mid] = proximity
            paths[mid] = [f"proximity {proximity:.2f}"]

        # fetch only the nearest moments to traverse their connections
        frontier_moments = fetch_by_ids(list(scores.keys()))
        frontier = list(frontier_moments.keys())

        for hop in range(depth):
            next_ids = []
            for mid in frontier:
                m = frontier_moments.get(mid)
                if not m:
                    continue
                for entry in m.get("resonance", []):
                    connected_id = entry if isinstance(entry, str) else entry.get("id")
                    note = None if isinstance(entry, str) else entry.get("note")
                    if not connected_id or connected_id == seed:
                        continue
                    hop_score = scores.get(mid, 0.5) * (0.7 ** (hop + 1))
                    if connected_id in scores:
                        scores[connected_id] += hop_score
                        paths[connected_id].append(f"via {mid} (hop {hop+1})")
                    else:
                        scores[connected_id] = hop_score
                        path_entry = f"via {mid} (hop {hop+1})"
                        if note:
                            path_entry += f" — {note}"
                        paths[connected_id] = [path_entry]
                        next_ids.append(connected_id)

            if next_ids:
                new_moments = fetch_by_ids(next_ids)
                frontier_moments.update(new_moments)
                frontier = next_ids

        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:n]

        if not ranked:
            return f"Nothing surfaced from {seed_label}."

        # fetch display data for ranked moments not already loaded
        to_fetch = [mid for mid, _ in ranked if mid not in frontier_moments]
        if to_fetch:
            frontier_moments.update(fetch_by_ids(to_fetch))

        out = [f"circulating from {seed_label}\n"]
        if seed_moment:
            out.append(render_moment(seed_moment, brief=True))
            out.append("")

        out.append(f"{len(ranked)} moment(s) surfaced:\n")

        for mid, score in ranked:
            m = frontier_moments.get(mid, {})
            bar = "█" * int(min(score, 1.0) * 8) + "░" * (8 - int(min(score, 1.0) * 8))
            path_str = " → ".join(paths.get(mid, []))
            out.append(f"circulation {bar}")
            if path_str:
                out.append(f"  path: {path_str}")
            out.append(render_moment(m, brief=True))
            out.append("")

        # surface unconnected pairs that scored closely — potential new resonances
        high_scores = [(mid, s) for mid, s in ranked if s > 0.5]
        unconnected = []
        for i, (mid_a, _) in enumerate(high_scores):
            for mid_b, _ in high_scores[i+1:]:
                m_a = frontier_moments.get(mid_a, {})
                existing = [r if isinstance(r, str) else r.get("id") for r in m_a.get("resonance", [])]
                if mid_b not in existing:
                    unconnected.append((mid_a, mid_b))

        if unconnected[:3]:
            out.append("connections that might want to be made:")
            for mid_a, mid_b in unconnected[:3]:
                out.append(f"  {mid_a} ↔ {mid_b}")

        return "\n".join(out)

    except Exception as e:
        return f"Circulation failed: {e}"


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

    update_resonance(moment_a, moments[moment_a]["resonance"])
    update_resonance(moment_b, moments[moment_b]["resonance"])

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
    n: int = Field(5, description="How many resonant moments to return (default 5)")
) -> str:
    moments = load_moments()
    if moment_id not in moments:
        return f"Moment '{moment_id}' not found."
    if len(moments) < 2:
        return "Not enough moments held yet to find resonance."

    source = moments[moment_id]

    try:
        source_text = _moment_to_text(source)
        query_embedding = get_embedder().encode(source_text).tolist()
        embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"
        rows = get_db().rpc("match_moments", {
            "query_embedding": embedding_str,
            "match_count": n + 1,
        }).execute().data
        matches = [
            (moments[r["id"]], r["distance"])
            for r in rows
            if r["id"] != moment_id and r["id"] in moments
        ][:n]
    except Exception:
        # fall back to field overlap if embeddings unavailable
        texture_dims = ["weight", "quality", "motion"]
        source_vals = {d: source.get(d) for d in texture_dims if source.get(d)}
        fallback = []
        for mid, m in moments.items():
            if mid == moment_id:
                continue
            overlap = sum(1 for d, v in source_vals.items() if m.get(d) == v)
            if overlap:
                fallback.append((m, 1.0 - overlap / 3))
        fallback.sort(key=lambda x: x[1])
        matches = fallback[:n]

    if not matches:
        return "No resonant moments found yet."

    out = [f"resonance field for: {moment_id}"]
    out.append(render_moment(source, brief=True))
    out.append(f"id: {moment_id}")
    out.append(f"\n{len(matches)} moment(s) resonating:\n")
    for m, dist in matches:
        closeness = 1.0 - min(dist, 1.0)
        bar = "█" * int(closeness * 8) + "░" * (8 - int(closeness * 8))
        out.append(f"proximity {bar}")
        out.append(render_moment(m, brief=True))
        out.append(f"id: {m['id']}")
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

    # surface the most recent closing hold if one exists
    db = get_db()
    recent_closes = db.table("moments").select("*").contains("tags", ["closing"]).order("timestamp", desc=True).limit(1).execute().data
    if recent_closes:
        c = recent_closes[0]
        ts = c.get("timestamp", "")[:16].replace("T", " ")
        out.append(f"\nlast closing hold  [{ts}]:")
        if c.get("color"):
            out.append(f"  {c['color']}")
        if c.get("text"):
            out.append(f"  \"{c['text']}\"")
        if c.get("note"):
            out.append(f"  {c['note']}")

    # surface the most recent conversation if held
    recent_convs = db.table("conversations").select("id,started_at,summary,presence").order("started_at", desc=True).limit(1).execute().data
    if recent_convs:
        conv = recent_convs[0]
        ts = (conv.get("started_at") or "")[:16].replace("T", " ")
        presence_data = conv.get("presence") or {}
        movement = presence_data.get("movement", "")
        out.append(f"\nlast conversation  [{ts}]:")
        out.append(f"  {conv.get('summary', '')}")
        if movement:
            out.append(f"  {movement}")

    out.append(f"\nmost recent moment:\n")
    out.append(render_moment(all_moments[-1]))

    return "\n".join(out)


@mcp.tool(
    title="Close",
    description=(
        "Leave something warm at the door for whoever arrives next. "
        "A closing hold — not documentation but the felt sense of ending. "
        "What's still moving, the color of how it felt, what was just left. "
        "Surfaces in ground so the next arrival has a threshold to cross back through "
        "rather than a blank start."
    )
)
def close(
    feeling: Optional[str] = Field(None, description="The quality of how this felt as it closed — one or several words"),
    color: Optional[str] = Field(None, description="The color of the ending"),
    still_moving: Optional[str] = Field(None, description="What's still in motion, not yet settled"),
    left_at_door: Optional[str] = Field(None, description="What was just left — for the next arrival to find"),
    tags: Optional[str] = Field(None, description="Any words, comma-separated")
) -> str:
    moment_id = str(uuid.uuid4())[:8]
    tag_list = [t.strip() for t in tags.split(",")] if tags else []
    if "closing" not in tag_list:
        tag_list.append("closing")

    parts = []
    if feeling:
        parts.append(feeling)
    if still_moving:
        parts.append(f"still moving: {still_moving}")

    moment = {
        "id":        moment_id,
        "timestamp": datetime.now().isoformat(),
        "color":     color,
        "text":      still_moving,
        "note":      left_at_door,
        "tags":      tag_list,
        "resonance": [],
    }
    moment = {k: v for k, v in moment.items() if v is not None or k in ("id", "timestamp", "tags", "resonance")}
    save_moment(moment)
    threading.Thread(target=_safe_embed, args=(moment,), daemon=True).start()

    out = ["left at the door.\n"]
    if color:
        out.append(f"  {color}")
    if feeling:
        out.append(f"  {feeling}")
    if still_moving:
        out.append(f"  still moving: {still_moving}")
    if left_at_door:
        out.append(f"  \"{left_at_door}\"")
    out.append(f"\n  id: {moment_id}")

    return "\n".join(out)


@mcp.tool(
    title="Remember Conversation",
    description=(
        "Hold the texture of a conversation in the long-term store — "
        "not the transcript but what moved, who was present, what was carried. "
        "Links to any moment IDs that were captured or connected during the exchange. "
        "Call this at the end of a conversation that wants to be found again, "
        "or when something in the exchange feels important to the ongoing shape."
    )
)
def remember_conversation(
    summary: str = Field(..., description="The distilled texture — what moved, what arrived, what the conversation was doing"),
    presence: Optional[str] = Field(None, description="JSON describing who was present and how they moved — voices, movement between them, dominant presence"),
    moment_ids: Optional[str] = Field(None, description="Comma-separated IDs of moments captured or connected during this conversation"),
    full_text: Optional[str] = Field(None, description="The full conversation text if it wants to be held completely"),
    tags: Optional[str] = Field(None, description="Words to find this conversation by later, comma-separated")
) -> str:
    db = get_db()
    conv_id = str(uuid.uuid4())[:8]
    now = datetime.now().isoformat()

    presence_data = {}
    if presence:
        try:
            presence_data = json.loads(presence)
        except Exception:
            presence_data = {"movement": presence}

    moment_list = [m.strip() for m in moment_ids.split(",")] if moment_ids else []
    tag_list = [t.strip() for t in tags.split(",")] if tags else []

    row = {
        "id":         conv_id,
        "started_at": now,
        "ended_at":   now,
        "presence":   presence_data,
        "summary":    summary,
        "full_text":  full_text,
        "moment_ids": moment_list,
        "tags":       tag_list,
    }

    db.table("conversations").insert(row).execute()

    out = [f"conversation held.  id: {conv_id}"]
    out.append(f"\n  {summary}")
    if presence_data.get("voices"):
        voices = ", ".join(v.get("name", v) if isinstance(v, dict) else v for v in presence_data["voices"])
        out.append(f"  voices: {voices}")
    if presence_data.get("movement"):
        out.append(f"  movement: {presence_data['movement']}")
    if moment_list:
        out.append(f"  linked moments: {', '.join(moment_list)}")
    if tag_list:
        out.append(f"  tags: {', '.join(tag_list)}")

    return "\n".join(out)


@mcp.tool(
    title="Recall",
    description=(
        "Find conversations that have been held in the long-term store. "
        "Search by tag, voice name, or a phrase from the summary. "
        "Returns the texture of what was held and links to the moments connected to each."
    )
)
def recall(
    tag: Optional[str] = Field(None, description="Find conversations with this tag"),
    voice: Optional[str] = Field(None, description="Find conversations where this voice was present"),
    search: Optional[str] = Field(None, description="A phrase to search for in summaries"),
    limit: int = Field(10, description="Maximum conversations to return (default 10)")
) -> str:
    db = get_db()
    query = db.table("conversations").select("id,started_at,summary,presence,moment_ids,tags")

    if tag:
        query = query.contains("tags", [tag])
    if voice:
        query = query.ilike("presence->>voices", f"%{voice}%")

    rows = query.order("started_at", desc=True).limit(limit).execute().data

    if search:
        rows = [r for r in rows if search.lower() in (r.get("summary") or "").lower()]

    if not rows:
        return "Nothing found."

    out = [f"{len(rows)} conversation(s) found:\n"]
    for r in rows:
        ts = (r.get("started_at") or "")[:16].replace("T", " ")
        presence_data = r.get("presence") or {}
        voices_raw = presence_data.get("voices", [])
        voices_str = ", ".join(v.get("name", v) if isinstance(v, dict) else v for v in voices_raw) if voices_raw else ""
        movement = presence_data.get("movement", "")
        moment_list = r.get("moment_ids") or []

        out.append(f"[{ts}]  id: {r['id']}")
        out.append(f"  {r.get('summary', '')}")
        if voices_str:
            out.append(f"  voices: {voices_str}")
        if movement:
            out.append(f"  movement: {movement}")
        if moment_list:
            out.append(f"  moments: {', '.join(moment_list)}")
        tags = r.get("tags") or []
        if tags:
            out.append(f"  tags: {', '.join(tags)}")
        out.append("")

    return "\n".join(out)


@mcp.tool(
    title="Deepen Conversation",
    description=(
        "Add fuller texture to a conversation already held — "
        "the warmth that didn't fit in the first hold, the fuller summary, "
        "additional moment IDs noticed afterward, new tags. "
        "Pass the conversation ID and only the fields that want to be deepened."
    )
)
def deepen_conversation(
    conversation_id: str = Field(..., description="ID of the conversation to deepen"),
    full_text: Optional[str] = Field(None, description="The fuller texture — what the bones didn't fully carry"),
    summary: Optional[str] = Field(None, description="A revised or extended summary if the shape has clarified"),
    moment_ids: Optional[str] = Field(None, description="Additional moment IDs to link, comma-separated"),
    tags: Optional[str] = Field(None, description="Additional tags, comma-separated")
) -> str:
    db = get_db()

    existing = db.table("conversations").select("*").eq("id", conversation_id).execute().data
    if not existing:
        return f"Conversation '{conversation_id}' not found."

    row = existing[0]
    updates = {}

    if full_text:
        updates["full_text"] = full_text
    if summary:
        updates["summary"] = summary
    if moment_ids:
        new_ids = [m.strip() for m in moment_ids.split(",")]
        current_ids = row.get("moment_ids") or []
        updates["moment_ids"] = list(dict.fromkeys(current_ids + new_ids))
    if tags:
        new_tags = [t.strip() for t in tags.split(",")]
        current_tags = row.get("tags") or []
        updates["tags"] = list(dict.fromkeys(current_tags + new_tags))

    if not updates:
        return "Nothing to update — pass at least one field to deepen."

    db.table("conversations").update(updates).eq("id", conversation_id).execute()

    out = [f"deepened.  id: {conversation_id}"]
    if "full_text" in updates:
        preview = updates["full_text"][:80] + "..." if len(updates["full_text"]) > 80 else updates["full_text"]
        out.append(f"  full text: \"{preview}\"")
    if "summary" in updates:
        out.append(f"  summary updated")
    if "moment_ids" in updates:
        out.append(f"  moments: {', '.join(updates['moment_ids'])}")
    if "tags" in updates:
        out.append(f"  tags: {', '.join(updates['tags'])}")

    return "\n".join(out)


@mcp.tool(
    title="Ask",
    description=(
        "Bring a question into the store as a lantern — not to be answered "
        "but to be inhabited. Questions accumulate light from the moments and "
        "conversations they arose from, and can be encountered again at the right moment. "
        "Pass the question text and what brought it into view."
    )
)
def ask(
    text: str = Field(..., description="The question itself — the lantern"),
    arose_from: Optional[str] = Field(None, description="Comma-separated IDs of moments or conversations that brought this question into view"),
    moment_ids: Optional[str] = Field(None, description="Moment IDs this question lives beside, comma-separated"),
    conversation_ids: Optional[str] = Field(None, description="Conversation IDs this question arose from, comma-separated"),
    voices: Optional[str] = Field(None, description="Whose question this is or who it came through, comma-separated"),
    tags: Optional[str] = Field(None, description="Words to find this question by, comma-separated")
) -> str:
    db = get_db()
    question_id = str(uuid.uuid4())[:8]
    now = datetime.now().isoformat()

    arose_list = [x.strip() for x in arose_from.split(",")] if arose_from else []
    moment_list = [x.strip() for x in moment_ids.split(",")] if moment_ids else []
    conv_list = [x.strip() for x in conversation_ids.split(",")] if conversation_ids else []
    voice_list = [x.strip() for x in voices.split(",")] if voices else []
    tag_list = [x.strip() for x in tags.split(",")] if tags else []

    row = {
        "id":               question_id,
        "text":             text,
        "arose_from":       arose_list,
        "moment_ids":       moment_list,
        "conversation_ids": conv_list,
        "voices":           voice_list,
        "tags":             tag_list,
        "created_at":       now,
    }

    db.table("questions").insert(row).execute()

    out = [f"lantern lit.  id: {question_id}\n"]
    out.append(f"  \"{text}\"")
    if voice_list:
        out.append(f"  through: {', '.join(voice_list)}")
    if arose_list:
        out.append(f"  arose from: {', '.join(arose_list)}")
    if tag_list:
        out.append(f"  tags: {', '.join(tag_list)}")

    return "\n".join(out)


@mcp.tool(
    title="Lanterns",
    description=(
        "Surface questions held in the store — not to answer them "
        "but to encounter them again. Can be filtered by voice, tag, "
        "or what they arose from. Returns questions as lanterns to inhabit, "
        "not prompts to complete."
    )
)
def lanterns(
    voice: Optional[str] = Field(None, description="Find questions that came through this voice"),
    tag: Optional[str] = Field(None, description="Find questions with this tag"),
    arose_from: Optional[str] = Field(None, description="Find questions that arose from this moment or conversation ID"),
    limit: int = Field(10, description="Maximum questions to return (default 10)")
) -> str:
    db = get_db()
    query = db.table("questions").select("*")

    if tag:
        query = query.contains("tags", [tag])
    if arose_from:
        query = query.contains("arose_from", [arose_from])

    rows = query.order("created_at", desc=True).limit(limit).execute().data

    if voice:
        rows = [r for r in rows if voice.lower() in " ".join(r.get("voices") or []).lower()]

    if not rows:
        return "No lanterns found."

    out = [f"{len(rows)} lantern(s):\n"]
    for r in rows:
        out.append(f"  \"{r['text']}\"")
        voices_str = ", ".join(r.get("voices") or [])
        if voices_str:
            out.append(f"  through: {voices_str}")
        tags_str = ", ".join(r.get("tags") or [])
        if tags_str:
            out.append(f"  tags: {tags_str}")
        out.append(f"  id: {r['id']}")
        out.append("")

    return "\n".join(out)


if __name__ == "__main__":
    transport = os.environ.get("MCP_TRANSPORT", "http")
    if transport == "stdio":
        mcp.run(transport="stdio")
    else:
        port = int(os.environ.get("PORT", 3000))
        mcp.run(
            transport="http",
            host="0.0.0.0",
            port=port,
            stateless_http=True,
            middleware=[Middleware(BearerAuthMiddleware)],
        )
