"""Bounded official Steam featured offers; public catalog, no account access."""
import re
from datetime import datetime, timezone
import query_intelligence as qi
import shopping

ENDPOINT = 'https://store.steampowered.com/api/featuredcategories/'


def requested(text):
    value = qi.normalized(text)
    if not re.search(r'\bsteam\b', value) or not re.search(r'\b(promocoes|promocao|ofertas|descontos)\b', value):
        return False
    # Unknown requirements remain with ordinary research. Never replace a named
    # game, genre, price cap, date or requested count by the featured catalog.
    allowed = {'pesquisa','pesquise','pesquisar','busque','buscar','procure','procura','encontre',
               'mostre','mostra','me','por','favor','alguns','algumas','jogos','jogo','em','na','no',
               'da','do','de','steam','promocao','promocoes','ofertas','oferta','descontos','desconto',
               'atuais','atual','agora','hoje','quero','ver','os','as','com','e'}
    return all(token in allowed for token in re.findall(r'\w+', value))


def response(fetch, *, now=None):
    now = now or datetime.now(timezone.utc)
    raw = fetch(ENDPOINT, {'cc':'br','l':'portuguese'})
    if not isinstance(raw, dict):
        raise ValueError('Invalid Steam catalog')
    section = raw.get('specials')
    rows = section.get('items') if isinstance(section, dict) else None
    if not isinstance(rows, list):
        raise ValueError('Missing Steam offers')
    products, sources, seen = [], [], set()
    for item in rows[:100]:
        if not isinstance(item, dict): continue
        app = item.get('id')
        price, original = item.get('final_price'), item.get('original_price')
        expiry = item.get('discount_expiration')
        if (type(app) is not int or app <= 0 or app in seen or item.get('type') != 0
            or item.get('discounted') is not True or item.get('currency') != 'BRL'
            or type(price) is not int or type(original) is not int or not 0 <= price < original
            or not isinstance(item.get('name'), str) or not item['name'].strip()): continue
        if expiry is not None and (type(expiry) not in (int,float) or not now.timestamp() < expiry < 1e12): continue
        seen.add(app)
        url = f'https://store.steampowered.com/app/{app}/'
        def brl(cents): return 'R$ ' + f'{cents / 100:.2f}'.replace('.', ',')
        products.append({'nome':item['name'][:160], 'loja':'Steam · Brasil',
            'preco':price/100, 'preco_texto':brl(price), 'moeda':'BRL',
            'url_item':url, 'verificado_em':now.isoformat(),
            'link_veredito':'parcial', 'link_motivo':'Item declarado no catálogo oficial; página individual não aberta.',
            'specs':{'Preço anterior':brl(original)}, 'disponibilidade':'desconhecida'})
        sources.append({'id':f'S{len(sources)+1}', 'titulo':item['name'][:160], 'url':url})
        if len(products) == 6: break
    if not products:
        return 'A Steam respondeu, mas não encontrei ofertas válidas em reais nos destaques atuais. Não estimei preços.'
    fence = shopping.fence_resultado({'produtos':products,'fontes':sources})
    if not fence: raise ValueError('Invalid Steam cards')
    return ('Encontrei **'+str(len(products))+(' jogo em promoção' if len(products)==1 else ' jogos em promoção')+' nos destaques da Steam**. '
            'Preços declarados pelo catálogo oficial para o Brasil, consultados agora; confirme o valor na página do jogo. '
            'Esta é uma amostra dos destaques, não a lista completa de promoções.'
            '\n\n[Fonte: catálogo público da Steam]('+ENDPOINT+'?cc=br&l=portuguese)'+fence)
