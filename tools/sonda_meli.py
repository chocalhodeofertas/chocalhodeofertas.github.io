import json, re, requests
e = json.load(open("data/estado.json"))
pares = list(e["links"].items())[:4]
H = {"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148",
     "Accept-Language": "pt-BR"}
for pid, link in pares:
    r = requests.get(link, headers=H, timeout=20, allow_redirects=True)
    hist = [h.headers.get("location", "")[:120] for h in r.history]
    ids = re.findall(r"MLB-?\d{6,}", r.text)
    uniq = list(dict.fromkeys(i.replace("-", "") for i in ids))
    print("###", pid, link, r.status_code, len(r.text))
    print("  redirects:", hist)
    print("  final:", r.url[:150])
    print("  ids:", uniq[:8], "pid presente:", pid in uniq, "pos:", uniq.index(pid) if pid in uniq else None)
    for pat in [r'"product_id":"(MLB\d+)"', r'"item_id":"(MLB\d+)"', r'/p/(MLB\d+)', r'wid=(MLB\d+)']:
        print("  ", pat, list(dict.fromkeys(re.findall(pat, r.text)))[:4])
