"""Sonda: pede à API da Shopee o esquema completo (introspecção do GraphQL)."""
import json
import os
from pathlib import Path
from bot.shopee import Shopee

shp = Shopee(os.environ.get("SHOPEE_APP_ID"), os.environ.get("SHOPEE_SECRET"))
q = "{__schema{queryType{fields{name args{name type{name kind ofType{name}}}}} mutationType{fields{name}} types{name kind fields{name type{name kind ofType{name kind}}}}}}"
d = shp._chamar(q)
Path("saida").mkdir(exist_ok=True)
Path("saida/esquema_shopee.json").write_text(json.dumps(d, ensure_ascii=False, indent=1))
s = d["__schema"]
print("CONSULTAS", [f["name"] for f in s["queryType"]["fields"]])
print("MUTACOES", [f["name"] for f in (s.get("mutationType") or {}).get("fields") or []])
for f in s["queryType"]["fields"]:
    print("ARGS", f["name"], [a["name"] for a in f["args"]])
for t in s["types"]:
    if t["kind"] == "OBJECT" and not t["name"].startswith("__") and t["fields"]:
        print("TIPO", t["name"], [x["name"] for x in t["fields"]])
