"""Observed offers from a read product page, with explicit field provenance."""
import hashlib
import json
import re
from datetime import date, datetime, timezone

import shopping
import web_extract


def _encoded(fields):
    return json.dumps(fields, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def extract(page, url, title, query):
    # Reuse the same link, challenge, removed-item and product-page checks as
    # shopping. The HTML is already downloaded; this callback performs no I/O.
    products = shopping._recuperar_ofertas(url, title,
        baixar_fn=lambda _: {'texto': page, 'final': url}, consulta=query)
    eligible, _ = shopping.aplicar_filtros(products, shopping.extrair_criterios(query))
    for product in eligible[:4]:
        if (not product.get('preco_confirmado') or product.get('item_de_listagem')
                or product.get('link_veredito') not in ('verificado', 'parcial')
                or not shopping._mesmo_recurso(product.get('url_item', ''), url)):
            continue
        # Require explicit currency and a single exact offer, not an aggregate
        # price or a value/default inferred from the merchant's country.
        nodes = web_extract._ld_por_tipo(web_extract._ldjson_objs(page), {'product'}, teto=8)
        for node in nodes:
            if shopping._limpa(node.get('name'), 160) != product.get('nome'):
                continue
            declared = node.get('url')
            if declared and (not isinstance(declared, str) or not shopping._mesmo_recurso(declared, url)):
                continue
            offers = node.get('offers')
            offers = offers if isinstance(offers, list) else [offers]
            if len(offers) != 1 or not isinstance(offers[0], dict):
                continue
            offer = offers[0]
            if offer.get('@type') != 'Offer' or not isinstance(offer.get('priceCurrency'), str):
                continue
            currency = offer['priceCurrency'].strip().upper()
            if not re.fullmatch(r'[A-Z]{3}', currency):
                continue
            if not re.fullmatch(r'\d+(?:[.,]\d+)*', str(offer.get('price', '')).strip()):
                continue
            price = shopping.normalizar_preco(offer.get('price'), currency)
            if not price or price[0] <= 0 or price[0] != product.get('preco') or price[1] != product.get('moeda'):
                continue
            declared = offer.get('url')
            if declared and (not isinstance(declared, str) or not shopping._mesmo_recurso(declared, url)):
                continue
            valid_until = offer.get('priceValidUntil')
            if valid_until:
                try:
                    if date.fromisoformat(str(valid_until)[:10]) < datetime.now(timezone.utc).date():
                        continue
                except ValueError:
                    continue
            fields = {'name': product['nome'], 'price': str(offer['price']),
                      'priceCurrency': currency, 'availability': str(offer.get('availability') or '')[:100],
                      'priceValidUntil': str(valid_until or '')[:32]}
            return {'fields': fields, 'price': price[0], 'currency': price[1],
                    'availability': product.get('disponibilidade', 'desconhecida'),
                    'url': url, 'observed_at': product['verificado_em'],
                    'source': 'jsonld_product_offer', 'field_path': 'Product.offers',
                    'sha256': hashlib.sha256(_encoded(fields).encode()).hexdigest()}
    return None


def valid(offer, url):
    if not isinstance(offer, dict) or offer.get('source') != 'jsonld_product_offer':
        return False
    fields = offer.get('fields')
    if not isinstance(fields, dict) or set(fields) != {'name', 'price', 'priceCurrency', 'availability', 'priceValidUntil'}:
        return False
    if (not all(isinstance(v, str) for v in fields.values()) or len(_encoded(fields)) > 800
            or offer.get('sha256') != hashlib.sha256(_encoded(fields).encode()).hexdigest()
            or not shopping._mesmo_recurso(str(offer.get('url') or ''), url)):
        return False
    if (not re.fullmatch(r'\d+(?:[.,]\d+)*', fields['price'].strip())
            or not re.fullmatch(r'[A-Z]{3}', fields['priceCurrency'])
            or offer.get('field_path') != 'Product.offers'):
        return False
    observed = offer.get('observed_at')
    if not isinstance(observed, str) or len(observed) > 40:
        return False
    try:
        if datetime.fromisoformat(observed.replace('Z', '+00:00')).utcoffset() is None:
            return False
    except ValueError:
        return False
    price = shopping.normalizar_preco(fields['price'], fields['priceCurrency'])
    return bool(price and price[0] > 0 and price == (offer.get('price'), offer.get('currency'))
                and shopping._disp_normalizada(fields['availability']) == offer.get('availability'))


def availability_label(offer):
    return {'em_estoque': 'em estoque', 'sem_estoque': 'sem estoque',
            'estoque_limitado': 'estoque limitado',
            'pre_venda': 'pré-venda'}.get(offer.get('availability'), 'não informada')


def summary(offer, url):
    """Compact presentation; full fields and timestamp remain in provenance."""
    if not valid(offer, url):
        return ''
    observed = datetime.fromisoformat(offer['observed_at'].replace('Z', '+00:00')).astimezone(timezone.utc)
    return (f"Preço observado: {shopping.formatar_preco(offer['price'], offer['currency'])}. "
            f"Disponibilidade declarada: {availability_label(offer)}. "
            f"Consultado em {observed:%d/%m/%Y %H:%M} UTC.")


def text(offer, url):
    """Human-readable normalization of the stored fields, never a DOM quotation."""
    if not valid(offer, url):
        return ''
    observed = datetime.fromisoformat(offer['observed_at'].replace('Z', '+00:00')).astimezone(timezone.utc)
    return (f"Dados estruturados JSON-LD: {offer['fields']['name']}. "
            f"Preço observado: {shopping.formatar_preco(offer['price'], offer['currency'])}. "
            f"Disponibilidade declarada: {availability_label(offer)}. "
            f"Leitura em UTC: {observed:%d/%m/%Y}; registro {offer['observed_at']}.")
