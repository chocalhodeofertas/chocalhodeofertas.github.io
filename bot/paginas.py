"""Moldura comum das páginas escondidas do Chocalho (números e fila): mesma marca do site público
(Schibsted Grotesk, roxo/uva/rosa), feitas para ler no celular.

Ideia do desenho: a página fala em frases. O topo é uma frase grande montada com os números do dia
(a única coisa chamativa); o resto é quieto: seções com título, listas e gráficos simples.
"""
import html

CSS = """
@font-face { font-family:"Schibsted Grotesk"; src:url(fonts/schibsted.woff2) format("woff2"); font-weight:400 900; font-display:swap; }
:root { --fundo:#FBF7FD; --papel:#FFFFFF; --texto:#24062A; --suave:#6B4F72; --linha:#EADCF1; --lav:#F1E1FB;
  --uva:#3A0A40; --roxo:#8E2BB0; --rosa:#DC1173; --ok:#1F7A52; --ok-fundo:#E1F3E9; --alerta:#B3123F; --alerta-fundo:#FCE4EC;
  color-scheme:light; }
@media (prefers-color-scheme: dark) { :root { --fundo:#1E0524; --papel:#2A0B31; --texto:#F7EEFB; --suave:#C7B0CF;
  --linha:#46214F; --lav:#3A1744; --uva:#F1E1FB; --roxo:#D08BEA; --rosa:#FF6FAE; --ok:#7BD9AC; --ok-fundo:#173A2A;
  --alerta:#FF8FB0; --alerta-fundo:#45132A; color-scheme:dark; } }
* { box-sizing:border-box; }
html { -webkit-text-size-adjust:100%; }
body { margin:0; background:var(--fundo); color:var(--texto);
  font:400 16px/1.5 "Schibsted Grotesk", system-ui, sans-serif; }
.pagina { max-width:720px; margin:0 auto; padding:20px max(18px, env(safe-area-inset-right)) 56px max(18px, env(safe-area-inset-left)); }
.topo { display:flex; align-items:center; justify-content:space-between; gap:12px; flex-wrap:wrap; margin-bottom:28px; }
.marca { font-weight:800; font-size:18px; color:var(--uva); letter-spacing:-.01em; }
.abas { display:flex; gap:4px; background:var(--lav); padding:4px; border-radius:999px; }
.abas a { color:var(--uva); text-decoration:none; font-weight:600; font-size:14px; padding:6px 14px; border-radius:999px; }
.abas a[aria-current="page"] { background:var(--papel); box-shadow:0 1px 2px rgba(58,10,64,.12); }
.abas a:focus-visible, a:focus-visible { outline:3px solid var(--roxo); outline-offset:2px; }
.manchete { font-weight:800; font-size:clamp(28px, 7vw, 40px); line-height:1.12; letter-spacing:-.02em; color:var(--uva);
  margin:0 0 10px; max-width:20ch; text-wrap:balance; }
.lide { font-size:17px; color:var(--texto); margin:0 0 6px; max-width:52ch; }
.quando { font-size:13px; color:var(--suave); margin:0 0 28px; }
.aviso { background:var(--alerta-fundo); color:var(--alerta); border-radius:12px; padding:12px 14px; font-weight:600; margin:0 0 24px; }
.fatos { display:grid; grid-template-columns:repeat(auto-fit, minmax(150px, 1fr)); margin:0 0 36px; border-top:2px solid var(--uva); }
.fatos div { padding:12px 12px 12px 0; border-bottom:1px solid var(--linha); }
.fatos dt { font-size:13px; color:var(--suave); }
.fatos dd { font-variant-numeric:tabular-nums; margin:2px 0 0; font-size:28px; font-weight:800; line-height:1.1; color:var(--texto); }
.fatos dd small { font-variant-numeric:normal; display:block; font-size:13px; font-weight:400; color:var(--suave); margin-top:4px; line-height:1.35; }
section { margin:0 0 40px; min-width:0; }
h2 { font-size:20px; font-weight:800; color:var(--uva); margin:0 0 4px; letter-spacing:-.01em; }
.nota { font-size:14px; color:var(--suave); margin:0 0 14px; max-width:60ch; }
.duas { display:grid; grid-template-columns:repeat(auto-fit, minmax(280px, 1fr)); gap:0 28px; }
.lista { list-style:none; margin:0; padding:0 16px; background:var(--papel); border:1px solid var(--linha); border-radius:16px; }
.lista li { padding:12px 0; border-top:1px solid var(--linha); }
.lista li:first-child { border-top:0; }
.lista li.vazio { color:var(--suave); font-size:15px; }
.linha-topo { display:flex; flex-wrap:wrap; align-items:center; gap:4px 10px; font-size:13px; color:var(--suave); }
.hora { font-variant-numeric:tabular-nums; font-weight:700; color:var(--texto); min-width:40px; }
.nome { font-size:15px; overflow-wrap:anywhere; margin-top:3px; }
.extra { font-size:14px; color:var(--suave); margin-top:2px; }
.extra b { color:var(--texto); font-weight:700; }
.pill { display:inline-block; font-size:12px; font-weight:700; padding:3px 10px; border-radius:999px; margin-left:auto; }
.pill.ok { background:var(--ok-fundo); color:var(--ok); } .pill.fora { background:var(--alerta-fundo); color:var(--alerta); }
.pill.espera { background:var(--lav); color:var(--roxo); } .pill.mudo { background:var(--lav); color:var(--suave); }
.pill.alerta { background:var(--alerta-fundo); color:var(--alerta); }
.sobe { color:var(--ok); } .desce { color:var(--alerta); } .mudo { color:var(--suave); }
svg { width:100%; height:auto; display:block; overflow:visible; }
.grade { stroke:var(--linha); stroke-width:1; } .base { stroke:var(--suave); stroke-width:1; opacity:.5; }
.eixo { fill:var(--suave); font-size:12px; font-family:"Schibsted Grotesk", sans-serif; }
.rotulo { fill:var(--texto); font-size:13px; font-weight:700; font-family:"Schibsted Grotesk", sans-serif; }
.linha-graf { fill:none; stroke:var(--roxo); stroke-width:2; stroke-linejoin:round; stroke-linecap:round; }
.area { fill:var(--roxo); opacity:.1; } .ponto { fill:var(--roxo); stroke:var(--fundo); stroke-width:2; }
.barra { fill:var(--roxo); } .barra.sai { fill:var(--rosa); } .alvo { fill:transparent; }
.alvo:hover + .dica, .alvo:focus + .dica { opacity:1; }
.legenda { display:flex; gap:16px; font-size:13px; color:var(--suave); margin:8px 0 0; }
.legenda i { display:inline-block; width:10px; height:10px; border-radius:3px; margin-right:6px; vertical-align:-1px; }
.vazio { color:var(--suave); font-size:15px; }
table { width:100%; border-collapse:collapse; font-size:15px; }
td { padding:10px 4px; border-top:1px solid var(--linha); vertical-align:top; overflow-wrap:anywhere; }
td.num { font-variant-numeric:tabular-nums; text-align:right; white-space:nowrap; }
@media (prefers-reduced-motion: no-preference) {
  .manchete { animation:entra .5s ease-out both; }
  @keyframes entra { from { opacity:0; transform:translateY(6px); } }
}
"""

ABAS = (("numeros", "Números", "numeros-bcfc6fce.html"), ("fila", "Fila", "fila-4e7a91c3.html"))


def pagina(titulo, ativa, corpo):
    abas = "".join(
        f'<a href="{arq}"' + (' aria-current="page"' if chave == ativa else "") + f">{nome}</a>"
        for chave, nome, arq in ABAS
    )
    return f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex, nofollow, noarchive">
<meta http-equiv="refresh" content="600">
<title>{html.escape(titulo)}</title>
<link rel="preload" href="fonts/schibsted.woff2" as="font" type="font/woff2" crossorigin>
<style>{CSS}</style></head>
<body><div class="pagina">
<header class="topo"><span class="marca">Chocalho de Ofertas</span><nav class="abas" aria-label="Páginas">{abas}</nav></header>
{corpo}
</div></body></html>
"""


def fatos(itens):
    """Linha de números de apoio: [(rótulo, valor, explicação)]."""
    return '<dl class="fatos">' + "".join(
        f"<div><dt>{rot}</dt><dd>{val}" + (f"<small>{extra}</small>" if extra else "") + "</dd></div>"
        for rot, val, extra in itens) + "</dl>"


def plural(n, um, varios):
    return f"{n} {um if n == 1 else varios}"
