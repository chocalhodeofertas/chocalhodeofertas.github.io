"""Página pública do Chocalho (GitHub Pages): ofertas do momento + link do canal.

O bot reescreve docs/index.html no máximo uma vez por hora, e só quando muda.
"""
import hashlib
import html
import json
import re
from pathlib import Path

from .mensagens import EMOJI_CATEGORIA, brl

ARQ = Path(__file__).resolve().parent.parent / "docs" / "index.html"
MAX_ITENS = 60

NOMES = {
    "fralda": "Fraldas", "higiene": "Higiene", "roupa": "Roupas", "brinquedo": "Brinquedos",
    "jogo": "Jogos", "quarto": "Quarto", "passeio": "Passeio", "alimentacao": "Alimentação",
    "gestante": "Gestante", "game": "Games", "livro": "Livros", "escola": "Escola", "esporte": "Esporte",
    "casa": "Casa e quarto", "festa": "Festa", "outros": "Outros",
}


def guardar(estado, ofertas, agora):
    """Guarda as ofertas atuais (só as que têm link oficial) para a página."""
    if not ofertas:
        return
    estado["vitrine"] = {
        "em": agora.isoformat(timespec="minutes"),
        "itens": [
            {"id": o.id, "titulo": o.titulo[:110], "preco": o.preco, "de": o.preco_de,
             "desconto": round(o.desconto, 3), "link": o.link, "imagem": o.imagem, "categoria": o.categoria}
            for o in ofertas[:MAX_ITENS]
        ],
    }


def link_canal(canal):
    canal = (canal or "").strip()
    if canal.startswith("@"):
        return "https://t.me/" + canal[1:]
    if canal.startswith("https://t.me/"):
        return canal
    return ""


def _card(i):
    e = html.escape
    emoji = EMOJI_CATEGORIA.get(i["categoria"], "✨")
    preco_de = f'<s>{brl(i["de"])}</s>' if i.get("de") else ""
    selo = f'<span class="selo">-{round(i["desconto"] * 100)}%</span>' if i.get("de") else ""
    img = (f'<img src="{e(i["imagem"], quote=True)}" alt="" loading="lazy" '
           f'onerror="this.outerHTML=\'<div class=sem-foto>{emoji}</div>\'">' if i.get("imagem")
           else f'<div class="sem-foto">{emoji}</div>')
    return (
        f'<a class="card" data-cat="{e(i["categoria"])}" href="{e(i["link"], quote=True)}" '
        f'target="_blank" rel="noopener sponsored">'
        f'<div class="foto">{img}{selo}</div>'
        f'<div class="info"><p class="titulo">{e(i["titulo"])}</p>'
        f'<p class="precos">{preco_de}<b>{brl(i["preco"])}</b></p>'
        f'<span class="ver">Ver no Mercado Livre</span></div></a>'
    )


def gerar_html(estado, canal, grupo_wa=None):
    v = estado.get("vitrine") or {}
    itens = v.get("itens") or []
    cats = sorted({i["categoria"] for i in itens}, key=lambda c: NOMES.get(c, c))
    chips = '<button class="chip ativo" data-f="">Tudo</button>' + "".join(
        f'<button class="chip" data-f="{c}">{EMOJI_CATEGORIA.get(c, "✨")} {NOMES.get(c, c.title())}</button>'
        for c in cats)
    url_canal = link_canal(canal)
    botoes = []
    if grupo_wa:
        botoes.append('<a class="entrar wa" href="grupo.html">Entrar no grupo do WhatsApp</a>')
    if url_canal:
        botoes.append(f'<a class="entrar" href="{html.escape(url_canal, quote=True)}" target="_blank" '
                      f'rel="noopener">Entrar no canal do Telegram</a>')
    botao = '<div class="botoes">' + "".join(botoes) + "</div>" if botoes else ""
    em = v.get("em", "")
    hora = f"{em[8:10]}/{em[5:7]} às {em[11:16]}" if len(em) >= 16 else ""
    cards = "".join(_card(i) for i in itens) or '<p class="vazio">As próximas ofertas aparecem aqui em breve. 🪇</p>'
    return f"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Chocalho de Ofertas</title>
<meta name="description" content="Ofertas de bebê e criança no Mercado Livre, atualizadas o dia todo.">
<meta property="og:title" content="Chocalho de Ofertas">
<meta property="og:description" content="Ofertas de bebê e criança no Mercado Livre, atualizadas o dia todo.">
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>🪇</text></svg>">
<style>
:root {{
  --fundo:#fff8ec; --cartao:#ffffff; --texto:#2b2620; --suave:#7a6f63; --borda:#f0e2c8;
  --destaque:#f4b400; --destaque-texto:#2b2620; --selo:#e2574c; --link:#3366cc;
}}
@media (prefers-color-scheme: dark) {{
  :root:not([data-theme="light"]) {{
    --fundo:#1d1a16; --cartao:#2a2620; --texto:#f3ece2; --suave:#b5a998; --borda:#3a342c;
    --destaque:#f4b400; --destaque-texto:#1d1a16; --selo:#ef6b60; --link:#8fb0ff;
  }}
}}
:root[data-theme="dark"] {{
  --fundo:#1d1a16; --cartao:#2a2620; --texto:#f3ece2; --suave:#b5a998; --borda:#3a342c;
  --destaque:#f4b400; --destaque-texto:#1d1a16; --selo:#ef6b60; --link:#8fb0ff;
}}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--fundo); color:var(--texto);
  font:16px/1.4 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif; }}
header {{ text-align:center; padding:28px 16px 8px; }}
.logo {{ font-size:44px; }}
h1 {{ margin:4px 0 2px; font-size:26px; letter-spacing:-.3px; }}
.sub {{ margin:0 0 16px; color:var(--suave); }}
.botoes {{ display:flex; flex-wrap:wrap; gap:10px; justify-content:center; }}
.entrar.wa {{ background:#25d366; color:#08331a; }}
.entrar {{ display:inline-block; background:var(--destaque); color:var(--destaque-texto); font-weight:700;
  padding:12px 22px; border-radius:999px; text-decoration:none; }}
.chips {{ display:flex; gap:8px; overflow-x:auto; padding:18px 16px 6px; max-width:1100px; margin:0 auto; }}
.chip {{ flex:none; border:1px solid var(--borda); background:var(--cartao); color:var(--texto);
  padding:7px 14px; border-radius:999px; font:inherit; font-size:14px; cursor:pointer; }}
.chip.ativo {{ background:var(--destaque); color:var(--destaque-texto); border-color:var(--destaque); font-weight:600; }}
main {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(160px,1fr)); gap:12px;
  padding:12px 16px 24px; max-width:1100px; margin:0 auto; }}
.card {{ display:flex; flex-direction:column; background:var(--cartao); border:1px solid var(--borda);
  border-radius:14px; overflow:hidden; color:inherit; text-decoration:none; }}
.foto {{ position:relative; aspect-ratio:1; background:#fff; display:flex; align-items:center; justify-content:center; }}
.foto img {{ width:100%; height:100%; object-fit:contain; }}
.sem-foto {{ font-size:48px; }}
.selo {{ position:absolute; top:8px; left:8px; background:var(--selo); color:#fff; font-weight:700;
  font-size:13px; padding:3px 8px; border-radius:999px; }}
.info {{ padding:10px 12px 12px; display:flex; flex-direction:column; gap:6px; flex:1; }}
.titulo {{ margin:0; font-size:14px; display:-webkit-box; -webkit-line-clamp:3; -webkit-box-orient:vertical; overflow:hidden; }}
.precos {{ margin:auto 0 0; display:flex; flex-direction:column; }}
.precos s {{ color:var(--suave); font-size:13px; }}
.precos b {{ font-size:18px; }}
.ver {{ color:var(--link); font-size:13px; font-weight:600; }}
.vazio {{ grid-column:1/-1; text-align:center; color:var(--suave); padding:40px 0; }}
footer {{ text-align:center; color:var(--suave); font-size:13px; padding:8px 16px 32px; max-width:640px; margin:0 auto; }}
</style>
</head>
<body>
<header>
  <div class="logo">🪇</div>
  <h1>Chocalho de Ofertas</h1>
  <p class="sub">Ofertas de bebê e criança no Mercado Livre</p>
  {botao}
</header>
<nav class="chips">{chips}</nav>
<main>{cards}</main>
<footer>
  <p>Atualizado em {hora}. Preços e estoque podem mudar a qualquer momento.</p>
  <p>#publi · Os links são de afiliado: o Chocalho pode receber comissão pelas compras, sem custo extra pra você.</p>
</footer>
<script>
document.querySelectorAll('.chip').forEach(function (b) {{
  b.addEventListener('click', function () {{
    document.querySelectorAll('.chip').forEach(function (x) {{ x.classList.remove('ativo'); }});
    b.classList.add('ativo');
    var f = b.getAttribute('data-f');
    document.querySelectorAll('.card').forEach(function (c) {{
      c.style.display = (!f || c.getAttribute('data-cat') === f) ? '' : 'none';
    }});
  }});
}});
</script>
</body>
</html>
"""


def gerar_grupo_html(grupo_wa):
    """Página-ponte: abre o app do WhatsApp direto (inclusive de dentro do Instagram/Facebook)."""
    m = re.search(r"chat\.whatsapp\.com/([A-Za-z0-9]+)", grupo_wa or "")
    codigo = m.group(1) if m else ""
    web = f"https://chat.whatsapp.com/{codigo}" if codigo else (grupo_wa or "")
    e = html.escape
    return f"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Chocalho de Ofertas</title>
<meta name="description" content="Entre no grupo de ofertas de bebê e criança.">
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>🪇</text></svg>">
<style>
:root {{ --fundo:#fff8ec; --texto:#2b2620; --suave:#7a6f63; }}
@media (prefers-color-scheme: dark) {{ :root:not([data-theme="light"]) {{ --fundo:#1d1a16; --texto:#f3ece2; --suave:#b5a998; }} }}
:root[data-theme="dark"] {{ --fundo:#1d1a16; --texto:#f3ece2; --suave:#b5a998; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; min-height:100vh; display:flex; align-items:center; justify-content:center; text-align:center;
  background:var(--fundo); color:var(--texto); font:17px/1.45 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif; padding:24px 16px; }}
.logo {{ font-size:56px; }}
h1 {{ font-size:24px; margin:6px 0 4px; }}
p {{ color:var(--suave); margin:0 0 22px; }}
a.botao {{ display:block; max-width:340px; margin:0 auto 14px; padding:16px 22px; border-radius:999px;
  background:#25d366; color:#08331a; font-weight:800; font-size:19px; text-decoration:none; }}
small {{ color:var(--suave); display:block; max-width:340px; margin:0 auto; }}
</style>
</head>
<body>
<main>
  <div class="logo">🪇</div>
  <h1>Chocalho de Ofertas</h1>
  <p>Abrindo o grupo no WhatsApp…</p>
  <a class="botao" id="entrar" href="{e(web, quote=True)}">Entrar no grupo do WhatsApp</a>
  <small>Se o WhatsApp não abrir sozinho, toque no botão. #publi: os links do grupo são de afiliado.</small>
</main>
<script>
(function () {{
  var codigo = {json.dumps(codigo)}, web = {json.dumps(web)}, ua = navigator.userAgent || "";
  function abrir() {{
    if (window.fbq) {{ try {{ fbq('track', 'Lead'); }} catch (e) {{}} }}
    if (!codigo) {{ location.href = web; return; }}
    if (/android/i.test(ua)) {{
      location.href = "intent://chat/?code=" + codigo + "#Intent;scheme=whatsapp;package=com.whatsapp;" +
        "S.browser_fallback_url=" + encodeURIComponent(web) + ";end";
    }} else if (/iphone|ipad|ipod/i.test(ua)) {{
      location.href = "whatsapp://chat?code=" + codigo;
      setTimeout(function () {{ location.href = web; }}, 1600);
    }} else {{
      location.href = web;
    }}
  }}
  document.getElementById("entrar").addEventListener("click", function (ev) {{ ev.preventDefault(); abrir(); }});
  setTimeout(abrir, 400);
}})();
</script>
</body>
</html>
"""


def talvez_publicar(estado, canal, agora, arquivo=ARQ, log=print, grupo_wa=None):
    """Reescreve a página se mudou e se já passou 1 hora desde a última vez."""
    ultima = estado.get("vitrine_publicada_em")
    if ultima and ultima[:13] == agora.isoformat()[:13]:
        return False
    conteudo = gerar_html(estado, canal, grupo_wa)
    assinatura = hashlib.sha1(json.dumps([(estado.get("vitrine") or {}).get("itens"), canal, grupo_wa],
                                         sort_keys=True)
                              .encode()).hexdigest()
    if assinatura == estado.get("vitrine_assinatura") and Path(arquivo).exists():
        return False
    Path(arquivo).parent.mkdir(parents=True, exist_ok=True)
    Path(arquivo).write_text(conteudo, encoding="utf-8")
    if grupo_wa:
        (Path(arquivo).parent / "grupo.html").write_text(gerar_grupo_html(grupo_wa), encoding="utf-8")
    estado["vitrine_assinatura"] = assinatura
    estado["vitrine_publicada_em"] = agora.isoformat(timespec="minutes")
    log("Página de ofertas atualizada.")
    return True
