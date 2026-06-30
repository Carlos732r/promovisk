"""
PromoVisk – Script de Automação v3
------------------------------------
Estratégia: acessa a página de ofertas do ML como navegador,
extrai os produtos do JSON embutido na página (sem API, sem token).
"""

import os
import json
import re
import time
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone

# ── Credenciais Telegram ──────────────────────────────────────
TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHANNEL_ID", "")

# ── Configurações ─────────────────────────────────────────────
ARQUIVO_JSON    = "data/promocoes.json"
MAX_PRODUTOS    = 60   # Total máximo de produtos no JSON
DESCONTO_MINIMO = 5    # % mínimo para incluir

# URLs de ofertas do ML por categoria
PAGINAS = [
    ("Celulares",   "📱", "https://www.mercadolivre.com.br/ofertas#deals-filter-facets=MLB1055"),
    ("Tecnologia",  "💻", "https://www.mercadolivre.com.br/ofertas#deals-filter-facets=MLB1648"),
    ("Games",       "🎮", "https://www.mercadolivre.com.br/ofertas#deals-filter-facets=MLB1144"),
    ("TVs e Áudio", "📺", "https://www.mercadolivre.com.br/ofertas#deals-filter-facets=MLB1000"),
    ("Casa",        "🏠", "https://www.mercadolivre.com.br/ofertas#deals-filter-facets=MLB1574"),
    ("Ferramentas", "🔨", "https://www.mercadolivre.com.br/ofertas#deals-filter-facets=MLB1039"),
    ("Moda",        "👕", "https://www.mercadolivre.com.br/ofertas#deals-filter-facets=MLB1430"),
]

# Headers que imitam Chrome real
HEADERS = {
    "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection":      "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest":  "document",
    "Sec-Fetch-Mode":  "navigate",
    "Sec-Fetch-Site":  "none",
    "Cache-Control":   "max-age=0",
}


# ═══════════════════════════════════════════════════════════════
# 1. BUSCA NA PÁGINA DE OFERTAS
# ═══════════════════════════════════════════════════════════════
def buscar_ofertas_pagina(categoria_nome, categoria_emoji, url):
    """Acessa a página de ofertas e extrai produtos do JSON embutido."""
    print(f"\n🔍 {categoria_emoji} {categoria_nome}")
    print(f"   URL: {url}")

    try:
        session = requests.Session()
        # Primeiro acessa a home para pegar cookies
        session.get("https://www.mercadolivre.com.br", headers=HEADERS, timeout=15)
        time.sleep(1)

        # Depois acessa a página de ofertas
        resp = session.get(
            "https://www.mercadolivre.com.br/ofertas",
            headers=HEADERS,
            timeout=20,
        )
        print(f"   Status: {resp.status_code}")

        if resp.status_code != 200:
            print(f"   ⚠️ Erro HTTP: {resp.status_code}")
            return []

        return extrair_produtos_html(resp.text, categoria_nome, categoria_emoji)

    except Exception as e:
        print(f"   ⚠️ Erro: {e}")
        return []


def extrair_produtos_html(html, categoria_nome, categoria_emoji):
    """Extrai produtos do HTML da página de ofertas."""
    produtos = []

    # Tenta extrair do JSON embutido na página (__PRELOADED_STATE__ ou similar)
    padroes_json = [
        r'window\.__PRELOADED_STATE__\s*=\s*({.+?});\s*</script>',
        r'window\.__INITIAL_STATE__\s*=\s*({.+?});\s*</script>',
        r'"deals"\s*:\s*(\[.+?\])\s*[,}]',
        r'deals-app-container["\s]+data-component[^>]+>(.+?)</script>',
    ]

    for padrao in padroes_json:
        matches = re.findall(padrao, html, re.DOTALL)
        if matches:
            print(f"   ✔ JSON encontrado com padrão: {padrao[:40]}...")
            for match in matches[:1]:
                try:
                    dados = json.loads(match)
                    prods = extrair_de_json(dados, categoria_nome, categoria_emoji)
                    if prods:
                        print(f"   ✔ {len(prods)} produtos extraídos do JSON")
                        return prods
                except Exception as e:
                    print(f"   ⚠️ Erro ao parsear JSON: {e}")

    # Fallback: extrai do HTML diretamente com BeautifulSoup
    print("   Tentando extração via HTML...")
    return extrair_de_html(html, categoria_nome, categoria_emoji)


def extrair_de_json(dados, categoria_nome, categoria_emoji):
    """Extrai produtos de um JSON embutido na página."""
    produtos = []

    # Navega pelo JSON procurando listas de produtos
    def buscar_itens(obj, profundidade=0):
        if profundidade > 8:
            return []
        itens = []
        if isinstance(obj, list):
            for item in obj:
                if isinstance(item, dict) and item.get("price") and item.get("title"):
                    itens.append(item)
                else:
                    itens.extend(buscar_itens(item, profundidade + 1))
        elif isinstance(obj, dict):
            for v in obj.values():
                itens.extend(buscar_itens(v, profundidade + 1))
        return itens

    itens = buscar_itens(dados)
    for item in itens[:15]:
        prod = montar_produto(item, categoria_nome, categoria_emoji)
        if prod:
            produtos.append(prod)
    return produtos


def extrair_de_html(html, categoria_nome, categoria_emoji):
    """Extrai produtos diretamente do HTML com BeautifulSoup."""
    soup    = BeautifulSoup(html, "html.parser")
    produtos = []

    # Seletores comuns de cards de produto no ML
    seletores = [
        "li.promotion-item",
        "div.promotion-item",
        "li[class*='deal']",
        "div[class*='deal-item']",
        "article[class*='item']",
        "li.ui-search-layout__item",
    ]

    cards = []
    for seletor in seletores:
        cards = soup.select(seletor)
        if cards:
            print(f"   ✔ {len(cards)} cards encontrados com '{seletor}'")
            break

    if not cards:
        print("   ⚠️ Nenhum card encontrado no HTML")
        # Debug: salva trecho do HTML para análise
        print(f"   HTML snippet: {html[2000:2500]}")
        return []

    for card in cards[:15]:
        try:
            titulo_el = card.select_one("p.promotion-item__title, h2, .item__title, [class*='title']")
            preco_el  = card.select_one("[class*='price__fraction'], [class*='price-tag']")
            link_el   = card.select_one("a[href]")
            img_el    = card.select_one("img[src]")
            orig_el   = card.select_one("[class*='original'], [class*='before'], s")
            desc_el   = card.select_one("[class*='discount'], [class*='off']")

            if not titulo_el or not preco_el:
                continue

            titulo = titulo_el.get_text(strip=True)
            link   = link_el["href"] if link_el else "#"
            imagem = img_el.get("data-src") or img_el.get("src", "") if img_el else ""

            # Limpa e converte preço
            preco_txt = preco_el.get_text(strip=True).replace(".", "").replace(",", ".")
            preco_num = float(re.sub(r"[^\d.]", "", preco_txt) or "0")

            orig_num = 0
            if orig_el:
                orig_txt = orig_el.get_text(strip=True).replace(".", "").replace(",", ".")
                orig_num = float(re.sub(r"[^\d.]", "", orig_txt) or "0")

            desconto = 0
            if desc_el:
                desc_txt = desc_el.get_text(strip=True)
                desc_match = re.search(r"(\d+)", desc_txt)
                if desc_match:
                    desconto = int(desc_match.group(1))
            elif orig_num > preco_num > 0:
                desconto = round(((orig_num - preco_num) / orig_num) * 100)

            if preco_num <= 0 or desconto < DESCONTO_MINIMO:
                continue

            frete_el     = card.select_one("[class*='shipping'], [class*='frete']")
            frete_gratis = bool(frete_el and "grátis" in frete_el.get_text().lower())

            produtos.append({
                "id":                   re.search(r"MLB\d+", link).group() if re.search(r"MLB\d+", link) else f"item_{len(produtos)}",
                "titulo":               titulo,
                "categoria":            categoria_nome,
                "categoria_emoji":      categoria_emoji,
                "imagem":               imagem,
                "preco_atual":          round(preco_num, 2),
                "preco_original":       round(orig_num, 2) if orig_num > preco_num else round(preco_num * 1.2, 2),
                "desconto_porcentagem": desconto,
                "parcelas_num":         0,
                "parcelas_valor":       0,
                "frete_gratis":         frete_gratis,
                "frete_tag":            "Frete grátis ⚡ FULL" if frete_gratis else "",
                "cupom_codigo":         "",
                "cupom_valor":          "",
                "loja":                 "Mercado Livre",
                "link_afiliado":        link,
                "destaque":             desconto >= 25,
                "adicionado_em":        datetime.now(timezone.utc).isoformat(),
            })
        except Exception as e:
            print(f"   ⚠️ Erro ao processar card: {e}")
            continue

    print(f"   ✔ {len(produtos)} produtos extraídos do HTML")
    return produtos


def montar_produto(item, categoria_nome, categoria_emoji):
    """Monta produto a partir de um dict do JSON embutido."""
    try:
        preco_atual    = float(item.get("price", 0) or 0)
        preco_original = float(item.get("original_price", 0) or item.get("originalPrice", 0) or 0)
        titulo         = item.get("title", "") or item.get("name", "")
        link           = item.get("permalink", "") or item.get("url", "") or "#"
        imagem         = item.get("thumbnail", "") or item.get("image", "") or ""
        item_id        = item.get("id", "") or re.search(r"MLB\d+", link).group() if re.search(r"MLB\d+", link) else ""

        if not titulo or preco_atual <= 0:
            return None

        if preco_original > preco_atual:
            desconto = round(((preco_original - preco_atual) / preco_original) * 100)
        else:
            desconto = int(item.get("discount_percentage", 0) or item.get("discountPercentage", 0) or 0)

        if desconto < DESCONTO_MINIMO:
            return None

        frete        = item.get("shipping", {}) or {}
        frete_gratis = frete.get("free_shipping", False) or frete.get("freeShipping", False)

        parcelas     = item.get("installments", {}) or {}
        parcelas_num = int(parcelas.get("quantity", 0) or 0)
        parcelas_val = float(parcelas.get("amount", 0) or 0)

        return {
            "id":                   str(item_id),
            "titulo":               titulo,
            "categoria":            categoria_nome,
            "categoria_emoji":      categoria_emoji,
            "imagem":               imagem.replace("I.jpg", "O.jpg"),
            "preco_atual":          round(preco_atual, 2),
            "preco_original":       round(preco_original, 2) if preco_original > preco_atual else round(preco_atual * 1.2, 2),
            "desconto_porcentagem": desconto,
            "parcelas_num":         parcelas_num,
            "parcelas_valor":       round(parcelas_val, 2),
            "frete_gratis":         frete_gratis,
            "frete_tag":            "Frete grátis ⚡ FULL" if frete_gratis else "",
            "cupom_codigo":         "",
            "cupom_valor":          "",
            "loja":                 "Mercado Livre",
            "link_afiliado":        link,
            "destaque":             desconto >= 25,
            "adicionado_em":        datetime.now(timezone.utc).isoformat(),
        }
    except Exception:
        return None


# ═══════════════════════════════════════════════════════════════
# 2. JSON
# ═══════════════════════════════════════════════════════════════
def carregar_ids_existentes():
    try:
        with open(ARQUIVO_JSON, "r", encoding="utf-8-sig") as f:
            return {p["id"] for p in json.load(f).get("promocoes", [])}
    except Exception:
        return set()


def salvar_json(promocoes):
    os.makedirs("data", exist_ok=True)
    with open(ARQUIVO_JSON, "w", encoding="utf-8") as f:
        json.dump({
            "atualizado_em": datetime.now(timezone.utc).isoformat(),
            "total":         len(promocoes),
            "promocoes":     promocoes,
        }, f, ensure_ascii=False, indent=2)
    print(f"\n✅ JSON salvo com {len(promocoes)} promoções!")


# ═══════════════════════════════════════════════════════════════
# 3. TELEGRAM
# ═══════════════════════════════════════════════════════════════
def enviar_telegram(produto):
    if not TELEGRAM_TOKEN or TELEGRAM_TOKEN == "placeholder":
        return

    cupom_linha = ""
    if produto.get("cupom_codigo"):
        cupom_linha = f"\n🏷️ Cupom: `{produto['cupom_codigo']}`"
        if produto.get("cupom_valor"):
            cupom_linha += f" ({produto['cupom_valor']} off)"

    frete_linha = f"\n✅ {produto['frete_tag']}" if produto.get("frete_tag") else ""

    texto = (
        f"{produto['categoria_emoji']} *{produto['titulo']}*\n\n"
        f"~~R$ {produto['preco_original']:.2f}~~ → "
        f"*R$ {produto['preco_atual']:.2f}* "
        f"*{produto['desconto_porcentagem']}% OFF*"
        f"{frete_linha}"
        f"{cupom_linha}\n\n"
        f"🛒 [Ver oferta]({produto['link_afiliado']})\n\n"
        f"_PromoVisk – Promoções que valem a pena_ 🔥"
    )

    resp = requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        data={
            "chat_id":                  TELEGRAM_CHAT_ID,
            "text":                     texto,
            "parse_mode":               "Markdown",
            "disable_web_page_preview": False,
        },
        timeout=10,
    )
    print(f"   Telegram: {'✈️ Enviado!' if resp.status_code == 200 else f'⚠️ Erro {resp.status_code}'}")


# ═══════════════════════════════════════════════════════════════
# 4. MAIN
# ═══════════════════════════════════════════════════════════════
def main():
    print("\n🚀 PromoVisk – Iniciando busca de promoções...")
    print(f"⏰ {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}\n")

    ids_existentes = carregar_ids_existentes()
    todas          = []
    ids_vistos     = set()

    for categoria_nome, categoria_emoji, url in PAGINAS:
        produtos = buscar_ofertas_pagina(categoria_nome, categoria_emoji, url)

        for prod in produtos:
            if prod["id"] in ids_vistos:
                continue
            ids_vistos.add(prod["id"])
            todas.append(prod)

            if prod["id"] not in ids_existentes:
                enviar_telegram(prod)

        time.sleep(2)  # Pausa entre categorias para não sobrecarregar

    todas.sort(key=lambda x: x["desconto_porcentagem"], reverse=True)
    todas = todas[:MAX_PRODUTOS]

    if todas:
        salvar_json(todas)
    else:
        print("\n⚠️ Nenhuma promoção encontrada.")

    print(f"\n✅ Concluído! {len(todas)} promoções salvas.\n")


if __name__ == "__main__":
    main()
