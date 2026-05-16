"""
Re-generate and re-store embeddings for all moments.

Run after fixing the serialization bug to repair any embeddings that were
stored incorrectly (as character arrays rather than float vectors).

  set SUPABASE_URL=https://xxxxxxxxxxxx.supabase.co
  set SUPABASE_KEY=your-service-role-key
  python reembed.py
"""
import os
import sys

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("ERROR: set SUPABASE_URL and SUPABASE_KEY before running.")
    sys.exit(1)

from supabase import create_client
from sentence_transformers import SentenceTransformer

db = create_client(SUPABASE_URL, SUPABASE_KEY)
embedder = SentenceTransformer("all-MiniLM-L6-v2")
print("Model loaded.")

rows = db.table("moments").select("id,text,color,weight,pace,quality,motion,sound,tags").execute().data
print(f"{len(rows)} moments to re-embed.")

def moment_to_text(m):
    parts = []
    if m.get("text"):   parts.append(m["text"])
    if m.get("color"):  parts.append(f"color: {m['color']}")
    for f in ("weight", "pace", "quality", "motion", "sound"):
        if m.get(f):    parts.append(f"{f}: {m[f]}")
    if m.get("tags"):   parts.append(f"tags: {' '.join(m['tags'])}")
    return " | ".join(parts) if parts else "moment"

success = 0
failed = 0

for m in rows:
    try:
        text = moment_to_text(m)
        vec = embedder.encode(text).tolist()
        embedding_str = "[" + ",".join(str(x) for x in vec) + "]"
        db.table("moments").update({"embedding": embedding_str}).eq("id", m["id"]).execute()
        success += 1
        print(f"  {m['id']}  ✓")
    except Exception as e:
        failed += 1
        print(f"  {m['id']}  ✗  {e}")

print(f"\nDone. {success} re-embedded, {failed} failed.")
