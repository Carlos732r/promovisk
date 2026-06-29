"""
PromoVisk – Script de Automação
--------------------------------
Estratégia:
1. Usa token OAuth para autenticar
2. Busca por categoria ID do ML (mais confiável que texto livre)
3. Filtra produtos com desconto real
4. Salva em data/promocoes.json
5. Envia novidades pro Telegram
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
DESCONTO_MINIMO = 5       # % mínimo de desconto
MAX_POR_BUSCA   = 10      # produtos por categoria
ARQUIVO_JSON    = "data/promocoes.json"

# Categorias do ML Brasil com seus IDs oficiais
# Fonte: https://api.mercadolibre.com/sites/MLB/categories
CATEGORIAS = [
    ("Celulares",   "📱", "MLB1055"),   # Celulares e Telefones
    ("Tecnologia",  "💻", "MLB1648"),   # Computadores e Acessórios
    ("Games",       "🎮", "MLB1144"),   # Video Games
    ("TVs e Áudio", "📺", "MLB1000"),   # Eletrônicos, Áudio e Vídeo
    ("Casa",        "🏠", "MLB1574"),   # Eletrodomésticos
    ("Ferramentas", "🔨", "MLB1039"),   # Ferramentas
    ("Moda",        "👕", "MLB1430"),   # Moda e Acessórios
]


# ═══════════════════════════════════════════════════════════════
# 1. AUTENTICAÇÃO
# ═══════════════════════════════════════════════════════════════
def obter_token():
    print("🔑 Obtendo token de acesso...")
    url  = "https://api.mercadolibre.com/oauth/token"
    data = {
        "grant_type":    "client_credentials",
        "client_id":     ML_CLIENT_ID,
        "client_secret": ML_CLIENT_SECRET,
    }
    resp = requests.post(url, data=data, timeout=15)
    resp.raise_for_status()
    token = resp.json()["access_token"]
    print("✅ Token obtido!")
    return token


# ═══════════════════════════════════════════════════════════════
# 2. BUSCA POR CATEGORIA
# ═══════════════════════════════════════════════════════════════
def buscar_por_categoria(token, categoria_id, limite=MAX_POR_BUSCA):
    """Busca produtos em promoção dentro de uma categoria."""
    url    = "https://api.mercadolibre.com/sites/MLB/search"
    params = {
        "category": categoria_id,
        "limit":    limite * 4,
        "sort":     "relevance",
        "discount": "5-100",   # Filtra por desconto de 5% a 100%
    }
    headers = {"Authorization": f"Bearer {token}"}
    resp    = requests.get(url, params=params, headers=headers, timeout=15)
    print(f"   Status: {resp.status_code}")
    if resp.status_code != 200:
        print(f"   Erro: {resp.text[:300]}")
        return []
    resultados = resp.json().get("results", [])
    print(f"   API retornou: {len(resultados)} itens")

    # Debug dos 2 primeiros
    for i, r in enumerate(resultados[:2]):
        print(f"   [{i+1}] R${r.get('price')} | orig=R${r.get('original_price')} | {r.get('title','')[:45]}")

    return resultados


# ═══════════════════════════════════════════════════════════════
# 3. PROCESSAR PRODUTO
# ═══════════════════════════════════════════════════════════════
def processar_produto(item, categoria_nome, categoria_emoji):
    preco_atual    = item.get("price", 0) or 0
    preco_original = item.get("original_price") or preco_atual

    if preco_atual <= 0:
        return None

    # Calcula desconto
    if preco_original > preco_atual:
        desconto = round(((preco_original - preco_atual) / preco_original) * 100)
    else:
        desconto = 0

    if desconto < DESCONTO_MINIMO:
        return None

    parcelas     = item.get("installments") or {}
    parcelas_num = parcelas.get("quantity", 0)
    parcelas_val = parcelas.get("amount", 0)
    frete_gratis = (item.get("shipping") or {}).get("free_shipping", False)

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
        "loja":                 "Mercado Livre",
        "link_afiliado":        item.get("permalink", "#"),
        "destaque":             desconto >= 25,
        "adicionado_em":        datetime.now(timezone.utc).isoformat(),
    }


# ═══════════════════════════════════════════════════════════════
# 4. JSON
# ═══════════════════════════════════════════════════════════════
def carregar_ids_existentes():
    try:
        with open(ARQUIVO_JSON, "r", encoding="utf-8-sig") as f:
            dados = json.load(f)
            return {p["id"] for p in dados.get("promocoes", [])}
    except Exception:
        return set()


def salvar_json(promocoes):
    os.makedirs("data", exist_ok=True)
    dados = {
        "atualizado_em": datetime.now(timezone.utc).isoformat(),
        "total":         len(promocoes),
        "promocoes":     promocoes,
    }
    with open(ARQUIVO_JSON, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)
    print(f"✅ JSON salvo com {len(promocoes)} promoções!")


# ═══════════════════════════════════════════════════════════════
# 5. TELEGRAM
# ═══════════════════════════════════════════════════════════════
def enviar_telegram(produto):
    if not TELEGRAM_TOKEN or TELEGRAM_TOKEN == "placeholder":
        return
    frete = "✅ Frete grátis" if produto["frete_gratis"] else ""
    texto = (
        f"{produto['categoria_emoji']} *{produto['titulo']}*\n\n"
        f"~~R$ {produto['preco_original']:.2f}~~ → "
        f"*R$ {produto['preco_atual']:.2f}*  "
        f"(-{produto['desconto_porcentagem']}%) {frete}\n\n"
        f"🛒 [Ver oferta]({produto['link_afiliado']})\n\n"
        f"_PromoVisk – Promoções que valem a pena_"
    )
    url  = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {
        "chat_id":                  TELEGRAM_CHAT_ID,
        "text":                     texto,
        "parse_mode":               "Markdown",
        "disable_web_page_preview": False,
    }
    resp = requests.post(url, data=data, timeout=10)
    if resp.status_code == 200:
        print(f"  ✈️  Telegram: enviado!")
    else:
        print(f"  ⚠️  Telegram erro: {resp.status_code}")


# ═══════════════════════════════════════════════════════════════
# 6. MAIN
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

        for item in itens:
            prod = processar_produto(item, categoria_nome, categoria_emoji)
            if prod is None:
                continue
            if prod["id"] in ids_vistos:
                continue
            ids_vistos.add(prod["id"])
            todas.append(prod)
            print(f"   ✔ -{prod['desconto_porcentagem']}% | R${prod['preco_atual']} | {prod['titulo'][:45]}")

            if prod["id"] not in ids_existentes:
                enviar_telegram(prod)

    todas.sort(key=lambda x: x["desconto_porcentagem"], reverse=True)

    if todas:
        salvar_json(todas)
    else:
        print("\n⚠️  Nenhuma promoção encontrada. JSON não alterado.")

    print(f"\n✅ Concluído! {len(todas)} promoções salvas.\n")


if __name__ == "__main__":
    main()
