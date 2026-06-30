"""
PromoVisk – Script de Automação v4
------------------------------------
Fonte: RSS do Promobit (promoções reais e verificadas)
Filtro: apenas produtos do Mercado Livre
Afiliado: converte todos os links para o link de afiliado do ML
"""

import os
import json
import re
import time
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from urllib.parse import urlparse, urlencode, urlunparse, parse_qs, urljoin

# ── Credenciais Telegram ──────────────────────────────────────
TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHANNEL_ID", "")

# ── Configurações ─────────────────────────────────────────────
ARQUIVO_JSON     = "data/promocoes.json"
MAX_PRODUTOS     = 60
DESCONTO_MINIMO  = 5

# Seu tracking ID do programa de afiliados do ML
ML_TRACKING_ID   = "nc20240806083958"

# Feeds RSS de promoções — vamos usar múltiplos para ter mais produtos
FEEDS_RSS = [
    ("https://www.promobit.com.br/feed/",          "Promobit"),
    ("https://www.pelando.com.br/api/feed/rss",    "Pelando"),
]

# Domínios do Mercado Livre para filtrar
DOMINIOS_ML = [
    "mercadolivre.com.br",
    "mercadolibre.com",
    "mercadolivre.com",
    "meli.com",
]

# Mapeamento de palavras-chave para categorias
CATEGORIAS_KEYWORDS = {
    "Celulares":   ["celular", "smartphone", "iphone", "samsung galaxy", "motorola", "xiaomi", "fone", "earphone", "airpods", "carregador"],
    "Tecnologia":  ["notebook", "laptop", "macbook", "tablet", "ipad", "smartwatch", "relógio inteligente", "câmera"],
    "Games":       ["playstation", "xbox", "nintendo", "controle", "headset gamer", "mouse gamer", "teclado gamer", "placa de vídeo", "gpu"],
    "Informática": ["ssd", "hd externo", "pendrive", "memória ram", "processador", "monitor", "webcam", "roteador"],
    "TVs e Áudio": ["smart tv", "televisão", "tv ", "soundbar", "caixa de som", "alexa", "echo", "home theater"],
    "Casa":        ["airfryer", "fritadeira", "aspirador", "robô", "panela", "cafeteira", "ferro", "ventilador", "ar condicionado"],
    "Ferramentas": ["furadeira", "parafusadeira", "kit ferramentas", "chave de fenda", "nível", "trena", "marreta"],
    "Moda":        ["tênis", "calçado", "camiseta", "calça", "shorts", "mochila", "bolsa", "óculos"],
}

HEADERS = {
    "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept":          "application/rss+xml, application/xml, text/xml, */*",
    "Accept-Language": "pt-BR,pt;q=0.9",
}


# ═══════════════════════════════════════════════════════════════
# 1. LINK DE AFILIADO
# ═══════════════════════════════════════════════════════════════
def converter_link_afiliado(url):
    """Converte qualquer link do ML para link de afiliado."""
    try:
        # Remove parâmetros de tracking antigos e adiciona o nosso
        parsed = urlparse(url)
        # Garante que é link do ML
        if not any(d in parsed.netloc for d in DOMINIOS_ML):
            return url
        # Monta o link limpo com o tracking ID
        link_afiliado = (
            f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
            f"?matt_tool={ML_TRACKING_ID}"
            f"&matt_word=&matt_source=copy&matt_type=sr"
        )
        return link_afiliado
    except Exception:
        return url


def eh_link_ml(url):
    """Verifica se o link é do Mercado Livre."""
    try:
        netloc = urlparse(url).netloc.lower()
        return any(d in netloc for d in DOMINIOS_ML)
    except Exception:
        return False


# ═══════════════════════════════════════════════════════════════
# 2. DETECTAR CATEGORIA
# ═══════════════════════════════════════════════════════════════
def detectar_categoria(titulo):
    """Detecta a categoria do produto pelo título."""
    titulo_lower = titulo.lower()
    for categoria, keywords in CATEGORIAS_KEYWORDS.items():
        for kw in keywords:
            if kw in titulo_lower:
                return categoria
    return "Tecnologia"  # Padrão

EMOJIS_CATEGORIAS = {
    "Celulares":   "📱",
    "Tecnologia":  "💻",
    "Games":       "🎮",
    "Informática": "🖥️",
    "TVs e Áudio": "📺",
    "Casa":        "🏠",
    "Ferramentas": "🔨",
    "Moda":        "👕",
}


# ═══════════════════════════════════════════════════════════════
# 3. EXTRAIR PREÇOS DO TEXTO
# ═══════════════════════════════════════════════════════════════
def extrair_precos(texto):
    """Extrai preço atual, original e desconto do texto da promoção."""
    preco_atual    = 0.0
    preco_original = 0.0
    desconto       = 0

    # Padrões comuns: "R$ 299,90", "R$299.90", "por R$ 199"
    precos = re.findall(r"R\$\s*(\d{1,6}(?:[.,]\d{3})*(?:[.,]\d{2})?)", texto)
    if precos:
        valores = []
        for p in precos:
            p_limpo = p.replace(".", "").replace(",", ".")
            try:
                valores.append(float(p_limpo))
            except Exception:
                pass
        if valores:
            preco_atual    = min(valores)
            preco_original = max(valores)

    # Padrão de desconto: "39% OFF", "39% de desconto"
    desc_match = re.search(r"(\d+)\s*%\s*(?:off|de desconto|desconto)", texto, re.IGNORECASE)
    if desc_match:
        desconto = int(desc_match.group(1))
    elif preco_original > preco_atual > 0:
        desconto = round(((preco_original - preco_atual) / preco_original) * 100)

    return preco_atual, preco_original, desconto


# ═══════════════════════════════════════════════════════════════
# 4. BUSCAR RSS
# ═══════════════════════════════════════════════════════════════
def buscar_feed_rss(url_feed, nome_fonte):
    """Busca e parseia um feed RSS de promoções."""
    print(f"\n📡 Buscando feed: {nome_fonte}")
    print(f"   URL: {url_feed}")
    try:
        resp = requests.get(url_feed, headers=HEADERS, timeout=20)
        print(f"   Status: {resp.status_code}")
        if resp.status_code != 200:
            print(f"   ⚠️ Erro HTTP")
            return []

        root = ET.fromstring(resp.content)
        # Namespace handling
        ns = {"atom": "http://www.w3.org/2005/Atom"}

        # Tenta pegar itens RSS padrão
        items = root.findall(".//item")
        if not items:
            items = root.findall(".//entry")

        print(f"   Itens encontrados no feed: {len(items)}")
        return items

    except Exception as e:
        print(f"   ⚠️ Erro ao buscar feed: {e}")
        return []


def processar_item_rss(item, nome_fonte):
    """Processa um item do RSS e retorna produto formatado ou None."""
    try:
        # Extrai campos do RSS
        titulo = ""
        link   = ""
        descricao = ""
        imagem = ""

        for tag in ["title"]:
            el = item.find(tag)
            if el is not None and el.text:
                titulo = el.text.strip()

        for tag in ["link"]:
            el = item.find(tag)
            if el is not None:
                link = (el.text or el.get("href", "")).strip()

        for tag in ["description", "summary", "content"]:
            el = item.find(tag)
            if el is not None and el.text:
                descricao = el.text.strip()
                break

        # Tenta pegar imagem
        enclosure = item.find("enclosure")
        if enclosure is not None:
            imagem = enclosure.get("url", "")

        # Se não tem imagem no enclosure, tenta no media:content
        if not imagem:
            for el in item:
                if "image" in el.tag.lower() or "thumbnail" in el.tag.lower():
                    imagem = el.get("url", "") or (el.text or "")
                    if imagem:
                        break

        if not titulo or not link:
            return None

        # Filtra apenas links do Mercado Livre
        # Verifica no link principal e na descrição
        link_ml = ""
        if eh_link_ml(link):
            link_ml = link
        else:
            # Tenta achar link do ML na descrição
            links_desc = re.findall(r'https?://[^\s"<>]+', descricao)
            for l in links_desc:
                if eh_link_ml(l):
                    link_ml = l
                    break

        if not link_ml:
            return None  # Não é do ML, ignora

        # Extrai preços do título + descrição
        texto_completo = f"{titulo} {descricao}"
        preco_atual, preco_original, desconto = extrair_precos(texto_completo)

        if desconto < DESCONTO_MINIMO and preco_atual <= 0:
            return None

        # Se não achou preço mas tem desconto no título, usa valores aproximados
        if preco_atual <= 0:
            preco_atual    = 0.0
            preco_original = 0.0

        # Detecta categoria
        categoria       = detectar_categoria(titulo)
        categoria_emoji = EMOJIS_CATEGORIAS.get(categoria, "🛍️")

        # Extrai ID único do link ML
        id_match = re.search(r"MLB[-\s]?\d+", link_ml)
        item_id  = id_match.group().replace(" ", "").replace("-", "") if id_match else f"rss_{abs(hash(link_ml))}"

        # Converte para link de afiliado
        link_afiliado = converter_link_afiliado(link_ml)

        # Frete grátis mencionado?
        frete_gratis = bool(re.search(r"frete\s*gr[aá]tis|full|entrega\s*gr[aá]tis", texto_completo, re.IGNORECASE))

        # Cupom mencionado?
        cupom_codigo = ""
        cupom_valor  = ""
        cupom_match  = re.search(r"cupom[:\s]+([A-Z0-9]{4,20})", texto_completo, re.IGNORECASE)
        if cupom_match:
            cupom_codigo = cupom_match.group(1).upper()
        desconto_cupom = re.search(r"cupom.*?(\d+%|\d+\s*reais|\d+\s*off)", texto_completo, re.IGNORECASE)
        if desconto_cupom:
            cupom_valor = desconto_cupom.group(1)

        return {
            "id":                   item_id,
            "titulo":               titulo[:120],
            "categoria":            categoria,
            "categoria_emoji":      categoria_emoji,
            "imagem":               imagem,
            "preco_atual":          round(preco_atual, 2),
            "preco_original":       round(preco_original, 2),
            "desconto_porcentagem": desconto,
            "parcelas_num":         0,
            "parcelas_valor":       0.0,
            "frete_gratis":         frete_gratis,
            "frete_tag":            "Frete grátis ⚡ FULL" if frete_gratis else "",
            "cupom_codigo":         cupom_codigo,
            "cupom_valor":          cupom_valor,
            "loja":                 "Mercado Livre",
            "link_afiliado":        link_afiliado,
            "destaque":             desconto >= 25,
            "adicionado_em":        datetime.now(timezone.utc).isoformat(),
        }

    except Exception as e:
        print(f"   ⚠️ Erro ao processar item: {e}")
        return None


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
    print(f"\n✅ JSON salvo com {len(promocoes)} promoções!")


# ═══════════════════════════════════════════════════════════════
# 6. TELEGRAM
# ═══════════════════════════════════════════════════════════════
def enviar_telegram(produto):
    if not TELEGRAM_TOKEN or TELEGRAM_TOKEN == "placeholder":
        return

    preco_linha = ""
    if produto["preco_atual"] > 0:
        if produto["preco_original"] > produto["preco_atual"]:
            preco_linha = (
                f"~~R$ {produto['preco_original']:.2f}~~ → "
                f"*R$ {produto['preco_atual']:.2f}* "
                f"*{produto['desconto_porcentagem']}% OFF*"
            )
        else:
            preco_linha = f"*{produto['desconto_porcentagem']}% OFF*"
    else:
        preco_linha = f"*{produto['desconto_porcentagem']}% OFF*"

    cupom_linha = ""
    if produto.get("cupom_codigo"):
        cupom_linha = f"\n🏷️ Cupom: `{produto['cupom_codigo']}`"
        if produto.get("cupom_valor"):
            cupom_linha += f" ({produto['cupom_valor']} off)"

    frete_linha = f"\n✅ {produto['frete_tag']}" if produto.get("frete_tag") else ""

    texto = (
        f"{produto['categoria_emoji']} *{produto['titulo']}*\n\n"
        f"{preco_linha}"
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
    print(f"   Telegram: {'✈️ Enviado!' if resp.status_code == 200 else f'⚠️ Erro {resp.status_code}'}")


# ═══════════════════════════════════════════════════════════════
# 7. MAIN
# ═══════════════════════════════════════════════════════════════
def main():
    print("\n🚀 PromoVisk – Iniciando busca de promoções...")
    print(f"⏰ {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}\n")

    ids_existentes = carregar_ids_existentes()
    todas          = []
    ids_vistos     = set()
    total_ml       = 0
    total_ignorado = 0

    for url_feed, nome_fonte in FEEDS_RSS:
        items = buscar_feed_rss(url_feed, nome_fonte)

        for item in items:
            prod = processar_item_rss(item, nome_fonte)

            if prod is None:
                total_ignorado += 1
                continue

            if prod["id"] in ids_vistos:
                continue

            ids_vistos.add(prod["id"])
            todas.append(prod)
            total_ml += 1

            cupom_info = f" | 🏷️ {prod['cupom_codigo']}" if prod.get("cupom_codigo") else ""
            frete_info = " | ✅ Frete" if prod["frete_gratis"] else ""
            print(f"   ✔ ML | -{prod['desconto_porcentagem']}% | {prod['titulo'][:45]}{cupom_info}{frete_info}")

            if prod["id"] not in ids_existentes:
                enviar_telegram(prod)

        time.sleep(1)

    print(f"\n📊 Resumo:")
    print(f"   Total ML encontrado: {total_ml}")
    print(f"   Ignorados (não ML):  {total_ignorado}")

    todas.sort(key=lambda x: x["desconto_porcentagem"], reverse=True)
    todas = todas[:MAX_PRODUTOS]

    if todas:
        salvar_json(todas)
    else:
        print("\n⚠️ Nenhuma promoção do ML encontrada.")

    print(f"\n✅ Concluído! {len(todas)} promoções salvas.\n")


if __name__ == "__main__":
    main()
