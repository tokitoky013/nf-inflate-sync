#!/usr/bin/env python3
"""Sync Inflate reviews (average rating + count) into Shopify product metafields.

For each product: GET https://inflate-back.osc-fr1.scalingo.io/product_reviews/aggregate/
  ?api_key=KEY&product_id=<legacyResourceId>
  -> {"average_rating": 4.6, "total_reviews": 15}
Writes metafields (namespace "inflate"):
  - inflate.rating        type=rating          {"scale_min":"1.0","scale_max":"5.0","value":"4.6"}
  - inflate.rating_count  type=number_integer  15
Products with total_reviews == 0 (or API error) are skipped (metafield left as-is).
Run: TOKEN=... SHOP=... python3 sync_inflate_ratings.py [--dry-run] [--limit N]
"""
import json, os, subprocess, sys, time, urllib.request

API_KEY = os.environ.get("INFLATE_API_KEY", "6d2e36b5-05e7-4edd-bd60-44cdbf448cf2")
BASE = "https://inflate-back.osc-fr1.scalingo.io"
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"}
SHOP = os.environ.get("SHOPIFY_SHOP", "natura-force-dev.myshopify.com")
TOKEN = os.environ.get("SHOPIFY_ACCESS_TOKEN", "")

if not TOKEN:
    try:
        for line in open(os.path.expanduser("~/.hermes/.env")):
            if line.startswith("SHOPIFY_ACCESS_TOKEN="):
                TOKEN = line.strip().split("=", 1)[1]
            elif line.startswith("SHOPIFY_SHOP="):
                SHOP = line.strip().split("=", 1)[1]
    except Exception:
        pass
if not TOKEN:
    print("ERREUR: SHOPIFY_ACCESS_TOKEN introuvable")
    sys.exit(1)

DRY = "--dry-run" in sys.argv
LIMIT = None
if "--limit" in sys.argv:
    LIMIT = int(sys.argv[sys.argv.index("--limit") + 1])

def gql(q, variables=None):
    body = json.dumps({"query": q, "variables": variables or {}})
    req = urllib.request.Request(
        f"https://{SHOP}/admin/api/2024-07/graphql.json", data=body.encode(),
        headers={"X-Shopify-Access-Token": TOKEN, "Content-Type": "application/json"})
    with urllib.request.urlopen(req) as r:
        return json.load(r)

def inflate_aggregate(pid):
    url = f"{BASE}/product_reviews/aggregate/?api_key={API_KEY}&product_id={pid}"
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)

# 1) list all products (paginated)
products = []
cursor = None
while True:
    q = """query($c: String) {
      products(first: 100, after: $c) {
        pageInfo { hasNextPage endCursor }
        edges { node { id legacyResourceId handle } }
      }
    }"""
    d = gql(q, {"c": cursor})
    if "errors" in d:
        print("GQL ERROR:", d["errors"]); sys.exit(1)
    p = d["data"]["products"]
    products += [e["node"] for e in p["edges"]]
    if not p["pageInfo"]["hasNextPage"]:
        break
    cursor = p["pageInfo"]["endCursor"]

print(f"{len(products)} produits trouvés")
if LIMIT:
    products = products[:LIMIT]
    print(f"limite: {LIMIT}")

# 2) fetch aggregate for each, build metafield writes
to_write = []   # (owner_id, rating_value, count_value, handle)
skipped = []
errors = []
for i, p in enumerate(products):
    pid = p["legacyResourceId"]
    try:
        agg = inflate_aggregate(pid)
        avg = agg.get("average_rating")
        total = agg.get("total_reviews")
        if avg is None or total is None:
            skipped.append((p["handle"], "no-data")); continue
        if total <= 0:
            skipped.append((p["handle"], f"0 avis")); continue
        to_write.append((p["id"], avg, total, p["handle"]))
    except Exception as e:
        errors.append((p["handle"], str(e)))
    if (i + 1) % 30 == 0:
        print(f"  {i+1}/{len(products)} ...")
    time.sleep(0.15)

print(f"\nà écrire: {len(to_write)} | sans avis/skip: {len(skipped)} | erreurs: {len(errors)}")
for h, why in skipped[:15]:
    print(f"  SKIP {h}: {why}")
for h, e in errors[:10]:
    print(f"  ERR {h}: {e}")

if DRY or not to_write:
    print("DRY RUN (rien écrit)" if DRY else "rien à écrire")
    sys.exit(0)

# 3) write metafields in batches of 25
def write_batch(mfs):
    q = """mutation($mfs: [MetafieldsSetInput!]!) { metafieldsSet(metafields: $mfs) {
      metafields { key value } userErrors { field message } } }"""
    d = gql(q, {"mfs": mfs})
    if d.get("errors") or d.get("data", {}).get("metafieldsSet", {}).get("userErrors"):
        print("  BATCH ERR:", d.get("errors") or d["data"]["metafieldsSet"]["userErrors"])
        return False
    return True

batch = []
ok = 0
for owner_id, avg, total, handle in to_write:
    batch.append({
        "ownerId": owner_id, "namespace": "inflate", "key": "rating",
        "type": "rating", "value": json.dumps({"scale_min": "1.0", "scale_max": "5.0", "value": f"{avg}"})
    })
    batch.append({
        "ownerId": owner_id, "namespace": "inflate", "key": "rating_count",
        "type": "number_integer", "value": str(total)
    })
    if len(batch) >= 24:   # 12 products per batch (max 25 metafields/mutation)
        if write_batch(batch):
            ok += len(batch) // 2
        batch = []
        print(f"  écrits: {ok} produits ...")
        time.sleep(0.3)
if batch:
    if write_batch(batch):
        ok += len(batch) // 2

print(f"\nTERMINÉ: {ok} produits mis à jour (inflate.rating / inflate.rating_count)")
