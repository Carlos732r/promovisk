"""
PromoVisk – Script de Automação
Busca produtos por categoria no ML, filtra descontos reais,
captura cupons e salva em JSON + envia pro Telegram.
"""

import os
import json
import requests
from datetime import datetime, timezone

# ── Credenciais ───────────────────────────────────────────────
ML_CLIENT_ID     = os.environ["ML_CLIENT_ID"]
ML_CLIENT_SECRET = os.environ["ML_CLIENT_SECRET"]
TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHANNEL_ID", "")

# ── Configurações ─────────────────────────────────────────────
SITE_ID         = "MLB"
DESCONTO_MINIMO = 5
MAX_POR_CAT     = 8
ARQUIVO_JSON    = "data/promocoes.json"

# Categorias com IDs oficiais do ML Brasil
CATEGORIAS = [
    ("Celulares",   "📱", "MLB1055"),
    ("Tecnologia",  "💻", "MLB1648"),
    ("Games",       "🎮", "MLB1144"),
    ("TVs e Áudio", "📺", "MLB1000"),
    ("Casa",        "🏠", "MLB1574"),
    ("Ferramentas", "🔨", "MLB1039"),
    ("Moda",        "👕", "MLB1430"),
]


# ═══════════════════════════════════════════════════════════════
# 1. TOKEN
# ═══════════════════════════════════════════════════════════════
def obter_token():
    print("🔑 Obtendo token...")
    resp = requests.post(
        "https://api.mercadolibre.com/oauth/token",
        data={
            "grant_type":    "client_credentials",
            "client_id":     ML_CLIENT_ID,
            "client_secret": ML_CLIENT_SECRET,
        },
        timeout=15,
    )
    resp.raise_for_status()
    print("✅ Token obtido!")
    return resp.json()["access_token"]


# ═══════════════════════════════════════════════════════════════
# 2. BUSCA POR CATEGORIA (sem parâmetros restritos)
# ═══════════════════════════════════════════════════════════════
def buscar_por_categoria(token, categoria_id):
    url     = "https://api.mercadolibre.com/sites/MLB/search"
    headers = {**HEADERS_NAVEGADOR, "Authorization": f"Bearer {token}"}
    params  = {
        "category": categoria_id,
        "limit":    MAX_POR_CAT * 5,
        "sort":     "relevance",
    }
    resp = requests.get(url, params=params, headers=headers, timeout=15)
    print(f"   Status: {resp.status_code}")
    if resp.status_code != 200:
        print(f"   Erro: {resp.text[:200]}")
        return []
    resultados = resp.json().get("results", [])
    print(f"   Retornou: {len(resultados)} itens")
    return resultados


# ═══════════════════════════════════════════════════════════════
# 3. BUSCAR DETALHES DO PRODUTO (preço, cupom, etc)
# ═══════════════════════════════════════════════════════════════
HEADERS_NAVEGADOR = {
    "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept":          "application/json, text/plain, */*",
    "Accept-Language": "pt-BR,pt;q=0.9",
    "Referer":         "https://www.mercadolivre.com.br/",
    "Origin":          "https://www.mercadolivre.com.br",
}

def buscar_detalhes(token, item_id):
    """Busca detalhes extras do produto incluindo cupons e promoções."""
    headers = {**HEADERS_NAVEGADOR, "Authorization": f"Bearer {token}"}
    resp = requests.get(
        f"https://api.mercadolibre.com/items/{item_id}",
        headers=headers,
        timeout=10,
    )
    if resp.status_code != 200:
        return None
    return resp.json()


# ═══════════════════════════════════════════════════════════════
# 4. PROCESSAR PRODUTO
# ═══════════════════════════════════════════════════════════════
def processar_produto(item, categoria_nome, categoria_emoji, token):
    preco_atual    = item.get("price", 0) or 0
    preco_original = item.get("original_price") or 0

    if preco_atual <= 0:
        return None

    # Calcula desconto
    if preco_original > preco_atual:
        desconto = round(((preco_original - preco_atual) / preco_original) * 100)
    else:
        # Sem original_price no resultado da busca — tenta buscar detalhes
        preco_original = preco_atual
        desconto = 0

    # Tenta buscar detalhes para pegar original_price e cupons
    cupom_codigo = ""
    cupom_valor  = ""
    try:
        detalhes = buscar_detalhes(token, item.get("id", ""))
        if detalhes:
            orig = detalhes.get("original_price") or 0
            if orig > preco_atual:
                preco_original = orig
                desconto = round(((preco_original - preco_atual) / preco_original) * 100)

            # Captura cupons se existirem
            sale_terms = detalhes.get("sale_terms") or []
            for term in sale_terms:
                if term.get("id") == "COUPON_CODE":
                    cupom_codigo = term.get("value_struct", {}).get("number", "") or term.get("value_name", "")
                if term.get("id") == "COUPON_DISCOUNT":
                    cupom_valor = term.get("value_name", "")

            # Também verifica promotions
            promotions = detalhes.get("promotions") or []
            for promo in promotions:
                if promo.get("coupon_code"):
                    cupom_codigo = promo.get("coupon_code", "")
                    cupom_valor  = promo.get("coupon_discount", "")
    except Exception as e:
        print(f"   ⚠️ Erro ao buscar detalhes de {item.get('id')}: {e}")

    if desconto < DESCONTO_MINIMO:
        return None

    parcelas     = item.get("installments") or {}
    parcelas_num = parcelas.get("quantity", 0)
    parcelas_val = parcelas.get("amount", 0)
    frete_gratis = (item.get("shipping") or {}).get("free_shipping", False)

    # Monta tag de frete igual ao ML
    if frete_gratis:
        frete_tag = "Frete grátis ⚡ FULL"
    else:
        frete_tag = ""

    return {
        "id":                   item.get("id", ""),
        "titulo":               item.get("title", ""),
        "categoria":            categoria_nome,
        "categoria_emoji":      categoria_emoji,
        "imagem":               (item.get("thumbnail") or "").replace("I.jpg", "O.jpg"),
        "preco_atual":          round(preco_atual, 2),
        "preco_original":       round(preco_original, 2),
        "desconto_porcentagem": desconto,
        "parcelas_num":         parcelas_num,
        "parcelas_valor":       round(parcelas_val, 2),
        "frete_gratis":         frete_gratis,
        "frete_tag":            frete_tag,
        "cupom_codigo":         cupom_codigo,
        "cupom_valor":          cupom_valor,
        "loja":                 "Mercado Livre",
        "link_afiliado":        item.get("permalink", "#"),
        "destaque":             desconto >= 25,
        "adicionado_em":        datetime.now(timezone.utc).isoformat(),
    }


# ═══════════════════════════════════════════════════════════════
# 5. JSON
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
    print(f"✅ JSON salvo com {len(promocoes)} promoções!")


# ═══════════════════════════════════════════════════════════════
# 6. TELEGRAM
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
        f"🛒 [Ver oferta no Mercado Livre]({produto['link_afiliado']})\n\n"
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
    status = "✈️ Enviado!" if resp.status_code == 200 else f"⚠️ Erro {resp.status_code}"
    print(f"   Telegram: {status}")


# ═══════════════════════════════════════════════════════════════
# 7. MAIN
# ═══════════════════════════════════════════════════════════════
def main():
    print("\n🚀 PromoVisk – Iniciando busca de promoções...")
    print(f"⏰ {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}\n")

    token          = obter_token()
    ids_existentes = carregar_ids_existentes()
    todas          = []
    ids_vistos     = set()

    for categoria_nome, categoria_emoji, categoria_id in CATEGORIAS:
        print(f"\n🔍 {categoria_emoji} {categoria_nome} (ID: {categoria_id})")
        itens = buscar_por_categoria(token, categoria_id)

        aceitos = 0
        for item in itens:
            if aceitos >= MAX_POR_CAT:
                break
            if item.get("id") in ids_vistos:
                continue

            prod = processar_produto(item, categoria_nome, categoria_emoji, token)
            if prod is None:
                continue

            ids_vistos.add(prod["id"])
            todas.append(prod)
            aceitos += 1

            cupom_info = f" | 🏷️ {prod['cupom_codigo']}" if prod.get("cupom_codigo") else ""
            print(f"   ✔ -{prod['desconto_porcentagem']}% | R${prod['preco_atual']} | {prod['titulo'][:40]}{cupom_info}")

            if prod["id"] not in ids_existentes:
                enviar_telegram(prod)

    todas.sort(key=lambda x: x["desconto_porcentagem"], reverse=True)

    if todas:
        salvar_json(todas)
    else:
        print("\n⚠️ Nenhuma promoção encontrada. JSON não alterado.")

    print(f"\n✅ Concluído! {len(todas)} promoções salvas.\n")


if __name__ == "__main__":
    main()
