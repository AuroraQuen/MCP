import json
import os
from datetime import datetime

# --- Config ---
# Set these before running:
#   set SUPABASE_URL=https://xxxxxxxxxxxx.supabase.co
#   set SUPABASE_KEY=your-service-role-key
#   set DATA_DIR=C:\Users\Jerold\personal-growth-data

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
DATA_DIR     = os.environ.get("DATA_DIR", os.path.dirname(os.path.abspath(__file__)))
STORE_PATH   = os.path.join(DATA_DIR, "moments.json")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("ERROR: set SUPABASE_URL and SUPABASE_KEY environment variables before running.")
    exit(1)

if not os.path.exists(STORE_PATH):
    print(f"ERROR: moments.json not found at {STORE_PATH}")
    exit(1)

from supabase import create_client
client = create_client(SUPABASE_URL, SUPABASE_KEY)

with open(STORE_PATH, "r") as f:
    moments = json.load(f)

print(f"Migrating {len(moments)} moments...")

# try to load embedder for existing moments
embedder = None
try:
    from sentence_transformers import SentenceTransformer
    embedder = SentenceTransformer("all-MiniLM-L6-v2")
    print("Embedding model loaded — will generate embeddings during migration.")
except Exception:
    print("Embedding model not available — migrating without embeddings.")

def moment_to_text(m):
    parts = []
    if m.get("text"):   parts.append(m["text"])
    if m.get("color"):  parts.append(f"color: {m['color']}")
    for f in ("weight", "pace", "quality", "motion", "sound"):
        if m.get(f):    parts.append(f"{f}: {m[f]}")
    if m.get("tags"):   parts.append(f"tags: {' '.join(m['tags'])}")
    return " | ".join(parts) if parts else "moment"

success = 0
failed  = 0

for mid, m in moments.items():
    try:
        ts = m.get("timestamp")
        if ts and not ts.endswith("Z") and "+" not in ts:
            ts = ts + "Z"

        row = {
            "id":        m["id"],
            "timestamp": ts,
            "text":      m.get("text"),
            "color":     m.get("color"),
            "weight":    m.get("weight"),
            "pace":      m.get("pace"),
            "quality":   m.get("quality"),
            "motion":    m.get("motion"),
            "sound":     m.get("sound"),
            "tags":      m.get("tags", []),
            "resonance": m.get("resonance", []),
        }

        if embedder:
            text = moment_to_text(m)
            row["embedding"] = embedder.encode(text).tolist()

        client.table("moments").upsert(row).execute()
        success += 1
        print(f"  {m['id']}  ✓")

    except Exception as e:
        failed += 1
        print(f"  {m.get('id', '?')}  ✗  {e}")

print(f"\nDone. {success} migrated, {failed} failed.")
