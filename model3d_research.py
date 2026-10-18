"""V5.6 — geração aproximada de modelos 3D a partir de pesquisa pública.

Fluxo: assunto fora do catálogo → provedores públicos (search_orchestrator com
orçamento curto) → medidas citadas em trechos/títulos → composição procedural
por template paramétrico. Nada de assets de terceiros: apenas texto público é
usado para inferir proporções. Resultado sempre rotulado:

- `aproximado`: medidas confiáveis encontradas nas fontes;
- `conceitual`: fontes consultadas sem medidas confiáveis — forma genérica;
- `None`: rede fora ou nenhuma fonte — limitação honesta, sem geometria.

Medidas em triplo são lidas na ordem das fontes (largura × altura ×
profundidade); nas famílias em que a forma elimina a ambiguidade (disco,
drone) a menor medida vira altura. Nunca é CAD, nunca é o produto oficial.
A busca é injetável (`buscar`) para testes; cache TTL em memória por assunto,
sem gravar nada em disco.
"""
import copy
import re
import threading
import time
import unicodedata

TTL_OK_S = 6 * 3600
TTL_NEGADO_S = 30 * 60
CAPACIDADE = 32
LIMITE_RESULTADOS = 8

_CACHE = {}
_LOCK = threading.Lock()

# Templates paramétricos: famílias de forma defensáveis para o assunto.
_TEMPLATES = (
    ('disco', r'aspirador|robo de limpeza|caixa de som|alto.?falante|smart speaker|prato|antena'),
    ('drone', r'drone|quadricoptero'),
    ('ferramenta', r'furadeira|parafusadeira|serra eletrica|esmerilhadeira|martelete|retifica'),
    ('cilindro', r'liquidificador|batedeira|jarra|lata|bomba|extintor|abajur|luminaria|vaso|cilindro|poste'),
    ('caixa', r'geladeira|refrigerador|fogao|microondas|forno|lavadora|maquina de lavar|secadora|air.?fryer|'
              r'guarda.?roupa|armario|estante|sofa|poltrona|cama|escrivaninha|impressora|scanner|roteador|'
              r'modem|cooler|inversor|televisao|\btv\b'),
)

NOTE = 'Aproximação por composição procedural; sem precisão de engenharia.'
_CHARSET_FONTE = re.compile(r'[^A-Za-z0-9 \-]')
_NUM = r'(\d{1,4}(?:[.,]\d{1,2})?)'
_DIM = re.compile(
    _NUM + r'\s*(?:x|×|por)\s*' + _NUM + r'\s*(?:x|×|por)\s*' + _NUM +
    r'\s*(milimetros|mm|centimetros|cm|metros|m|p(?:o)?l(?:egadas?)?|")(?![a-z])')


def _norm(texto):
    return ''.join(c for c in unicodedata.normalize('NFKD', (texto or '').lower())
                   if not unicodedata.combining(c))


def _limpo(texto, limite):
    return _CHARSET_FONTE.sub('', texto or '').strip()[:limite] or 'objeto'


def limpar_cache():
    with _LOCK:
        _CACHE.clear()


def template(topic_norm):
    for familia, padrao in _TEMPLATES:
        if re.search(padrao, topic_norm or ''):
            return familia
    return None


def _p(objects, key, label, pos, dims, color, desc, related=(), role='functional',
       order=0, kind='cube', rot=(0, 0, 0)):
    objects.append(dict(id=key, kind=kind, label=label, position=list(pos), dimensions=list(dims),
                        color=color, description=desc, related=list(related), role=role,
                        group='', order=order, rotation=list(rot),
                        metadata={'conceptual': True, 'note': NOTE}))


def _t_disco(o):
    _p(o, 'corpo', 'Corpo', [0, 0, 0], [2.0, .55, 2.0], '#3a3f4c',
       'Corpo em disco, formato típico desse tipo de aparelho.', ('topo', 'sensor', 'base'),
       role='structural', order=1, kind='cylinder')
    _p(o, 'topo', 'Aro superior', [0, .3, 0], [1.6, .06, 1.6], '#23252c',
       'Acabamento superior ilustrativo.', ('corpo', 'sensor'), order=2, kind='cylinder')
    _p(o, 'sensor', 'Sensor', [0, .4, .4], [.28, .18, .28], '#14161c',
       'Sensor frontal ilustrativo; sem leitura real.', ('topo',), order=3, kind='cylinder')
    _p(o, 'base', 'Base', [0, -.31, 0], [1.7, .1, 1.7], '#23252c',
       'Base ilustrativa; sem rodas ou movimento reais.', ('corpo',), order=4, kind='cylinder')
    _p(o, 'painel', 'Painel de controle', [.66, .02, .66], [.3, .08, .14], '#67c3d6',
       'Painel ilustrativo de comandos.', ('corpo',), order=5)
    steps = [dict(title='Forma geral', text='Composição em disco, comum nesse tipo de aparelho; '
                  'proporções aproximadas.', selected='corpo'),
             dict(title='Sensores', text='O sensor frontal é apenas ilustrativo.', selected='sensor'),
             dict(title='Limites', text='A forma vem de referências públicas; não é o produto oficial.',
                  selected='painel')]
    return steps, [2.0, .55, 2.0]


def _t_drone(o):
    _p(o, 'corpo', 'Corpo', [0, 0, 0], [1.1, .22, .8], '#3a3f4c',
       'Corpo central com eletrônica conceitual.', ('braco_1', 'braco_2', 'braco_3', 'braco_4', 'camera'),
       role='structural', order=1)
    for i, (x, z, giro) in enumerate(((0.55, 0.45, 45), (-0.55, 0.45, -45),
                                      (0.55, -0.45, -45), (-0.55, -0.45, 45)), start=1):
        _p(o, f'braco_{i}', f'Braço {i}', [x, 0, z], [.75, .06, .1], '#23252c',
           'Braço estrutural do rotor.', ('corpo', f'rotor_{i}'), role='structural',
           order=1 + i, rot=(0, giro, 0))
        _p(o, f'rotor_{i}', f'Rotor {i}', [x * 1.7, .06, z * 1.7], [.5, .04, .5], '#14161c',
           'Rotor ilustrativo; sem rotação real.', (f'braco_{i}',), order=5 + i, kind='cylinder')
    _p(o, 'camera', 'Câmera', [0, -.18, .2], [.3, .12, .3], '#14161c',
       'Câmera ilustrativa abaixo do corpo.', ('corpo',), order=10)
    steps = [dict(title='Estrutura', text='Corpo central com quatro braços em X.', selected='corpo'),
             dict(title='Rotores', text='Os rotores são discos ilustrativos, sem movimento real.',
                  selected='rotor_2'),
             dict(title='Câmera', text='A câmera é apenas conceitual.', selected='camera')]
    return steps, [1.1, .22, .8]


def _t_ferramenta(o):
    _p(o, 'corpo', 'Corpo', [0, .1, 0], [.75, .35, .5], '#3a3f4c',
       'Corpo principal da ferramenta.', ('mandril', 'punho'), role='structural', order=1)
    _p(o, 'mandril', 'Mandril', [.5, .1, 0], [.22, .22, .22], '#9aa0ae',
       'Mandril ilustrativo para broca/acessório.', ('corpo',), order=2, kind='cylinder', rot=(0, 0, 90))
    _p(o, 'punho', 'Punho', [-.15, -.35, 0], [.32, .5, .34], '#23252c',
       'Empunhadura ilustrativa.', ('corpo', 'gatilho'), role='structural', order=3)
    _p(o, 'gatilho', 'Gatilho', [-.02, -.12, .22], [.12, .18, .1], '#14161c',
       'Acionador ilustrativo.', ('punho',), order=4)
    steps = [dict(title='Corpo', text='Forma geral de ferramenta elétrica; aproximada.', selected='corpo'),
             dict(title='Mandril', text='O mandril é um cilindro ilustrativo.', selected='mandril'),
             dict(title='Empunhadura', text='Punho e gatilho são conceituais.', selected='punho')]
    return steps, [.75, .35, .5]


def _t_cilindro(o):
    _p(o, 'corpo', 'Corpo', [0, 0, 0], [1.2, 2.0, 1.2], '#4a5568',
       'Corpo cilíndrico, formato comum desse tipo de objeto.', ('tampa', 'base', 'botao'),
       role='structural', order=1, kind='cylinder')
    _p(o, 'tampa', 'Tampa', [0, 1.05, 0], [1.02, .16, 1.02], '#3a3f4c',
       'Tampa ilustrativa, sem abertura real.', ('corpo',), order=2, kind='cylinder')
    _p(o, 'base', 'Base', [0, -1.1, 0], [1.05, .22, 1.05], '#23252c',
       'Base de apoio ilustrativa.', ('corpo',), role='structural', order=3, kind='cylinder')
    _p(o, 'botao', 'Controle', [0, .35, .62], [.22, .08, .08], '#67c3d6',
       'Controle frontal ilustrativo.', ('corpo',), order=4)
    steps = [dict(title='Corpo', text='Corpo cilíndrico aproximado.', selected='corpo'),
             dict(title='Tampa', text='A tampa é apenas ilustrativa.', selected='tampa'),
             dict(title='Base', text='A base é estrutural e conceitual.', selected='base')]
    return steps, [1.2, 2.0, 1.2]


def _t_caixa(o):
    _p(o, 'corpo', 'Corpo', [0, 0, 0], [2.0, 1.6, 1.4], '#4a5568',
       'Corpo em caixa, formato comum para esse tipo de objeto.', ('frente', 'topo', 'pe_esq', 'pe_dir'),
       role='structural', order=1)
    _p(o, 'frente', 'Frente', [0, 0, .72], [1.7, 1.2, .06], '#3a3f4c',
       'Frente/painel ilustrativo.', ('corpo', 'puxador'), order=2)
    _p(o, 'puxador', 'Puxador', [0, .1, .78], [.5, .08, .06], '#9aa0ae',
       'Puxador ilustrativo.', ('frente',), order=3)
    _p(o, 'topo', 'Topo', [0, .83, 0], [1.6, .06, 1.0], '#5b6480',
       'Acabamento superior.', ('corpo',), order=4)
    _p(o, 'pe_esq', 'Pé esquerdo', [-.8, -.85, .55], [.16, .12, .16], '#23252c',
       'Apoio ilustrativo.', ('corpo',), order=5, kind='cylinder')
    _p(o, 'pe_dir', 'Pé direito', [.8, -.85, .55], [.16, .12, .16], '#23252c',
       'Apoio ilustrativo.', ('corpo',), order=6, kind='cylinder')
    steps = [dict(title='Forma geral', text='Volume em caixa, aproximado por proporções públicas.',
                  selected='corpo'),
             dict(title='Frente', text='A frente e o puxador são ilustrativos.', selected='frente'),
             dict(title='Apoios', text='Os pés são estruturais e conceituais.', selected='pe_esq')]
    return steps, [2.0, 1.6, 1.4]


_FAMILIAS = {'disco': _t_disco, 'drone': _t_drone, 'ferramenta': _t_ferramenta,
             'cilindro': _t_cilindro, 'caixa': _t_caixa}


def _converter(valor, unidade):
    numero = float(valor.replace(',', '.'))
    if unidade.startswith('milim') or unidade == 'mm':
        return numero / 10
    if unidade.startswith('centim') or unidade == 'cm':
        return numero
    if unidade.startswith('m'):
        return numero * 100
    return numero * 2.54


def _medidas(texto):
    """Primeira tripla válida (largura, altura, profundidade) convertida para cm."""
    for achado in _DIM.finditer(texto or ''):
        a, b, c = (_converter(achado[i], achado[4]) for i in (1, 2, 3))
        valores = (a, b, c)
        if not all(1.0 <= v <= 500.0 for v in valores):
            continue
        if max(valores) / max(min(valores), .1) > 100:
            continue
        return valores
    return None


def _escala(objects, canon, alvo):
    """Aplica as proporções encontradas sobre o template (por eixo, limitado)."""
    fatores = []
    for i in range(3):
        fator = alvo[i] / canon[i] if canon[i] else 1.0
        fatores.append(max(.2, min(12.0, fator)))
    for item in objects:
        item['position'] = [round(max(-2.9, min(2.9, item['position'][i] * fatores[i])), 3)
                            for i in range(3)]
        item['dimensions'] = [round(max(.015, min(3.0, item['dimensions'][i] * fatores[i])), 3)
                              for i in range(3)]


def _dominios(achados):
    from urllib.parse import urlparse
    vistos = []
    for a in achados:
        host = urlparse((a.get('url') or '').strip()).netloc.lower().removeprefix('www.')
        if host and host not in vistos:
            vistos.append(host)
        if len(vistos) >= 3:
            break
    return vistos


def _buscar_padrao(consulta, limite):
    import research
    achados, _info = research._buscar_orquestrado(
        consulta, max_resultados=limite, timeout=6.0,
        orcamento={'max_consultas': 1, 'max_provedores': 3, 'timeout_total': 7.0,
                   'min_resultados': 2, 'max_por_provedor': 8})
    return [dict(titulo=a.get('titulo', ''), url=a.get('url', ''), trecho=a.get('trecho', ''))
            for a in achados]


def gerar(topic, buscar=None):
    """Cena aproximada/conceitual para o assunto, ou None (limitação honesta).

    `buscar(consulta, limite) -> [{'titulo','url','trecho'}]` é injetável nos
    testes; em produção usa o orquestrador real com orçamento curto.
    """
    import model3d
    t = re.sub(r'\s+', ' ', _norm(topic)).strip()
    if not t:
        return None
    familia = template(t)
    agora = time.monotonic()
    with _LOCK:
        registro = _CACHE.get(t)
        if registro and registro[0] > agora:
            return copy.deepcopy(registro[1])
    resultado = None
    if familia:
        buscar_fn = buscar or _buscar_padrao
        try:
            achados = buscar_fn(f'{t} dimensões medidas', LIMITE_RESULTADOS) or []
        except Exception:
            achados = None
        if achados:
            texto = ' '.join((a.get('titulo', '') or '') + ' ' + (a.get('trecho', '') or '')
                             for a in achados[:LIMITE_RESULTADOS])[:8000]
            medidas = _medidas(texto)
            if familia in ('disco', 'drone') and medidas:
                # Listagens vêm tipicamente como L×P×A: a menor medida é a altura.
                menor, meio, maior = sorted(medidas)
                medidas = (maior, menor, meio)
            doms = _dominios(achados)
            objects = []
            steps, canon = _FAMILIAS[familia](objects)
            titulo_limpo = _limpo(topic, 60)
            if medidas:
                alvo = [m * (2.4 / max(medidas)) for m in medidas]
                _escala(objects, canon, alvo)
                medida_txt = ' × '.join(f'{m:g}'.replace('.', ',') for m in medidas) + ' cm'
                fonte = ', '.join(doms) if doms else 'fontes públicas'
                descricao = (f'Modelo aproximado e educativo de {titulo_limpo}: composição procedural inspirada '
                             f'em referências públicas ({fonte}); proporções a partir de medidas citadas nas '
                             f'fontes ({medida_txt}). Não é CAD, não é o produto oficial e pode conter '
                             f'imprecisões.')
                origem = 'Aproximado por referências públicas — ' + (fonte[:120])
                precision = 'aproximado'
            else:
                descricao = (f'Modelo conceitual e educativo de {titulo_limpo}: as fontes públicas consultadas '
                             f'não confirmaram medidas confiáveis, então a forma é uma composição procedural '
                             f'genérica. Não é CAD nem o produto oficial.')
                origem = 'Modelo conceitual educativo — ' + titulo_limpo[:100]
                precision = 'conceitual'
            cena = dict(id='aprox-' + (re.sub(r'[^a-z0-9]+', '-', t)[:24].strip('-') or 'objeto'),
                        version=1, title=titulo_limpo + ' (aproximação educativa)', description=descricao,
                        education='device', precision=precision, source=origem, objects=objects,
                        steps=steps, rotation=[18, 26, 0], details=True)
            try:
                model3d.validate(cena)
            except ValueError:
                cena = None
            resultado = cena
    with _LOCK:
        if len(_CACHE) >= CAPACIDADE:
            _CACHE.pop(next(iter(_CACHE)))
        _CACHE[t] = (agora + (TTL_OK_S if resultado else TTL_NEGADO_S), resultado)
    return copy.deepcopy(resultado)
