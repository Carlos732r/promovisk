"""
PromoVisk – Script de Automação
--------------------------------
O que esse script faz:
1. Busca um token de acesso na API do Mercado Livre
2. Pesquisa produtos em promoção por categoria
3. Filtra apenas os que têm desconto real
4. Salva tudo em data/promocoes.json
5. Envia as novidades para o canal do Telegram
"""

import os
import json
import requests
from datetime import datetime, timezone

# ── Credenciais (vêm das variáveis de ambiente / GitHub Secrets) ──
ML_CLIENT_ID     = os.environ["ML_CLIENT_ID"]
ML_CLIENT_SECRET = os.environ["ML_CLIENT_SECRET"]
TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHANNEL_ID", "")

# ── Configurações ─────────────────────────────────────────────
SITE_ID          = "MLB"          # Brasil
DESCONTO_MINIMO  = 10             # Só mostra se tiver pelo menos 10% de desconto
MAX_POR_BUSCA    = 10             # Quantos produtos buscar por categoria
ARQUIVO_JSON     = "data/promocoes.json"

# Categorias para buscar (nome exibido, emoji, termo de busca na API)
CATEGORIAS = [
    ("Celulares",   "📱", "celular smartphone"),
    ("Tecnologia",  "💻", "notebook laptop"),
    ("Games",       "🎮", "controle console playstation xbox"),
    ("Informática", "🖥️", "ssd mouse teclado gamer"),
    ("TVs e Áudio", "📺", "smart tv 4k"),
    ("Casa",        "🏠", "aspirador robô airfryer"),
    ("Ferramentas", "🔨", "kit ferramentas furadeira"),
    ("Moda",        "👕", "tênis camiseta"),
]


# ═══════════════════════════════════════════════════════════════
# 1. AUTENTICAÇÃO
# ═══════════════════════════════════════════════════════════════
def obter_token():
    """Pega o token de acesso usando Client Credentials."""
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
    print("✅ Token obtido com sucesso!")
    return token


# ═══════════════════════════════════════════════════════════════
# 2. BUSCA DE PRODUTOS
# ═══════════════════════════════════════════════════════════════
def buscar_produtos(token, query, limite=MAX_POR_BUSCA):
    """Busca produtos na API do ML e filtra por desconto manualmente."""
    url    = f"https://api.mercadolibre.com/sites/{SITE_ID}/search"
    # Buscamos mais itens para compensar o filtro manual de desconto
    params = {
        "q":     query,
        "limit": limite * 3,
        "sort":  "relevance",
    }
    headers = {"Authorization": f"Bearer {token}"}
    resp    = requests.get(url, params=params, headers=headers, timeout=15)
    if resp.status_code != 200:
        print(f"  ⚠️  Erro na busca '{query}': {resp.status_code} – {resp.text[:200]}")
        return []
    resultados = resp.json().get("results", [])
    # Filtra só os que têm preco original maior que o atual (desconto real)
    com_desconto = [
        r for r in resultados
        if r.get("original_price") and r["original_price"] > r.get("price", 0)
    ]
    print(f"   {len(resultados)} itens retornados → {len(com_desconto)} com desconto real")
    return com_desconto[:limite]


def processar_produto(item, categoria_nome, categoria_emoji):
    """Transforma o retorno bruto da API no formato do nosso JSON."""
    preco_atual    = item.get("price", 0)
    preco_original = item.get("original_price") or preco_atual

    # Calcula desconto real
    if preco_original <= preco_atual:
        return None  # Sem desconto real, ignora
    desconto = round(((preco_original - preco_atual) / preco_original) * 100)
    if desconto < DESCONTO_MINIMO:
        return None  # Desconto pequeno demais, ignora

    # Parcelas
    parcelas     = item.get("installments", {})
    parcelas_num = parcelas.get("quantity", 0)
    parcelas_val = parcelas.get("amount", 0)

    # Frete grátis
    frete_gratis = item.get("shipping", {}).get("free_shipping", False)

    # Link do produto (vamos trocar pelo link de afiliado depois)
    link = item.get("permalink", "#")

    return {
        "id":                    item.get("id", ""),
        "titulo":                item.get("title", ""),
        "categoria":             categoria_nome,
        "categoria_emoji":       categoria_emoji,
        "imagem":                item.get("thumbnail", "").replace("I.jpg", "O.jpg"),
        "preco_atual":           round(preco_atual, 2),
        "preco_original":        round(preco_original, 2),
        "desconto_porcentagem":  desconto,
        "parcelas_num":          parcelas_num,
        "parcelas_valor":        round(parcelas_val, 2),
        "frete_gratis":          frete_gratis,
        "loja":                  "Mercado Livre",
        "link_afiliado":         link,   # Substituir pelo link de afiliado real
        "destaque":              desconto >= 30,  # Produtos com 30%+ viram destaque
        "adicionado_em":         datetime.now(timezone.utc).isoformat(),
    }


# ═══════════════════════════════════════════════════════════════
# 3. COMPARAR COM JSON ATUAL (para detectar novidades)
# ═══════════════════════════════════════════════════════════════
def carregar_ids_existentes():
    """Carrega os IDs que já estão no JSON para não reenviar no Telegram."""
    try:
        with open(ARQUIVO_JSON, "r", encoding="utf-8-sig") as f:
            dados = json.load(f)
            return {p["id"] for p in dados.get("promocoes", [])}
    except FileNotFoundError:
        return set()
    except Exception:
        print("⚠️  JSON existente não pôde ser lido, começando do zero.")
        return set()


# ═══════════════════════════════════════════════════════════════
# 4. SALVAR JSON
# ═══════════════════════════════════════════════════════════════
def salvar_json(promocoes):
    """Salva a lista de promoções no arquivo JSON do site."""
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
    """Envia uma promoção para o canal do Telegram."""
    if not TELEGRAM_TOKEN or TELEGRAM_TOKEN == "placeholder":
        return  # Bot ainda não configurado, pula

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
        "chat_id":    TELEGRAM_CHAT_ID,
        "text":       texto,
        "parse_mode": "Markdown",
        "disable_web_page_preview": False,
    }
    resp = requests.post(url, data=data, timeout=10)
    if resp.status_code == 200:
        print(f"  ✈️  Telegram: '{produto['titulo'][:40]}...' enviado!")
    else:
        print(f"  ⚠️  Erro Telegram: {resp.status_code} – {resp.text}")


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

    for categoria_nome, categoria_emoji, query in CATEGORIAS:
        print(f"\n🔍 Buscando: {categoria_emoji} {categoria_nome} ({query})")
        itens = buscar_produtos(token, query)
        print(f"   Retornou {len(itens)} itens da API")

        for item in itens:
            prod = processar_produto(item, categoria_nome, categoria_emoji)
            if prod is None:
                continue
            if prod["id"] in ids_vistos:
                continue  # Evita duplicata

            ids_vistos.add(prod["id"])
            todas.append(prod)
            print(f"   ✔ {prod['desconto_porcentagem']}% off – {prod['titulo'][:50]}")

            # Envia no Telegram só se for uma promoção nova
            if prod["id"] not in ids_existentes:
                enviar_telegram(prod)

    # Ordena por maior desconto
    todas.sort(key=lambda x: x["desconto_porcentagem"], reverse=True)

    if todas:
        salvar_json(todas)
    else:
        print("\n⚠️  Nenhuma promoção encontrada. JSON não foi alterado.")

    print(f"\n✅ Concluído! {len(todas)} promoções salvas.\n")


if __name__ == "__main__":
    main()
