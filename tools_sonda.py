import os, json, requests
from bot.mercadolivre import token_do_app
t = token_do_app(os.environ["ML_CLIENT_ID"], os.environ["ML_CLIENT_SECRET"])
H = {"Authorization": f"Bearer {t}"}
def g(p, auth=True):
    r = requests.get("https://api.mercadolibre.com"+p, headers=H if auth else {}, timeout=20)
    try: j = r.json()
    except Exception: j = r.text[:150]
    print(f"\n### {r.status_code} {p} auth={auth}\n" + json.dumps(j, ensure_ascii=False)[:900])
    return j
for cat in ["MLB1384", "MLB1132"]:
    c = g(f"/categories/{cat}", auth=False)
    if isinstance(c, dict):
        print("FILHOS", cat, [(x["id"], x["name"]) for x in c.get("children_categories", [])])
h = g("/highlights/MLB/category/MLB1384")
g("/sites/MLB/search?category=MLB1384&limit=3")
g("/sites/MLB/search?q=fralda&limit=3")
if isinstance(h, dict) and h.get("content"):
    for e in h["content"][:3]:
        if e.get("type") == "PRODUCT":
            g(f"/products/{e['id']}")
            g(f"/products/{e['id']}/items?limit=2")
        else:
            g(f"/items?ids={e['id']}&attributes=id,title,price,original_price,permalink,status")
g("/sites/MLB/categories")
