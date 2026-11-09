"""V5.6 — catálogo local de dispositivos aproximados.

Reconstruções educativas por primitivas (cubo, esfera, cilindro, pirâmide),
criadas pelo próprio projeto. Nenhum asset, modelo ou imagem de terceiros é
baixado ou embutido; referências públicas servem apenas para inferir
proporções e elementos visuais. Medidas e encaixes são ilustrativos: não são
CAD, não representam compatibilidade e não têm precisão de engenharia.
"""
import re
import unicodedata

NOTE = 'Reconstrução educativa original; medidas ilustrativas.'
TITULO_PREFIXO = 'Catálogo local V5.6 — '

# A ordem importa: apelidos específicos antes dos genéricos.
_ALIASES = (
    ('turbina_aviao', r'turbina|turbofan|motor a jato|jet engine|turbina de aviao'),
    ('smartphone_desmontado', r'smartphone desmontado|celular desmontado|pecas do celular|pecas do smartphone'),
    ('carro_eletrico', r'carro eletrico|veiculo eletrico|chassi eletrico|bateria de carro'),
    ('drone_quadricoptero', r'drone|quadricoptero|fpv'),
    ('coracao_humano', r'coracao|coracao humano|anatomia do coracao'),
    ('suporte_celular', r'suporte (?:de |para )?(?:celular|telefone)'),
    ('motor_v8', r'\bv8\b|motor v8'),
    ('xbox', r'xbox'),
    ('playstation', r'playstation|\bps ?[2-5]\b'),
    ('controle', r'controle|gamepad|joystick'),
    ('celular', r'celular|smartphone|\biphone\b|\bgalaxy\b'),
    ('placa_mae', r'placa[- ]?mae|motherboard'),
    ('gabinete', r'gabinete|\btorre\b'),
    ('monitor', r'\bmonitor\b'),
    ('teclado', r'teclado'),
    ('headset', r'headset|fone de ouvido'),
    ('mesa', r'\bmesa\b|escrivaninha|bancada'),
    ('console', r'console|videogame|video game'),
)


def _norm(texto):
    return ''.join(c for c in unicodedata.normalize('NFKD', (texto or '').lower())
                   if not unicodedata.combining(c))


def resolver(texto_norm):
    """Apelido de dispositivo no texto já normalizado, ou None."""
    if re.search(r'\bxbox\b', texto_norm) and not re.search(r'\bxbox series s\b', texto_norm):
        return 'console'  # Não representar Series X/One/360 como Series S.
    for chave, padrao in _ALIASES:
        if re.search(padrao, texto_norm):
            return chave
    return None


def assunto(texto_norm):
    """Recorte curto do objeto pedido, sem verbos, artigos e ruído de 3D."""
    s = re.sub(r'\b(3d|tridimensional|girando)\b', ' ', texto_norm)
    s = re.sub(r'\b(me|por favor|pra mim|para mim)\b', ' ', s)
    s = re.sub(r'\b(mostre|mostra|exiba|exibe|veja|ver|crie|cria|faca|faz|gerar|gere|monte|montar|'
               r'construa|construir|desenhe|desenhar|renderize|renderizar|modele|modelar|quero|queria)\b', ' ', s)
    s = re.sub(r'\b(um|uma|o|a|os|as|de|do|da|dos|das|em|no|na)\b', ' ', s)
    s = re.sub(r'\b(modelo|representacao|versao|imagem|objeto)\b', ' ', s)
    return re.sub(r'\s+', ' ', s).strip(' .!,?')[:40]


def _peca(objects, key, label, pos, dims, color, desc, related=(), role='functional',
          group='', order=0, kind='cube', rot=(0, 0, 0),
          roughness=None, metalness=None, opacity=None, transparent=None,
          wireframe=None, emissive=None, explodeVector=None):
    p = dict(id=key, kind=kind, label=label, position=list(pos), dimensions=list(dims),
             color=color, description=desc, related=list(related), role=role, group=group,
             order=order, rotation=list(rot), metadata={'conceptual': True, 'note': NOTE})
    if roughness is not None:
        p['roughness'] = roughness
    if metalness is not None:
        p['metalness'] = metalness
    if opacity is not None:
        p['opacity'] = opacity
    if transparent is not None:
        p['transparent'] = transparent
    if wireframe is not None:
        p['wireframe'] = wireframe
    if emissive is not None:
        p['emissive'] = emissive
    if explodeVector is not None:
        p['explodeVector'] = list(explodeVector)
    objects.append(p)


def _cena(chave, titulo, descricao, objects, steps, fonte, education='device', precision='aproximado'):
    return dict(id='dev-' + chave, version=1, title=titulo, description=descricao,
                education=education, precision=precision,
                source=TITULO_PREFIXO + fonte, objects=objects, steps=steps,
                rotation=[18, 26, 0], details=True)


def _console_compacto():
    o = []
    _peca(o, 'corpo', 'Corpo', [0, 0, 0], [1.95, 1.15, .95], '#e9eaef',
          'Corpo branco compacto; proporções aproximadas de um console atual.', ('grade_topo', 'usb', 'botao'),
          role='structural', group='external', order=1)
    _peca(o, 'grade_topo', 'Grade superior', [0, .60, 0], [.72, .05, .72], '#23252c',
          'Saída de ar circular superior, o elemento visual mais marcante; desenho aproximado.',
          ('corpo', 'ventoinha'), group='external', order=2, kind='cylinder')
    _peca(o, 'grade_frente', 'Grade frontal', [0, 0, .49], [.5, .05, .5], '#23252c',
          'Segunda saída de ar, ilustrativa.', ('corpo',), group='external', order=3,
          kind='cylinder', rot=(90, 0, 0))
    _peca(o, 'usb', 'Porta USB', [-.7, .25, .48], [.16, .09, .05], '#23252c',
          'Porta frontal simplificada; posição não é oficial.', ('corpo',), group='external', order=4)
    _peca(o, 'botao', 'Botão de energia', [.72, .59, .2], [.14, .02, .1], '#c9ccd6',
          'Botão e pareamento são representados por uma peça única.', ('corpo',), group='external', order=5)
    _peca(o, 'pe_esq', 'Pé esquerdo', [-.75, -.6, .32], [.12, .06, .12], '#c9ccd6',
          'Apoio ilustrativo.', ('corpo',), group='external', order=6)
    _peca(o, 'pe_dir', 'Pé direito', [.75, -.6, .32], [.12, .06, .12], '#c9ccd6',
          'Apoio ilustrativo.', ('corpo',), group='external', order=7)
    _peca(o, 'ventoinha', 'Ventoinha', [0, -.15, .28], [.62, .06, .62], '#3b4152',
          'Ventoinha interna ilustrativa, ligada à grade superior.', ('placa', 'grade_topo'),
          group='internal', order=8, kind='cylinder', rot=(90, 0, 0))
    _peca(o, 'placa', 'Placa principal', [0, -.22, 0], [1.5, .06, .75], '#2f7d5c',
          'Placa-mãe compacta conceitual.', ('ventoinha', 'ssd', 'fonte_modulo'),
          group='internal', order=9)
    _peca(o, 'ssd', 'Armazenamento', [-.35, -.1, .25], [.5, .05, .16], '#3a3f4c',
          'Módulo de armazenamento ilustrativo.', ('placa',), group='internal', order=10)
    _peca(o, 'fonte_modulo', 'Fonte', [.45, .2, -.2], [.7, .12, .5], '#4a5060',
          'Módulo de alimentação ilustrativo.', ('placa',), group='internal', order=11)
    steps = [dict(title='Corpo', text='O corpo branco usa proporções aproximadas de um console compacto.',
                  selected='corpo'),
             dict(title='Ventilação', text='A saída circular de ar é um desenho ilustrativo.',
                  selected='grade_topo'),
             dict(title='Portas e energia', text='Portas e botão são simplificados e não indicam posições oficiais.',
                  selected='usb'),
             dict(title='Interior', text='No modo separado, observe placa, ventoinha e fonte conceituais.',
                  selected='placa', exploded=True)]
    return _cena('console-branco', 'Console compacto branco (aproximação do Xbox Series S)',
                 'Reconstrução educativa por primitivas, inspirada em referências públicas do Xbox Series S. '
                 'Não é modelo oficial nem CAD; cores e medidas são aproximadas.',
                 o, steps, 'console compacto branco')


def _console_escuro():
    o = []
    _peca(o, 'corpo', 'Corpo', [0, 0, 0], [1.9, 1.05, .8], '#262a33',
          'Corpo escuro de console; proporções aproximadas.', ('slot', 'usb', 'botao', 'grade'),
          role='structural', group='external', order=1)
    _peca(o, 'slot', 'Entrada de disco', [0, .32, .41], [1.05, .05, .07], '#14161c',
          'Entrada de mídia ilustrativa.', ('corpo',), group='external', order=2)
    _peca(o, 'grade', 'Grade de ventilação', [.6, -.25, .41], [.5, .3, .04], '#23252c',
          'Grade de ventilação ilustrativa.', ('corpo', 'ventoinha'), group='external', order=3)
    _peca(o, 'usb', 'Portas USB', [-.6, .3, .41], [.3, .08, .05], '#23252c',
          'Portas frontais simplificadas.', ('corpo',), group='external', order=4)
    _peca(o, 'botao', 'Botão de energia', [-.75, -.32, .41], [.12, .06, .04], '#9aa0ae',
          'Botão ilustrativo.', ('corpo',), group='external', order=5)
    _peca(o, 'pe_esq', 'Pé esquerdo', [-.7, -.55, .24], [.16, .06, .16], '#14161c',
          'Apoio ilustrativo.', ('corpo',), group='external', order=6)
    _peca(o, 'pe_dir', 'Pé direito', [.7, -.55, .24], [.16, .06, .16], '#14161c',
          'Apoio ilustrativo.', ('corpo',), group='external', order=7)
    _peca(o, 'ventoinha', 'Ventoinha', [.55, -.22, .2], [.5, .06, .5], '#3b4152',
          'Ventoinha interna ilustrativa.', ('grade', 'placa'), group='internal', order=8,
          kind='cylinder', rot=(90, 0, 0))
    _peca(o, 'placa', 'Placa principal', [0, -.22, 0], [1.45, .06, .65], '#2f7d5c',
          'Placa conceitual.', ('ventoinha', 'drive'), group='internal', order=9)
    _peca(o, 'drive', 'Leitor de mídia', [-.3, -.12, .1], [.7, .1, .5], '#3a3f4c',
          'Leitor interno ilustrativo.', ('placa', 'slot'), group='internal', order=10)
    steps = [dict(title='Corpo', text='Proporções aproximadas de um console escuro.', selected='corpo'),
             dict(title='Mídia', text='A entrada de disco é ilustrativa.', selected='slot'),
             dict(title='Ventilação', text='A grade traseira ajuda a dissipar calor; desenho aproximado.',
                  selected='grade'),
             dict(title='Interior', text='No modo separado, observe o leitor e a placa conceituais.',
                  selected='drive', exploded=True)]
    return _cena('console-escuro', 'Console escuro (aproximação de família PlayStation)',
                 'Reconstrução educativa aproximada por primitivas, inspirada em consoles escuros de referência '
                 'pública; sem marca específica e sem CAD.',
                 o, steps, 'console escuro')


def _console_generico():
    o = []
    _peca(o, 'corpo', 'Corpo', [0, 0, 0], [1.9, 1.1, .85], '#8a90a0',
          'Corpo neutro de console genérico; medidas ilustrativas.', ('grade', 'usb', 'botao'),
          role='structural', group='external', order=1)
    _peca(o, 'grade', 'Grade frontal', [0, 0, .44], [1.1, .5, .04], '#23252c',
          'Painel de ventilação ilustrativo.', ('corpo', 'ventoinha'), group='external', order=2)
    _peca(o, 'usb', 'Portas USB', [.7, .3, .44], [.24, .08, .04], '#23252c',
          'Portas simplificadas.', ('corpo',), group='external', order=3)
    _peca(o, 'botao', 'Botão de energia', [.7, -.3, .44], [.1, .06, .04], '#c9ccd6',
          'Botão ilustrativo.', ('corpo',), group='external', order=4)
    _peca(o, 'ventoinha', 'Ventoinha', [0, 0, .3], [.55, .06, .55], '#3b4152',
          'Ventoinha interna ilustrativa.', ('grade', 'placa'), group='internal', order=5,
          kind='cylinder', rot=(90, 0, 0))
    _peca(o, 'placa', 'Placa principal', [0, -.25, 0], [1.4, .06, .7], '#2f7d5c',
          'Placa conceitual.', ('ventoinha', 'ssd'), group='internal', order=6)
    _peca(o, 'ssd', 'Armazenamento', [.35, -.12, .2], [.45, .05, .14], '#3a3f4c',
          'Módulo ilustrativo.', ('placa',), group='internal', order=7)
    steps = [dict(title='Corpo', text='Console genérico com formas neutras.', selected='corpo'),
             dict(title='Ventilação', text='A grade frontal é ilustrativa.', selected='grade'),
             dict(title='Interior', text='Separe as peças para ver os módulos conceituais.',
                  selected='placa', exploded=True)]
    return _cena('console-generico', 'Console ilustrativo (genérico)',
                 'Console genérico educativo aproximado; sem marca e sem medidas oficiais.', o, steps,
                 'console genérico')


def _celular():
    o = []
    _peca(o, 'corpo', 'Corpo', [0, 0, 0], [.82, 1.62, .09], '#1c1e24',
          'Corpo fino com proporções típicas de celular moderno; aproximado.',
          ('tela', 'camera_modulo', 'bateria'), role='structural', group='external', order=1)
    _peca(o, 'tela', 'Tela', [0, .02, .046], [.72, 1.5, .02], '#5f8fe0',
          'Tela ilustrativa, sem interface real.', ('corpo',), group='external', order=2)
    _peca(o, 'camera_modulo', 'Módulo de câmeras', [-.24, .62, -.062], [.28, .3, .04], '#2a2e38',
          'Conjunto de câmeras traseiras, desenho aproximado.', ('corpo', 'lente_1', 'lente_2'),
          group='external', order=3)
    _peca(o, 'lente_1', 'Câmera 1', [-.29, .68, -.085], [.09, .03, .09], '#0f1116',
          'Lente ilustrativa.', ('camera_modulo',), group='external', order=4,
          kind='cylinder', rot=(90, 0, 0))
    _peca(o, 'lente_2', 'Câmera 2', [-.19, .56, -.085], [.09, .03, .09], '#0f1116',
          'Lente ilustrativa.', ('camera_modulo',), group='external', order=5,
          kind='cylinder', rot=(90, 0, 0))
    _peca(o, 'botao_lateral', 'Botão lateral', [.415, .28, 0], [.03, .14, .05], '#3a3f4c',
          'Botão de volume/power simplificado.', ('corpo',), group='external', order=6)
    _peca(o, 'porta', 'Porta de carga', [0, -.82, 0], [.2, .05, .05], '#14161c',
          'Conector de carga ilustrativo.', ('corpo', 'bateria'), group='external', order=7)
    _peca(o, 'bateria', 'Bateria', [0, -.1, -.01], [.6, 1.0, .05], '#3f9c74',
          'Bateria conceitual.', ('placa', 'porta'), group='internal', order=8)
    _peca(o, 'placa', 'Placa', [0, .42, -.01], [.6, .5, .04], '#2f7d5c',
          'Placa conceitual.', ('bateria', 'camera_modulo'), group='internal', order=9)
    steps = [dict(title='Corpo', text='Proporções aproximadas de um celular moderno.', selected='corpo'),
             dict(title='Tela', text='A tela é uma área ilustrativa, sem sistema.', selected='tela'),
             dict(title='Câmeras', text='O módulo de câmeras é um desenho aproximado.', selected='camera_modulo'),
             dict(title='Interior', text='Separe as peças para ver bateria e placa conceituais.',
                  selected='bateria', exploded=True)]
    return _cena('celular', 'Celular ilustrativo (aproximação genérica)',
                 'Representação aproximada e educativa de um celular moderno; sem marca e sem medidas oficiais.',
                 o, steps, 'celular aproximado')


def _controle():
    o = []
    _peca(o, 'corpo', 'Corpo', [0, 0, 0], [1.05, .34, .5], '#2f333e',
          'Corpo central do controle; proporções aproximadas.', ('grip_esq', 'grip_dir', 'analogico_esq'),
          role='structural', group='external', order=1)
    _peca(o, 'grip_esq', 'Empunhadura esquerda', [-.62, -.18, 0], [.34, .4, .42], '#2f333e',
          'Empunhadura ilustrativa.', ('corpo',), group='external', order=2, rot=(0, 0, -18))
    _peca(o, 'grip_dir', 'Empunhadura direita', [.62, -.18, 0], [.34, .4, .42], '#2f333e',
          'Empunhadura ilustrativa.', ('corpo',), group='external', order=3, rot=(0, 0, 18))
    _peca(o, 'analogico_esq', 'Analógico esquerdo', [-.4, .22, -.02], [.24, .06, .24], '#14161c',
          'Direcional analógico ilustrativo.', ('corpo',), group='external', order=4,
          kind='cylinder', rot=(90, 0, 0))
    _peca(o, 'analogico_dir', 'Analógico direito', [.28, .18, -.02], [.24, .06, .24], '#14161c',
          'Direcional analógico ilustrativo.', ('corpo',), group='external', order=5,
          kind='cylinder', rot=(90, 0, 0))
    _peca(o, 'dpad', 'Direcional digital', [-.34, .12, .18], [.22, .05, .22], '#14161c',
          'Cruz direcional ilustrativa.', ('corpo',), group='external', order=6)
    _peca(o, 'botao_a', 'Botão A', [.6, .24, .18], [.11, .11, .11], '#c05c5c',
          'Botão ilustrativo.', ('corpo', 'botao_b', 'botao_x', 'botao_y'), group='external', order=7, kind='sphere')
    _peca(o, 'botao_b', 'Botão B', [.72, .16, .04], [.11, .11, .11], '#67c3d6',
          'Botão ilustrativo.', ('botao_a',), group='external', order=8, kind='sphere')
    _peca(o, 'botao_x', 'Botão X', [.48, .16, .04], [.11, .11, .11], '#8b7fd6',
          'Botão ilustrativo.', ('botao_a',), group='external', order=9, kind='sphere')
    _peca(o, 'botao_y', 'Botão Y', [.6, .08, -.08], [.11, .11, .11], '#d9b36a',
          'Botão ilustrativo.', ('botao_a',), group='external', order=10, kind='sphere')
    _peca(o, 'bumper_esq', 'Botão superior esquerdo', [-.35, .18, -.24], [.3, .06, .12], '#3a3f4c',
          'Botão de ombro ilustrativo.', ('corpo',), group='external', order=11)
    _peca(o, 'bumper_dir', 'Botão superior direito', [.35, .18, -.24], [.3, .06, .12], '#3a3f4c',
          'Botão de ombro ilustrativo.', ('corpo',), group='external', order=12)
    _peca(o, 'porta_usb', 'Porta de conexão', [0, -.14, -.26], [.14, .05, .04], '#14161c',
          'Conexão ilustrativa (cabo não incluído).', ('corpo',), group='external', order=13)
    _peca(o, 'placa', 'Placa interna', [0, 0, .05], [.8, .05, .3], '#2f7d5c',
          'Placa conceitual, visível no modo separado.', ('corpo',), group='internal', order=14)
    steps = [dict(title='Corpo', text='Forma geral de um gamepad moderno, aproximada.', selected='corpo'),
             dict(title='Analógicos', text='Os analógicos são discos ilustrativos, sem movimento real.',
                  selected='analogico_esq'),
             dict(title='Botões', text='O conjunto de botões usa cores apenas para identificação.',
                  selected='botao_a'),
             dict(title='Conexão', text='A porta ilustra uma conexão; não há cabo ou wireless reais.',
                  selected='porta_usb')]
    return _cena('controle', 'Controle ilustrativo (gamepad aproximado)',
                 'Gamepad educativo aproximado; botões e medidas são ilustrativos, sem marca.',
                 o, steps, 'gamepad ilustrativo')


def _placa_mae(education='device'):
    o = []
    _peca(o, 'placa', 'Placa', [0, 0, 0], [2.4, .07, 2.0], '#2f7d5c',
          'Base da placa-mãe com trilhas conceituais; formato aproximado de placa ATX.',
          ('soquete', 'pente_1', 'pente_2', 'pcie', 'painel_io'), role='structural', group='external', order=1)
    _peca(o, 'soquete', 'Soquete da CPU', [-.55, .05, -.35], [.5, .05, .5], '#1d1f26',
          'Soquete ilustrativo; não representa socket real.', ('placa', 'processador'), group='external', order=2)
    _peca(o, 'processador', 'Processador', [-.55, .12, -.35], [.42, .08, .42], '#c3c9d7',
          'CPU ilustrativa instalada no soquete conceitual.', ('soquete', 'pente_1'), group='external', order=3)
    _peca(o, 'slot_ram_1', 'Slot de memória 1', [.25, .04, .22], [1.5, .04, .08], '#14161c',
          'Encaixe ilustrativo de memória.', ('placa', 'pente_1'), group='external', order=4)
    _peca(o, 'slot_ram_2', 'Slot de memória 2', [.25, .04, .5], [1.5, .04, .08], '#14161c',
          'Encaixe ilustrativo de memória.', ('placa', 'pente_2'), group='external', order=5)
    _peca(o, 'pente_1', 'Memória 1', [.25, .12, .22], [1.4, .12, .1], '#8b7fd6',
          'Módulo de memória ilustrativo.', ('slot_ram_1', 'processador'), group='external', order=6)
    _peca(o, 'pente_2', 'Memória 2', [.25, .12, .5], [1.4, .12, .1], '#8b7fd6',
          'Módulo de memória ilustrativo.', ('slot_ram_2',), group='external', order=7)
    _peca(o, 'pcie', 'Slot de expansão', [-.3, .05, .78], [1.4, .06, .1], '#14161c',
          'Encaixe longo para placa de expansão, ilustrativo.', ('placa', 'chipset'), group='external', order=8)
    _peca(o, 'chipset', 'Chipset', [.6, .06, -.55], [.4, .08, .4], '#9aa0ae',
          'Chip auxiliar ilustrativo.', ('placa',), group='external', order=9)
    _peca(o, 'vrm', 'Reguladores de tensão', [-.95, .07, .12], [.7, .08, .12], '#3a3f4c',
          'Bloco de alimentação ilustrativo.', ('placa', 'soquete'), group='external', order=10)
    _peca(o, 'painel_io', 'Painel traseiro', [-1.15, .18, -.9], [.5, .3, .08], '#4a5060',
          'Conectores traseiros simplificados.', ('placa',), group='external', order=11)
    _peca(o, 'pilha', 'Bateria da placa', [.75, .05, .35], [.18, .03, .18], '#c9ccd6',
          'Bateria de relógio ilustrativa.', ('placa',), group='external', order=12,
          kind='cylinder')
    steps = [dict(title='Placa', text='A base reúne os circuitos que conectam os componentes.', selected='placa'),
             dict(title='CPU', text='O soquete e o processador são encaixes ilustrativos.', selected='processador'),
             dict(title='Memórias', text='Os módulos ocupam os slots de memória.', selected='pente_1'),
             dict(title='Expansão', text='Slots, chipset e alimentação completam a placa; encaixes não representam '
                  'compatibilidade real.', selected='pcie', exploded=True)]
    return _cena('placa-mae', 'Placa-mãe ilustrativa',
                 'Disposição aproximada de uma placa-mãe; encaixes, medidas e trilhas não representam '
                 'compatibilidade real.',
                 o, steps, 'placa-mãe ilustrativa', education=education)


def _gabinete():
    o = []
    _peca(o, 'base', 'Base do gabinete', [0, -1.07, 0], [1.0, .06, 1.1], '#3a3f4c',
          'Estrutura inferior da torre.', ('topo', 'fundo', 'lateral'), role='structural', group='external', order=1)
    _peca(o, 'topo', 'Topo do gabinete', [0, 1.07, 0], [1.0, .06, 1.1], '#3a3f4c',
          'Estrutura superior.', ('base', 'fundo', 'lateral'), role='structural', group='external', order=2)
    _peca(o, 'fundo', 'Traseira do gabinete', [0, 0, -.52], [1.0, 2.2, .06], '#3a3f4c',
          'Painel traseiro estrutural.', ('base', 'topo', 'placa'), role='structural', group='external', order=3)
    _peca(o, 'lateral', 'Painel lateral', [.5, 0, 0], [.05, 2.2, 1.1], '#4a5060',
          'Painel de vidro/concha ilustrativo: use transparência ou oculte para ver o interior.',
          ('base', 'topo', 'placa', 'gpu', 'fonte'), role='structural', group='external', order=4)
    _peca(o, 'frontal', 'Frente', [0, 0, .52], [1.0, 2.2, .06], '#23252c',
          'Frente com grade de ventilação.', ('base', 'topo', 'ventoinha_1', 'ventoinha_2'),
          role='structural', group='external', order=5)
    _peca(o, 'ventoinha_1', 'Ventoinha superior', [-.2, .75, .42], [.5, .06, .5], '#3b4152',
          'Ventoinha frontal ilustrativa.', ('frontal', 'placa'), group='internal', order=6,
          kind='cylinder', rot=(90, 0, 0))
    _peca(o, 'ventoinha_2', 'Ventoinha inferior', [-.2, .1, .42], [.5, .06, .5], '#3b4152',
          'Ventoinha frontal ilustrativa.', ('frontal', 'placa'), group='internal', order=7,
          kind='cylinder', rot=(90, 0, 0))
    _peca(o, 'fonte', 'Fonte', [-.05, -.78, -.05], [.8, .45, .8], '#2a2e38',
          'Fonte interna ilustrativa.', ('base', 'placa'), group='internal', order=8)
    _peca(o, 'placa', 'Placa-mãe', [-.3, .2, -.35], [.05, 1.2, .9], '#2f7d5c',
          'Placa interna conceitual.', ('fundo', 'gpu', 'fonte'), group='internal', order=9)
    _peca(o, 'gpu', 'Placa de vídeo', [-.15, .15, .1], [.85, .14, .35], '#3a3f4c',
          'Placa de vídeo ilustrativa conectada à placa.', ('placa',), group='internal', order=10)
    _peca(o, 'pe', 'Base de apoio', [0, -1.13, 0], [.9, .03, 1.0], '#14161c',
          'Apoio antiderrapante ilustrativo.', ('base',), group='external', order=11)
    steps = [dict(title='Estrutura', text='A torre é composta por base, topo e traseira.', selected='base'),
             dict(title='Painel lateral', text='Use Transparência ou Ocultar para ver o interior pelo painel.',
                  selected='lateral'),
             dict(title='Ventilação', text='As ventoinhas frontais são ilustrativas.', selected='ventoinha_1'),
             dict(title='Interior', text='Separe as peças para observar fonte, placa e placa de vídeo '
                  'conceituais.', selected='gpu', exploded=True)]
    return _cena('gabinete', 'Gabinete ilustrativo (torre)',
                 'Torre educativa aproximada com painel lateral e componentes internos conceituais; '
                 'medidas e encaixes não representam compatibilidade real.',
                 o, steps, 'gabinete ilustrativo')


def _monitor():
    o = []
    _peca(o, 'painel', 'Painel', [0, .25, 0], [2.0, 1.2, .07], '#262a33',
          'Corpo do painel; proporções aproximadas.', ('tela', 'haste', 'placa_controle'),
          role='structural', group='external', order=1)
    _peca(o, 'tela', 'Tela', [0, .25, .045], [1.86, 1.08, .02], '#5f8fe0',
          'Área de imagem ilustrativa, sem conteúdo real.', ('painel',), group='external', order=2)
    _peca(o, 'haste', 'Haste', [0, -.6, 0], [.09, .55, .09], '#4a5060',
          'Haste de sustentação.', ('painel', 'base'), role='structural', group='external', order=3)
    _peca(o, 'base', 'Base', [0, -.93, 0], [.6, .05, .4], '#3a3f4c',
          'Base de apoio.', ('haste',), role='structural', group='external', order=4)
    _peca(o, 'hdmi', 'Conexão', [.7, -.25, -.06], [.16, .05, .08], '#14161c',
          'Conexão de vídeo ilustrativa.', ('painel',), group='external', order=5)
    _peca(o, 'placa_controle', 'Placa de controle', [-.5, -.25, -.06], [.5, .3, .05], '#2f7d5c',
          'Eletrônica interna conceitual.', ('painel',), group='internal', order=6)
    steps = [dict(title='Tela', text='A área de imagem é ilustrativa.', selected='tela'),
             dict(title='Suporte', text='Haste e base são estruturais.', selected='haste'),
             dict(title='Conexões', text='As conexões são simplificadas.', selected='hdmi')]
    return _cena('monitor', 'Monitor ilustrativo',
                 'Monitor educativo aproximado; sem polegadas oficiais ou conexões reais.', o, steps,
                 'monitor ilustrativo')


def _teclado():
    o = []
    _peca(o, 'base', 'Base', [0, 0, 0], [1.9, .14, .62], '#3a3f4c',
          'Corpo do teclado; medidas ilustrativas.', ('fileira_1', 'espaco'), role='structural',
          group='external', order=1)
    _peca(o, 'fileira_1', 'Fileira superior', [0, .09, -.2], [1.7, .05, .12], '#23252c',
          'Fileira de teclas agrupada, apenas para leitura visual.', ('base', 'fileira_2'),
          group='external', order=2)
    _peca(o, 'fileira_2', 'Fileira central', [0, .09, -.07], [1.7, .05, .12], '#23252c',
          'Fileira de teclas agrupada.', ('fileira_1', 'fileira_3'), group='external', order=3)
    _peca(o, 'fileira_3', 'Fileira inferior', [0, .09, .06], [1.5, .05, .12], '#23252c',
          'Fileira de teclas agrupada.', ('fileira_2', 'espaco'), group='external', order=4)
    _peca(o, 'espaco', 'Barra de espaço', [0, .09, .19], [1.0, .05, .12], '#2a2e38',
          'Tecla de espaço ilustrativa.', ('base', 'fileira_3'), group='external', order=5)
    _peca(o, 'tecla_esc', 'Destaque 1', [-.83, .105, -.2], [.12, .07, .12], '#d9b36a',
          'Tecla destacada apenas para orientação visual.', ('fileira_1',), group='external', order=6)
    _peca(o, 'tecla_enter', 'Destaque 2', [.82, .105, .06], [.14, .07, .14], '#67c3d6',
          'Tecla destacada apenas para orientação visual.', ('fileira_3',), group='external', order=7)
    _peca(o, 'faixa_luz', 'Iluminação', [0, .075, .27], [.9, .02, .04], '#8b7fd6',
          'Faixa de iluminação decorativa.', ('base',), group='external', order=8)
    steps = [dict(title='Base', text='O corpo do teclado é uma composição simples.', selected='base'),
             dict(title='Teclas', text='As teclas são agrupadas em fileiras para leitura, não individualizadas.',
                  selected='fileira_2'),
             dict(title='Iluminação', text='A faixa de luz é decorativa.', selected='faixa_luz')]
    return _cena('teclado', 'Teclado ilustrativo',
                 'Teclado educativo aproximado; fileiras agrupadas, sem keycaps individuais.', o, steps,
                 'teclado ilustrativo')


def _headset():
    o = []
    _peca(o, 'arco_topo', 'Arco superior', [0, .62, 0], [.5, .08, .09], '#2a2e38',
          'Parte superior do arco; curva aproximada por segmentos.', ('arco_esq', 'arco_dir'),
          role='structural', group='external', order=1)
    _peca(o, 'arco_esq', 'Lado esquerdo do arco', [-.52, .42, 0], [.08, .35, .09], '#2a2e38',
          'Segmento lateral do arco.', ('arco_topo', 'concha_esq'), role='structural', group='external', order=2)
    _peca(o, 'arco_dir', 'Lado direito do arco', [.52, .42, 0], [.08, .35, .09], '#2a2e38',
          'Segmento lateral do arco.', ('arco_topo', 'concha_dir'), role='structural', group='external', order=3)
    _peca(o, 'concha_esq', 'Concha esquerda', [-.62, .1, 0], [.5, .5, .12], '#1d1f26',
          'Concha ilustrativa com espuma conceitual.', ('arco_esq',), group='external', order=4,
          kind='cylinder', rot=(0, 0, 90))
    _peca(o, 'concha_dir', 'Concha direita', [.62, .1, 0], [.5, .5, .12], '#1d1f26',
          'Concha ilustrativa com espuma conceitual.', ('arco_dir',), group='external', order=5,
          kind='cylinder', rot=(0, 0, 90))
    _peca(o, 'microfone_haste', 'Haste do microfone', [.45, -.2, .3], [.03, .3, .03], '#3a3f4c',
          'Haste ilustrativa.', ('concha_dir', 'microfone'), group='external', order=6, rot=(20, 0, 0))
    _peca(o, 'microfone', 'Microfone', [.42, -.36, .4], [.1, .1, .1], '#14161c',
          'Microfone ilustrativo; sem áudio real.', ('microfone_haste',), group='external', order=7, kind='sphere')
    steps = [dict(title='Arco', text='O arco é aproximado por segmentos retos.', selected='arco_topo'),
             dict(title='Conchas', text='As conchas são discos com espuma conceitual.', selected='concha_esq'),
             dict(title='Microfone', text='O microfone é puramente ilustrativo.', selected='microfone')]
    return _cena('headset', 'Headset ilustrativo',
                 'Headset educativo aproximado; sem componentes de áudio reais.', o, steps, 'headset ilustrativo')


def _mesa():
    o = []
    _peca(o, 'tampo', 'Tampo', [0, .55, 0], [2.6, .09, 1.5], '#9a6f4a',
          'Superfície de trabalho; proporções típicas de mesa.', ('perna_1', 'perna_2', 'perna_3', 'perna_4'),
          role='structural', group='external', order=1)
    for i, (x, z) in enumerate(((-1.2, -.65), (1.2, -.65), (-1.2, .65), (1.2, .65)), start=1):
        _peca(o, f'perna_{i}', f'Perna {i}', [x, -.05, z], [.09, .95, .09], '#5c4732',
              'Perna estrutural ilustrativa.', ('tampo',), role='structural', group='external', order=1 + i)
    _peca(o, 'travessa', 'Travessa', [0, .12, .62], [2.4, .06, .08], '#5c4732',
          'Travessa de estabilidade.', ('perna_2', 'perna_4'), role='structural', group='external', order=6)
    _peca(o, 'passa_cabo', 'Passagem de cabos', [.9, .61, .25], [.12, .04, .12], '#3a3f4c',
          'Abertura ilustrativa para cabos.', ('tampo',), group='external', order=7, kind='cylinder')
    _peca(o, 'suporte_headset', 'Suporte de headset', [-1.1, .72, .55], [.08, .28, .08], '#3a3f4c',
          'Elemento opcional para pendurar headset.', ('tampo',), role='optional', group='external', order=8)
    steps = [dict(title='Tampo', text='A superfície define a mesa.', selected='tampo'),
             dict(title='Pernas', text='As quatro pernas são estruturais.', selected='perna_1'),
             dict(title='Extras', text='Passagem de cabos e suporte opcional completam a mesa.',
                  selected='suporte_headset')]
    return _cena('mesa', 'Mesa ilustrativa',
                 'Mesa educativa aproximada; sem medidas oficiais de marcas.', o, steps, 'mesa ilustrativa')


def _suporte_celular():
    o = []
    _peca(o, 'base', 'Base', [0, -.4, 0], [.7, .06, .5], '#3a3f4c',
          'Base de apoio.', ('braco',), role='structural', group='external', order=1)
    _peca(o, 'braco', 'Braço', [0, -.02, -.06], [.08, .8, .08], '#4a5060',
          'Braço inclinado; ângulo aproximado.', ('base', 'apoio'), role='structural', group='external',
          order=2, rot=(-32, 0, 0))
    _peca(o, 'apoio', 'Apoio frontal', [0, .1, .16], [.6, .05, .12], '#4a5060',
          'Aba frontal que segura o celular.', ('braco',), role='structural', group='external', order=3,
          rot=(-32, 0, 0))
    _peca(o, 'celular_demo', 'Celular de exemplo', [0, .22, -.02], [.42, .8, .06], '#23252c',
          'Vista de um celular no suporte; apenas demonstração de uso.', ('braco', 'apoio'),
          role='optional', group='external', order=4, rot=(-32, 0, 0))
    steps = [dict(title='Base', text='A base dá estabilidade.', selected='base'),
             dict(title='Braço', text='O braço inclina o celular para leitura.', selected='braco'),
             dict(title='Apoio', text='A aba frontal segura o aparelho; o celular é uma demonstração.',
                  selected='apoio')]
    return _cena('suporte-celular', 'Suporte de celular ilustrativo',
                 'Suporte educativo aproximado; medidas e ângulo ilustrativos.', o, steps,
                 'suporte de celular')


def _motor_v8():
    o = []
    _peca(o, 'bloco', 'Bloco de cilindros V8', [0, .05, 0], [1.3, .75, 1.4], '#3a404d',
          'Bloco em V a 90 graus com galerias de arrefecimento e mancais principais; aproximação.',
          ('cabecote_esq', 'cabecote_dir', 'carter', 'virabrequim', 'admissao'),
          role='structural', group='external', order=1, metalness=0.75, roughness=0.35)
    _peca(o, 'carter', 'Cárter de óleo inferior', [0, -.46, 0], [1.1, .28, 1.3], '#212529',
          'Reservatório e cárter de lubrificação sob o virabrequim.', ('bloco',),
          role='structural', group='external', order=2, metalness=0.6, roughness=0.4, explodeVector=[0, -.8, 0])
    _peca(o, 'cabecote_esq', 'Cabeçote do banco esquerdo', [-.45, .52, 0], [.55, .28, 1.35], '#495057',
          'Cabeçote com câmaras de combustão e sedes de válvulas.', ('bloco', 'tampa_esq', 'coletor_escape_esq'),
          role='structural', group='external', order=3, rot=(0, 0, 28), metalness=0.8, roughness=0.3, explodeVector=[-.8, .8, 0])
    _peca(o, 'cabecote_dir', 'Cabeçote do banco direito', [.45, .52, 0], [.55, .28, 1.35], '#495057',
          'Cabeçote do banco direito com câmara de fluxo cruzado.', ('bloco', 'tampa_dir', 'coletor_escape_dir'),
          role='structural', group='external', order=4, rot=(0, 0, -28), metalness=0.8, roughness=0.3, explodeVector=[.8, .8, 0])
    _peca(o, 'tampa_esq', 'Tampa de válvulas anodizada esquerda', [-.55, .72, 0], [.48, .14, 1.38], '#c92a2a',
          'Tampa protetora do comando com acabamento em pintura eletrostática.', ('cabecote_esq',),
          group='external', order=5, rot=(0, 0, 28), metalness=0.7, roughness=0.2, explodeVector=[-1.1, 1.2, 0])
    _peca(o, 'tampa_dir', 'Tampa de válvulas anodizada direita', [.55, .72, 0], [.48, .14, 1.38], '#c92a2a',
          'Tampa protetora do comando direito.', ('cabecote_dir',),
          group='external', order=6, rot=(0, 0, -28), metalness=0.7, roughness=0.2, explodeVector=[1.1, 1.2, 0])
    _peca(o, 'virabrequim', 'Virabrequim crossplane forjado', [0, -.15, 0], [.24, .24, 1.5], '#adb5bd',
          'Eixo de manivelas crossplane forjado com contrapesos de balanceamento.', ('bloco', 'pistao_e1', 'polia'),
          role='functional', group='internal', order=7, kind='cylinder', rot=(90, 0, 0), metalness=0.95, roughness=0.15, explodeVector=[0, -.5, 0])
    for i, z in enumerate((-.5, -.17, .17, .5), start=1):
        _peca(o, f'pistao_e{i}', f'Pistão e biela esquerdo {i}', [-.32, .25, z], [.22, .32, .22], '#ced4da',
              f'Pistão forjado do banco esquerdo {i} com anéis de compressão.', ('virabrequim', 'cabecote_esq'),
              group='internal', order=7 + i, kind='cylinder', rot=(0, 0, 28), metalness=0.9, roughness=0.2, explodeVector=[-.6, .6, 0])
        _peca(o, f'pistao_d{i}', f'Pistão e biela direito {i}', [.32, .25, z], [.22, .32, .22], '#ced4da',
              f'Pistão forjado do banco direito {i}.', ('virabrequim', 'cabecote_dir'),
              group='internal', order=11 + i, kind='cylinder', rot=(0, 0, -28), metalness=0.9, roughness=0.2, explodeVector=[.6, .6, 0])
    _peca(o, 'admissao', 'Coletor de admissão plenum duplo', [0, .76, 0], [.72, .22, 1.1], '#868e96',
          'Coletor de admissão de ar de alta vazão no vale central entre os bancos.', ('bloco', 'corpo_borboleta'),
          group='external', order=16, metalness=0.85, roughness=0.25, explodeVector=[0, 1.1, 0])
    _peca(o, 'corpo_borboleta', 'Corpo de borboleta frontal', [0, .86, .65], [.32, .32, .22], '#343a40',
          'Válvula borboleta eletrônica dosadora de ar.', ('admissao',),
          group='external', order=17, kind='cylinder', rot=(90, 0, 0), metalness=0.8, roughness=0.3, explodeVector=[0, 1.2, .6])
    _peca(o, 'coletor_escape_esq', 'Coletores tubulares de escape esquerdo', [-.82, .25, 0], [.28, .45, 1.25], '#b18852',
          'Coletores de escape individuais dimensionados em aço inox revenido.', ('cabecote_esq',),
          group='external', order=18, metalness=0.75, roughness=0.4, explodeVector=[-1.2, -.2, 0])
    _peca(o, 'coletor_escape_dir', 'Coletores tubulares de escape direito', [.82, .25, 0], [.28, .45, 1.25], '#b18852',
          'Coletores tubulares de escape do banco direito.', ('cabecote_dir',),
          group='external', order=19, metalness=0.75, roughness=0.4, explodeVector=[1.2, -.2, 0])
    _peca(o, 'polia', 'Polia e amortecedor harmônico', [0, -.15, .82], [.38, .38, .12], '#212529',
          'Polia frontal da correia de acessórios com dumper torsional.', ('virabrequim',),
          group='external', order=20, kind='cylinder', rot=(90, 0, 0), metalness=0.7, roughness=0.3, explodeVector=[0, 0, .8])
    _peca(o, 'volante_motor', 'Volante do motor para embreagem', [0, -.15, -.82], [.62, .62, .12], '#495057',
          'Volante de inércia com cremalheira de partida.', ('virabrequim',),
          group='external', order=21, kind='cylinder', rot=(90, 0, 0), metalness=0.85, roughness=0.2, explodeVector=[0, 0, -.8])
    steps = [dict(title='Bloco e Bancos em V', text='Os dois bancos de 4 cilindros em ângulo de 90° proporcionam equilíbrio mecânico.', selected='bloco'),
             dict(title='Conjunto Móvel Interno', text='Virabrequim crossplane e os 8 pistões convertem a combustão em rotação.', selected='virabrequim'),
             dict(title='Admissão e Escapamento', text='Coletor de alto fluxo superior e saídas tubulares independentes.', selected='admissao'),
             dict(title='Vista Explodida Mecânica', text='Desmontagem vertical dos cabeçotes e radial dos pistões.', selected='cabecote_esq', exploded=True)]
    return _cena('motor-v8', 'Motor V8 de alta performance',
                 'Composição mecânica educativa e aproximada de um motor V8 em 90 graus: bloco, 8 pistões, virabrequim, cabeçotes e coletores.',
                 o, steps, 'motor V8 mecânico')


def _notebook(education='device'):
    o = []
    _peca(o, 'base', 'Base', [0, 0, 0], [1.7, .09, 1.15], '#4a5060',
          'Base com teclado e componentes; espessura ilustrativa.', ('teclado_1', 'tela_aro', 'bateria'),
          role='structural', group='external', order=1)
    _peca(o, 'teclado_1', 'Fileira de teclas 1', [0, .06, -.26], [1.5, .03, .26], '#3a3f4c',
          'Fileira agrupada de teclas.', ('base', 'teclado_2'), group='external', order=2)
    _peca(o, 'teclado_2', 'Fileira de teclas 2', [0, .06, .0], [1.5, .03, .26], '#3a3f4c',
          'Fileira agrupada de teclas.', ('teclado_1', 'teclado_3'), group='external', order=3)
    _peca(o, 'teclado_3', 'Fileira de teclas 3', [0, .06, .26], [1.4, .03, .22], '#3a3f4c',
          'Fileira agrupada de teclas.', ('teclado_2', 'touchpad'), group='external', order=4)
    _peca(o, 'touchpad', 'Touchpad', [0, .061, .42], [.5, .02, .24], '#2a2e38',
          'Área de toque ilustrativa.', ('base',), group='external', order=5)
    _peca(o, 'tela_aro', 'Moldura da tela', [0, .207, -1.045], [1.7, 1.05, .05], '#3a3f4c',
          'Moldura da tela conectada à base.', ('base', 'tela'), role='structural', group='external',
          order=6, rot=(-72, 0, 0))
    _peca(o, 'tela', 'Tela', [0, .212, -1.02], [1.56, .9, .02], '#5f8fe0',
          'Tela ilustrativa, sem sistema.', ('tela_aro',), group='external', order=7, rot=(-72, 0, 0))
    _peca(o, 'porta_usb', 'Porta USB', [.86, 0, -.1], [.05, .04, .12], '#14161c',
          'Porta lateral simplificada.', ('base',), group='external', order=8)
    _peca(o, 'bateria', 'Bateria', [0, -.035, .1], [1.3, .06, .8], '#3f9c74',
          'Bateria conceitual sob o teclado.', ('base', 'placa_interna'), group='internal', order=9)
    _peca(o, 'placa_interna', 'Placa interna', [0, -.03, -.35], [1.0, .04, .5], '#2f7d5c',
          'Placa conceitual.', ('base', 'bateria'), group='internal', order=10)
    steps = [dict(title='Base e teclado', text='A base reúne teclado e touchpad.', selected='base'),
             dict(title='Tela', text='A moldura inclina a tela; ângulo aproximado.', selected='tela'),
             dict(title='Conexões', text='Portas são simplificadas.', selected='porta_usb'),
             dict(title='Interior', text='Separe as peças para ver bateria e placa conceituais.',
                  selected='bateria', exploded=True)]
    return _cena('notebook', 'Notebook ilustrativo (aproximação)',
                 'Notebook educativo aproximado: base, teclado, tela e interior conceitual; '
                 'espessuras e encaixes são ilustrativos.', o, steps, 'notebook ilustrativo',
                 education=education)


def _turbina_aviao():
    o = []
    _peca(o, 'carenagem_sup', 'Carenagem externa superior', [0, .72, 0], [1.9, .25, 2.3], '#7b8594',
          'Capô superior de fluxo com revestimento acústico antirruído; aproximação.',
          ('carenagem_inf', 'duto_bypass', 'fan_case'),
          role='structural', group='external', order=1, metalness=0.8, roughness=0.3, explodeVector=[0, .9, 0])
    _peca(o, 'carenagem_inf', 'Carenagem externa inferior', [0, -.72, 0], [1.9, .25, 2.3], '#7b8594',
          'Capô articulado inferior para manutenção da nacelle.',
          ('carenagem_sup', 'duto_bypass', 'caixa_engrenagens'),
          role='structural', group='external', order=2, metalness=0.8, roughness=0.3, explodeVector=[0, -.9, 0])
    _peca(o, 'spinner_cone', 'Cone aerodinâmico frontal', [0, 0, 1.15], [.35, .5, .35], '#c92a2a',
          'Cone ogival frontal giratório com pintura espiral antipássaros.', ('fan_blades',),
          group='external', order=3, kind='cone', rot=(90, 0, 0), roughness=0.2, metalness=0.6, explodeVector=[0, 0, 1.2])
    _peca(o, 'fan_blades', 'Palhetas do Fan de Titânio', [0, 0, .85], [1.65, 1.65, .15], '#9cb3c9',
          'Rotor de titânio forjado com palhetas de corda larga que aceleram o ar primário e secundário.', ('spinner_cone', 'fan_case', 'eixo_spool'),
          role='functional', group='external', order=4, kind='cylinder', rot=(90, 0, 0), roughness=0.25, metalness=0.85, explodeVector=[0, 0, .9])
    _peca(o, 'fan_case', 'Anel de contenção do fan', [0, 0, .85], [1.8, 1.8, .22], '#343a40',
          'Anel balístico de contenção reforçado com aramida Kevlar.', ('fan_blades', 'duto_bypass'),
          role='structural', group='external', order=5, kind='ring', rot=(90, 0, 0), roughness=0.4, metalness=0.7, explodeVector=[0, 0, .7])
    _peca(o, 'duto_bypass', 'Duto de fluxo secundário bypass', [0, 0, 0], [1.7, 1.7, 1.2], '#495057',
          'Duto que guia o fluxo secundário gerando até 85% do empuxo total.', ('fan_case', 'estator_ogv'),
          role='structural', group='external', order=6, kind='pipe', rot=(90, 0, 0), opacity=0.85, transparent=True, roughness=0.5, metalness=0.5)
    _peca(o, 'estator_ogv', 'Palhetas estatoras guia de saída', [0, 0, .58], [1.55, 1.55, .1], '#6c757d',
          'Aletas aerodinâmicas fixas que eliminam a rotação turbulenta do ar.', ('duto_bypass', 'compressor_baixa'),
          group='internal', order=7, kind='cylinder', rot=(90, 0, 0), metalness=0.7, roughness=0.4, explodeVector=[0, 0, .5])
    _peca(o, 'compressor_baixa', 'Compressor de Baixa Pressão (LPC)', [0, 0, .35], [.85, .85, .28], '#868e96',
          'Estágios axiais iniciais de compressão do núcleo central.', ('eixo_spool', 'compressor_alta'),
          group='internal', order=8, kind='cylinder', rot=(90, 0, 0), metalness=0.8, roughness=0.3, explodeVector=[0, 0, .3])
    _peca(o, 'compressor_alta', 'Compressor de Alta Pressão (HPC)', [0, 0, .05], [.72, .72, .32], '#adb5bd',
          'Estágios de alta razão de pressão antes da câmara.', ('compressor_baixa', 'difusor'),
          group='internal', order=9, kind='cylinder', rot=(90, 0, 0), metalness=0.85, roughness=0.25, explodeVector=[0, 0, .1])
    _peca(o, 'difusor', 'Difusor anular', [0, 0, -.16], [.68, .68, .1], '#495057',
          'Transição aerodinâmica que reduz a velocidade e eleva a pressão estática.', ('compressor_alta', 'camara_combustao'),
          group='internal', order=10, kind='ring', rot=(90, 0, 0), metalness=0.6, roughness=0.5)
    _peca(o, 'camara_combustao', 'Câmara de combustão anular', [0, 0, -.32], [.75, .75, .24], '#d9480f',
          'Liner de cerâmica térmica onde o querosene é injetado e queimado a mais de 1500°C.', ('difusor', 'injetores', 'turbina_alta'),
          group='internal', order=11, kind='cylinder', rot=(90, 0, 0), emissive='#551100', roughness=0.6, metalness=0.4, explodeVector=[0, 0, -.2])
    _peca(o, 'injetores', 'Injetores de combustível', [0, 0, -.24], [.8, .8, .06], '#f59f00',
          'Bicos atomizadores de querosene em anel de injeção direta.', ('camara_combustao',),
          group='internal', order=12, kind='ring', rot=(90, 0, 0), metalness=0.9, roughness=0.2, explodeVector=[0, 0, -.1])
    _peca(o, 'turbina_alta', 'Turbina de Alta Pressão (HPT)', [0, 0, -.5], [.68, .68, .12], '#5c7cfa',
          'Palhetas monocristalinas resfriadas internamente que movem o compressor de alta.', ('camara_combustao', 'turbina_baixa'),
          group='internal', order=13, kind='cylinder', rot=(90, 0, 0), metalness=0.9, roughness=0.2, explodeVector=[0, 0, -.4])
    _peca(o, 'turbina_baixa', 'Turbinas de Baixa Pressão (LPT)', [0, 0, -.68], [.8, .8, .22], '#4263eb',
          'Múltiplos estágios de expansão que acionam o grande fan frontal via eixo central.', ('turbina_alta', 'eixo_spool'),
          group='internal', order=14, kind='cylinder', rot=(90, 0, 0), metalness=0.9, roughness=0.2, explodeVector=[0, 0, -.6])
    _peca(o, 'eixo_spool', 'Eixo central de acionamento concêntrico', [0, 0, .05], [.14, .14, 1.7], '#343a40',
          'Eixo de aço de alta resistência mecânica conectando a turbina ao fan.', ('fan_blades', 'turbina_baixa'),
          role='structural', group='internal', order=15, kind='cylinder', rot=(90, 0, 0), metalness=0.95, roughness=0.15)
    _peca(o, 'cone_escape', 'Cone central de exaustão', [0, 0, -1.05], [.4, .55, .4], '#212529',
          'Plug central aerodinâmico que alinha os gases da turbina.', ('turbina_baixa', 'bocal_escape'),
          group='external', order=16, kind='cone', rot=(-90, 0, 0), metalness=0.7, roughness=0.4, explodeVector=[0, 0, -1.0])
    _peca(o, 'bocal_escape', 'Bocal de exaustão convergente', [0, 0, -.92], [1.15, 1.15, .35], '#343a40',
          'Bocal de aceleração final do fluxo de gases quentes.', ('cone_escape',),
          role='structural', group='external', order=17, kind='pipe', rot=(90, 0, 0), metalness=0.8, roughness=0.35, explodeVector=[0, 0, -.8])
    _peca(o, 'caixa_engrenagens', 'Caixa de acessórios e bombas (AGB)', [0, -.88, .2], [.55, .22, .45], '#2b303a',
          'Transmissão acessória com geradores elétricos e bombas hidráulicas.', ('carenagem_inf',),
          group='external', order=18, metalness=0.6, roughness=0.4, explodeVector=[0, -.7, 0])
    _peca(o, 'pilone_asa', 'Pilone de fixação estrutural sob a asa', [0, .92, 0], [.26, .32, 1.4], '#5c677d',
          'Suporte estrutural reforçado que ancora o motor à asa da aeronave.', ('carenagem_sup',),
          role='structural', group='external', order=19, metalness=0.7, roughness=0.4, explodeVector=[0, .8, 0])
    steps = [dict(title='Carenagem e Fan', text='O fan frontal de titânio capta o ar e direciona a maior parte pelo duto bypass.', selected='fan_blades', view='front'),
             dict(title='Núcleo do Motor', text='Compressores de baixa e alta pressão comprimem o ar antes da câmara.', selected='compressor_alta', view='side'),
             dict(title='Combustão e Turbinas', text='A câmara queima combustível e os gases expandem nas turbinas que movem o eixo central.', selected='camara_combustao', view='side'),
             dict(title='Modo Explodido', text='Separação axial completa ao longo do eixo mecânico.', selected='eixo_spool', exploded=True)]
    return _cena('turbina_aviao', 'Turbina turbofan aeronáutica',
                 'Turbina aeronáutica turbofan de alta razão de diluição (High-Bypass); modelo educativo aproximado com fan, compressores, câmara de combustão, turbina e bocal de exaustão.',
                 o, steps, 'turbina turbofan aeronáutica')


def _smartphone_desmontado():
    o = []
    _peca(o, 'chassi_titanio', 'Chassi estrutural de titânio aeroespacial', [0, 0, 0], [.82, 1.65, .06], '#495057',
          'Chassi usinado em peça única com pontos de ancoragem para tela e componentes; aproximação.',
          ('vidro_frontal', 'tela_oled', 'placa_mae', 'bateria_lipo', 'vidro_traseiro'),
          role='structural', group='external', order=1, metalness=0.85, roughness=0.25)
    _peca(o, 'vidro_frontal', 'Vidro protetor Ceramic Shield frontal', [0, 0, .18], [.78, 1.6, .02], '#809bb8',
          'Camada de vidro cerâmico de alta resistência a riscos e impactos.', ('tela_oled',),
          role='structural', group='external', order=2, opacity=0.35, transparent=True, roughness=0.08, metalness=0.1, explodeVector=[0, 0, 1.4])
    _peca(o, 'tela_oled', 'Painel flexível Super Retina OLED', [0, 0, .12], [.76, 1.58, .02], '#111317',
          'Display emissivo OLED com taxa adaptativa de 120Hz e microcontrolador táctil.', ('chassi_titanio', 'vidro_frontal'),
          group='external', order=3, roughness=0.15, metalness=0.3, explodeVector=[0, 0, 1.0])
    _peca(o, 'placa_mae', 'Placa lógica principal em L', [-.18, .38, .02], [.38, .75, .03], '#2b593f',
          'PCB multicamada de alta densidade integrando o processador e memórias.', ('chassi_titanio', 'processador_soc', 'modulo_cameras'),
          group='internal', order=4, roughness=0.4, metalness=0.5, explodeVector=[-.3, .4, .6])
    _peca(o, 'processador_soc', 'Processador SoC com dissipador grafeno', [-.18, .45, .04], [.2, .2, .02], '#1c1f24',
          'System on Chip com CPU de 6 núcleos, GPU gráfica e acelerador de IA neural.', ('placa_mae',),
          group='internal', order=5, roughness=0.2, metalness=0.8, explodeVector=[-.3, .5, .9])
    _peca(o, 'memoria_ram', 'Memória unificada LPDDR5X', [-.18, .28, .04], [.18, .14, .02], '#212529',
          'Módulo de alta largura de banda para multitarefa veloz.', ('placa_mae',),
          group='internal', order=6, roughness=0.2, metalness=0.7, explodeVector=[-.3, .3, .9])
    _peca(o, 'bateria_lipo', 'Bateria Li-Ion de alta densidade energética', [.14, -.12, .01], [.46, 1.1, .05], '#343a40',
          'Célula química selada de 4500mAh com controlador de carga rápida.', ('chassi_titanio', 'bobina_wireless'),
          group='internal', order=7, roughness=0.5, metalness=0.3, explodeVector=[.5, -.1, .5])
    _peca(o, 'modulo_cameras', 'Módulo triplo de câmeras estabilizadas', [-.22, .58, -.06], [.32, .32, .06], '#1e2126',
          'Conjunto com sensor principal, ultra-angular e teleobjetiva periscópica.', ('placa_mae', 'lente_principal'),
          group='external', order=8, roughness=0.25, metalness=0.7, explodeVector=[-.4, .6, -.8])
    _peca(o, 'lente_principal', 'Lente grande-angular com anel de safira', [-.28, .64, -.11], [.12, .12, .04], '#0b0c10',
          'Lente de 48MP com abertura f/1.78 e estabilização por deslocamento de sensor.', ('modulo_cameras',),
          group='external', order=9, kind='cylinder', rot=(90, 0, 0), roughness=0.1, metalness=0.9, explodeVector=[-.5, .7, -1.2])
    _peca(o, 'lente_telefoto', 'Lente telefoto periscópica', [-.16, .64, -.11], [.12, .12, .04], '#0b0c10',
          'Zoom óptico de 5x com prisma reflexivo interno.', ('modulo_cameras',),
          group='external', order=10, kind='cylinder', rot=(90, 0, 0), roughness=0.1, metalness=0.9, explodeVector=[-.3, .7, -1.2])
    _peca(o, 'lente_ultra', 'Lente ultra grande-angular', [-.22, .52, -.11], [.12, .12, .04], '#0b0c10',
          'Lente de 120 graus de campo de visão para fotografia macro.', ('modulo_cameras',),
          group='external', order=11, kind='cylinder', rot=(90, 0, 0), roughness=0.1, metalness=0.9, explodeVector=[-.4, .5, -1.2])
    _peca(o, 'bobina_wireless', 'Bobina indutiva de cobre MagSafe', [0, -.05, -.04], [.55, .55, .02], '#d97706',
          'Espiras circulares de cobre eletrolítico para carregamento por indução magnética.', ('bateria_lipo',),
          group='internal', order=12, kind='ring', rot=(90, 0, 0), metalness=0.9, roughness=0.2, explodeVector=[0, -.1, -.5])
    _peca(o, 'motor_haptico', 'Atuador linear háptico Taptic Engine', [-.18, -.72, .01], [.28, .12, .03], '#495057',
          'Ressonador linear eletromagnético que produz feedback tátil refinado.', ('chassi_titanio',),
          group='internal', order=13, roughness=0.3, metalness=0.8, explodeVector=[-.3, -.8, .4])
    _peca(o, 'alto_falante', 'Módulo acústico estéreo inferior', [.16, -.72, .01], [.34, .12, .03], '#212529',
          'Câmara acústica com membrana de polímero para graves e agudos.', ('chassi_titanio',),
          group='internal', order=14, roughness=0.4, metalness=0.5, explodeVector=[.3, -.8, .4])
    _peca(o, 'porta_usbc', 'Conector USB-C blindado', [0, -.81, 0], [.2, .05, .04], '#adb5bd',
          'Porta de alta velocidade USB 3.0 com suporte a saída de vídeo DisplayPort.', ('chassi_titanio',),
          group='external', order=15, metalness=0.9, roughness=0.2, explodeVector=[0, -1.0, 0])
    _peca(o, 'vidro_traseiro', 'Vidro traseiro fosco texturizado', [0, 0, -.06], [.78, 1.6, .02], '#5c677d',
          'Painel traseiro de vidro microjateado resistente a impressões digitais.', ('chassi_titanio',),
          role='structural', group='external', order=16, opacity=0.85, roughness=0.3, metalness=0.2, explodeVector=[0, 0, -1.3])
    steps = [dict(title='Estrutura em Camadas', text='Os componentes modernos são empilhados em frações de milímetro.', selected='chassi_titanio', view='front'),
             dict(title='Tela e Vidro Cerâmico', text='O painel OLED flexível e a cobertura de vidro ultrafina.', selected='tela_oled', view='side'),
             dict(title='Processador e Placa-Mãe', text='O SoC principal integra CPU, GPU e acelerador neural.', selected='processador_soc', view='front'),
             dict(title='Desmontagem Explodida', text='Separação em eixos perpendiculares para visualizar todos os chips.', selected='bateria_lipo', exploded=True)]
    return _cena('smartphone_desmontado', 'Smartphone desmontado em camadas',
                 'Smartphone desmontado em camadas mecânicas: chassi de titânio, tela OLED, placa-mãe em L, bateria Li-Ion, bobina MagSafe e módulo de câmeras triplo; modelo educativo aproximado.',
                 o, steps, 'smartphone desmontado')


def _drone_quadricoptero():
    o = []
    _peca(o, 'quadro_carbono', 'Chassi inferior em X de fibra de carbono 3K', [0, -.05, 0], [1.9, .06, 1.9], '#1c1f24',
          'Estrutura em X simétrico cortada em CNC de fibra de carbono 3K com braços reforçados; aproximação.',
          ('placa_topo', 'motor_1', 'motor_2', 'motor_3', 'motor_4'),
          role='structural', group='external', order=1, roughness=0.35, metalness=0.2)
    _peca(o, 'placa_topo', 'Top plate superior de carbono', [0, .16, 0], [.6, .04, 1.2], '#1c1f24',
          'Placa superior que protege a eletrônica e ancora a bateria.', ('quadro_carbono', 'bateria_lipo'),
          role='structural', group='external', order=2, roughness=0.35, metalness=0.2, explodeVector=[0, .6, 0])
    _peca(o, 'stack_controladora', 'Controladora de voo F7 com ESC 4-em-1', [0, .05, 0], [.42, .12, .42], '#2b593f',
          'Stack eletrônica montada em borrachas amortecedoras com giroscópio de 8kHz e ESCs de 45A.', ('quadro_carbono',),
          group='internal', order=3, roughness=0.4, metalness=0.5, explodeVector=[0, .3, 0])
    _peca(o, 'motor_1', 'Motor brushless 2306 dianteiro esquerdo', [-.75, .06, .75], [.28, .22, .28], '#0077b6',
          'Motor elétrico sem escovas com ímãs de neodímio N52 e rolamentos cerâmicos.', ('quadro_carbono', 'helice_1'),
          group='external', order=4, kind='cylinder', rot=(0, 0, 0), metalness=0.85, roughness=0.2, explodeVector=[-.5, .4, .5])
    _peca(o, 'motor_2', 'Motor brushless 2306 dianteiro direito', [.75, .06, .75], [.28, .22, .28], '#0077b6',
          'Motor elétrico sem escovas direito com rotação invertida CCW.', ('quadro_carbono', 'helice_2'),
          group='external', order=5, kind='cylinder', rot=(0, 0, 0), metalness=0.85, roughness=0.2, explodeVector=[.5, .4, .5])
    _peca(o, 'motor_3', 'Motor brushless 2306 traseiro esquerdo', [-.75, .06, -.75], [.28, .22, .28], '#0077b6',
          'Motor elétrico sem escovas traseiro esquerdo CCW.', ('quadro_carbono', 'helice_3'),
          group='external', order=6, kind='cylinder', rot=(0, 0, 0), metalness=0.85, roughness=0.2, explodeVector=[-.5, .4, -.5])
    _peca(o, 'motor_4', 'Motor brushless 2306 traseiro direito', [.75, .06, -.75], [.28, .22, .28], '#0077b6',
          'Motor elétrico sem escovas traseiro direito CW.', ('quadro_carbono', 'helice_4'),
          group='external', order=7, kind='cylinder', rot=(0, 0, 0), metalness=0.85, roughness=0.2, explodeVector=[.5, .4, -.5])
    _peca(o, 'helice_1', 'Hélice tripá de policarbonato DE', [-.75, .2, .75], [.85, .04, .85], '#00b4d8',
          'Hélice aerodinâmica de 5 polegadas moldada em policarbonato inquebrável.', ('motor_1',),
          group='external', order=8, kind='cylinder', opacity=0.85, roughness=0.2, metalness=0.1, explodeVector=[-.5, .8, .5])
    _peca(o, 'helice_2', 'Hélice tripá de policarbonato DD', [.75, .2, .75], [.85, .04, .85], '#00b4d8',
          'Hélice tripá dianteira direita com passo otimizado.', ('motor_2',),
          group='external', order=9, kind='cylinder', opacity=0.85, roughness=0.2, metalness=0.1, explodeVector=[.5, .8, .5])
    _peca(o, 'helice_3', 'Hélice tripá de policarbonato TE', [-.75, .2, -.75], [.85, .04, .85], '#00b4d8',
          'Hélice tripá traseira esquerda.', ('motor_3',),
          group='external', order=10, kind='cylinder', opacity=0.85, roughness=0.2, metalness=0.1, explodeVector=[-.5, .8, -.5])
    _peca(o, 'helice_4', 'Hélice tripá de policarbonato TD', [.75, .2, -.75], [.85, .04, .85], '#00b4d8',
          'Hélice tripá traseira direita.', ('motor_4',),
          group='external', order=11, kind='cylinder', opacity=0.85, roughness=0.2, metalness=0.1, explodeVector=[.5, .8, -.5])
    _peca(o, 'camera_fpv', 'Micro câmera FPV de baixa latência', [0, .12, .52], [.22, .22, .24], '#e63946',
          'Sensor CMOS micro WDR ajustável para visão do piloto em tempo real.', ('placa_topo',),
          group='external', order=12, roughness=0.3, metalness=0.6, explodeVector=[0, .2, .8])
    _peca(o, 'antena_vtx', 'Antena circular polarizada VTX 5.8GHz', [0, .42, -.48], [.12, .45, .12], '#e63946',
          'Antena omnidirecional lollipop de transmissão de sinal de vídeo sem interferências.', ('placa_topo',),
          group='external', order=13, kind='cylinder', rot=(25, 0, 0), roughness=0.4, metalness=0.4, explodeVector=[0, .6, -.7])
    _peca(o, 'bateria_lipo', 'Bateria LiPo 4S 1500mAh 120C', [0, .32, -.05], [.45, .28, .72], '#f77f00',
          'Pack de baterias de polímero de lítio de alta taxa de descarga contínua.', ('placa_topo',),
          group='external', order=14, roughness=0.5, metalness=0.2, explodeVector=[0, .9, 0])
    steps = [dict(title='Estrutura em X de Fibra de Carbono', text='Braços independentes distribuem as forças e vibrações dos 4 motores.', selected='quadro_carbono', view='top'),
             dict(title='Motores Brushless e Hélices', text='Rotação oposta nos pares (CW e CCW) anula o torque residual.', selected='motor_1', view='front'),
             dict(title='Eletrônica e Controladora', text='Stack central com giroscópio, acelerômetro e ESCs de 45A.', selected='stack_controladora', view='side'),
             dict(title='Desmontagem Explodida', text='Separação dos motores, hélices, bateria LiPo e câmera FPV.', selected='bateria_lipo', exploded=True)]
    return _cena('drone_quadricoptero', 'Drone quadricóptero FPV',
                 'Drone quadricóptero de alta performance: chassi de fibra de carbono 3K, 4 motores brushless, hélices de policarbonato, stack controladora F7 e câmera FPV; modelo educativo aproximado.',
                 o, steps, 'drone quadricóptero FPV')


def _coracao_humano():
    o = []
    _peca(o, 'ventriculo_esquerdo', 'Ventrículo esquerdo com miocárdio espesso', [.22, -.25, 0], [.72, .9, .72], '#85141c',
          'Câmara cardíaca com espessura muscular desenvolvida para bombear sangue oxigenado para a aorta; aproximação.',
          ('ventriculo_direito', 'arco_aorta', 'valvula_mitral', 'septo_interventricular'),
          role='structural', group='external', order=1, kind='sphere', roughness=0.6, metalness=0.1)
    _peca(o, 'ventriculo_direito', 'Ventrículo direito', [-.22, -.22, .12], [.68, .82, .68], '#9b1823',
          'Câmara de ejeção pulmonar de baixa pressão.', ('ventriculo_esquerdo', 'arteria_pulmonar', 'valvula_tricuspide'),
          role='structural', group='external', order=2, kind='sphere', roughness=0.6, metalness=0.1)
    _peca(o, 'atrio_esquerdo', 'Átrio esquerdo posterossuperior', [.26, .35, -.18], [.55, .52, .55], '#a41926',
          'Câmara receptora do sangue oxigenado vindo das veias pulmonares.', ('ventriculo_esquerdo', 'veias_pulmonares'),
          role='structural', group='external', order=3, kind='sphere', roughness=0.55, metalness=0.1)
    _peca(o, 'atrio_direito', 'Átrio direito anterossuperior', [-.32, .32, .05], [.58, .55, .58], '#ab1e2c',
          'Câmara de recepção venosa das veias cavas superior e inferior.', ('ventriculo_direito', 'veia_cava_superior', 'veia_cava_inferior'),
          role='structural', group='external', order=4, kind='sphere', roughness=0.55, metalness=0.1)
    _peca(o, 'arco_aorta', 'Arco da artéria aorta ascendente', [.05, .68, 0], [.48, .62, .48], '#c92a2a',
          'Maior vaso do corpo humano, ramificando o sangue arterial.', ('ventriculo_esquerdo', 'arteria_braquiocefalica', 'arteria_carotida', 'arteria_subclavia'),
          group='external', order=5, kind='cylinder', rot=(0, 0, 15), roughness=0.4, metalness=0.25, explodeVector=[0, .9, 0])
    _peca(o, 'arteria_braquiocefalica', 'Tronco braquiocefálico do arco aórtico', [-.08, .95, 0], [.14, .35, .14], '#c92a2a',
          'Primeiro grande ramo da aorta que vasculariza o braço direito e lado direito da cabeça.', ('arco_aorta',),
          group='external', order=6, kind='cylinder', roughness=0.4, metalness=0.25, explodeVector=[-.2, 1.2, 0])
    _peca(o, 'arteria_carotida', 'Artéria carótida comum esquerda', [.06, .98, 0], [.12, .38, .12], '#c92a2a',
          'Ramo aórtico que irriga o cérebro e face pelo lado esquerdo.', ('arco_aorta',),
          group='external', order=7, kind='cylinder', roughness=0.4, metalness=0.25, explodeVector=[.1, 1.3, 0])
    _peca(o, 'arteria_subclavia', 'Artéria subclávia esquerda', [.18, .92, -.05], [.12, .32, .12], '#c92a2a',
          'Ramo aórtico direcionado ao membro superior esquerdo.', ('arco_aorta',),
          group='external', order=8, kind='cylinder', roughness=0.4, metalness=0.25, explodeVector=[.3, 1.2, 0])
    _peca(o, 'arteria_pulmonar', 'Tronco da artéria pulmonar', [-.14, .52, .22], [.42, .55, .42], '#1971c2',
          'Vaso que conduz sangue desoxigenado do ventrículo direito para os pulmões.', ('ventriculo_direito',),
          group='external', order=9, kind='cylinder', rot=(-20, 0, -15), roughness=0.4, metalness=0.25, explodeVector=[-.3, .7, .6])
    _peca(o, 'veia_cava_superior', 'Veia cava superior', [-.45, .72, -.1], [.26, .55, .26], '#1864ab',
          'Grande vaso venoso que traz sangue da cabeça, pescoço e membros superiores.', ('atrio_direito',),
          group='external', order=10, kind='cylinder', roughness=0.4, metalness=0.2, explodeVector=[-.7, .8, -.2])
    _peca(o, 'veia_cava_inferior', 'Veia cava inferior', [-.42, -.65, -.15], [.26, .45, .26], '#1864ab',
          'Conduz o sangue venoso vindo dos órgãos abdominais e pernas.', ('atrio_direito',),
          group='external', order=11, kind='cylinder', roughness=0.4, metalness=0.2, explodeVector=[-.7, -.8, -.2])
    _peca(o, 'veias_pulmonares', 'Veias pulmonares esquerdas e direitas', [.52, .38, -.28], [.24, .32, .24], '#c92a2a',
          'Quatro veias que desembocam sangue vermelho vivo no átrio esquerdo.', ('atrio_esquerdo',),
          group='external', order=12, kind='cylinder', rot=(0, 0, 45), roughness=0.4, metalness=0.2, explodeVector=[.8, .4, -.5])
    _peca(o, 'septo_interventricular', 'Septo muscular interventricular', [0, -.22, 0], [.12, .75, .55], '#6f0e16',
          'Parede muscular que isola hermeticamente os dois lados do coração.', ('ventriculo_esquerdo', 'ventriculo_direito'),
          role='structural', group='internal', order=13, roughness=0.6, metalness=0.1)
    _peca(o, 'valvula_mitral', 'Válvula mitral bicúspide', [.18, .08, -.05], [.28, .05, .28], '#e9ecef',
          'Válvula atrioventricular esquerda que impede o refluxo durante a sístole.', ('ventriculo_esquerdo', 'atrio_esquerdo'),
          group='internal', order=14, kind='ring', rot=(90, 0, 0), roughness=0.3, metalness=0.1)
    _peca(o, 'valvula_tricuspide', 'Válvula tricúspide atrioventricular', [-.18, .08, .08], [.28, .05, .28], '#e9ecef',
          'Válvula com três folhetos que separa átrio e ventrículo direitos.', ('ventriculo_direito', 'atrio_direito'),
          group='internal', order=15, kind='ring', rot=(90, 0, 0), roughness=0.3, metalness=0.1)
    _peca(o, 'valvula_aortica', 'Válvula aórtica semilunar', [.02, .28, 0], [.25, .05, .25], '#dee2e6',
          'Válvula que se abre sob alta pressão para permitir a ejeção sistêmica.', ('ventriculo_esquerdo', 'arco_aorta'),
          group='internal', order=16, kind='ring', rot=(90, 0, 0), roughness=0.3, metalness=0.1)
    steps = [dict(title='Músculo Cardíaco e Câmaras', text='O miocárdio ventricular bombeia o sangue oxigenado para o corpo.', selected='ventriculo_esquerdo', view='front'),
             dict(title='Grandes Vasos da Base', text='Arco da aorta e artéria pulmonar distribuem o fluxo sanguíneo arterial e venoso.', selected='arco_aorta', view='front'),
             dict(title='Circulação Venosa e Átrios', text='As veias cavas e veias pulmonares trazem o sangue de volta ao coração.', selected='veia_cava_superior', view='back'),
             dict(title='Visão Interna das Válvulas', text='Ative o modo Raio-X ou separe as peças para examinar as válvulas e o septo.', selected='valvula_mitral', exploded=True)]
    return _cena('coracao_humano', 'Coração humano anatômico',
                 'Coração humano anatômico: ventrículos, átrios, arco aórtico com ramos, artéria pulmonar, veias cavas e válvulas internas; modelo educativo aproximado.',
                 o, steps, 'coração humano anatômico')


def _carro_eletrico():
    o = []
    _peca(o, 'chassi_base', 'Quadro perimetral do chassi skateboard', [0, 0, 0], [1.3, .12, 2.6], '#495057',
          'Chassi espacial rígido em liga de alumínio fundido e extrudado que ancora os módulos; aproximação.',
          ('pack_bateria', 'motor_dianteiro', 'motor_traseiro', 'suspensao_de', 'suspensao_dd'),
          role='structural', group='external', order=1, metalness=0.8, roughness=0.3)
    _peca(o, 'pack_bateria', 'Compartimento selado de bateria 800V', [0, -.06, 0], [1.15, .16, 1.7], '#212529',
          'Gabinete estrutural blindado inferior com placas de refrigeração líquida.', ('chassi_base', 'modulos_bateria'),
          role='structural', group='external', order=2, metalness=0.7, roughness=0.35, explodeVector=[0, -.7, 0])
    _peca(o, 'modulos_bateria', 'Módulos internos de células Li-Ion', [0, -.04, 0], [1.0, .1, 1.55], '#0077b6',
          'Módulos de alta densidade energética operando em arquitetura ultra rápida de 800 volts.', ('pack_bateria', 'cabeamento_hv'),
          group='internal', order=3, roughness=0.3, metalness=0.6, emissive='#001133')
    _peca(o, 'cabeamento_hv', 'Barramentos elétricos de alta tensão', [0, .08, 0], [.18, .04, 2.1], '#f77f00',
          'Cabos blindados em laranja de segurança que conectam os motores à bateria.', ('motor_dianteiro', 'motor_traseiro'),
          group='internal', order=4, roughness=0.4, metalness=0.2)
    _peca(o, 'motor_dianteiro', 'Motor elétrico e inversor dianteiro PMSM', [0, .05, .95], [.55, .32, .45], '#343a40',
          'Motor síncrono de ímãs permanentes compacto com diferencial dianteiro integrado.', ('chassi_base', 'barra_direcao'),
          group='external', order=5, metalness=0.85, roughness=0.25, explodeVector=[0, .3, .9])
    _peca(o, 'motor_traseiro', 'Unidade de tração de alta potência traseira', [0, .05, -.95], [.62, .35, .48], '#343a40',
          'Motor elétrico traseiro com inversor de carbeto de silício (SiC) para torque imediato.', ('chassi_base',),
          group='external', order=6, metalness=0.85, roughness=0.25, explodeVector=[0, .3, -.9])
    _peca(o, 'barra_direcao', 'Caixa de direção elétrica dianteira', [0, .02, 1.15], [1.2, .08, .12], '#6c757d',
          'Mecanismo de cremalheira assistido eletronicamente com esterçamento preciso.', ('motor_dianteiro',),
          group='external', order=7, metalness=0.8, roughness=0.3)
    _peca(o, 'suspensao_de', 'Suspensão duplo A dianteira esquerda', [-.72, .02, 1.05], [.32, .15, .28], '#6c757d',
          'Braços de controle de alumínio forjado com amortecedor adaptativo.', ('chassi_base', 'roda_de'),
          role='structural', group='external', order=8, metalness=0.75, roughness=0.35, explodeVector=[-.5, .2, 0])
    _peca(o, 'suspensao_dd', 'Suspensão duplo A dianteira direita', [.72, .02, 1.05], [.32, .15, .28], '#6c757d',
          'Braço duplo A dianteiro direito.', ('chassi_base', 'roda_dd'),
          role='structural', group='external', order=9, metalness=0.75, roughness=0.35, explodeVector=[.5, .2, 0])
    _peca(o, 'suspensao_te', 'Suspensão multilink traseira esquerda', [-.72, .02, -1.05], [.32, .15, .28], '#6c757d',
          'Suspensão independente multibraço para máxima aderência em curvas.', ('chassi_base', 'roda_te'),
          role='structural', group='external', order=10, metalness=0.75, roughness=0.35, explodeVector=[-.5, .2, 0])
    _peca(o, 'suspensao_td', 'Suspensão multilink traseira direita', [.72, .02, -1.05], [.32, .15, .28], '#6c757d',
          'Suspensão multibraço traseira direita.', ('chassi_base', 'roda_td'),
          role='structural', group='external', order=11, metalness=0.75, roughness=0.35, explodeVector=[.5, .2, 0])
    _peca(o, 'pinca_de', 'Pinça de freio esportiva dianteira esquerda', [-.92, .08, 1.05], [.1, .16, .12], '#e63946',
          'Pinça monobloco de 6 pistões em vermelho de alto rendimento.', ('roda_de',),
          group='external', order=12, metalness=0.6, roughness=0.3, explodeVector=[-.9, 0, 0])
    _peca(o, 'pinca_dd', 'Pinça de freio esportiva dianteira direita', [.92, .08, 1.05], [.1, .16, .12], '#e63946',
          'Pinça dianteira direita esportiva.', ('roda_dd',),
          group='external', order=13, metalness=0.6, roughness=0.3, explodeVector=[.9, 0, 0])
    _peca(o, 'pinca_te', 'Pinça de freio esportiva traseira esquerda', [-.92, .08, -1.05], [.1, .16, .12], '#e63946',
          'Pinça traseira com acionamento do freio regenerativo.', ('roda_te',),
          group='external', order=14, metalness=0.6, roughness=0.3, explodeVector=[-.9, 0, 0])
    _peca(o, 'pinca_td', 'Pinça de freio esportiva traseira direita', [.92, .08, -1.05], [.1, .16, .12], '#e63946',
          'Pinça traseira direita esportiva.', ('roda_td',),
          group='external', order=15, metalness=0.6, roughness=0.3, explodeVector=[.9, 0, 0])
    _peca(o, 'roda_de', 'Roda dianteira esquerda aro 21 com pneu', [-.98, 0, 1.05], [.62, .62, .26], '#1c1f24',
          'Roda forjada esportiva com pneu de baixa resistência ao rolamento.', ('suspensao_de', 'pinca_de'),
          group='external', order=16, kind='cylinder', rot=(0, 0, 90), roughness=0.4, metalness=0.5, explodeVector=[-1.2, 0, .2])
    _peca(o, 'roda_dd', 'Roda dianteira direita aro 21 com pneu', [.98, 0, 1.05], [.62, .62, .26], '#1c1f24',
          'Roda forjada dianteira direita.', ('suspensao_dd', 'pinca_dd'),
          group='external', order=17, kind='cylinder', rot=(0, 0, 90), roughness=0.4, metalness=0.5, explodeVector=[1.2, 0, .2])
    _peca(o, 'roda_te', 'Roda traseira esquerda aro 21 com pneu', [-.98, 0, -1.05], [.62, .62, .26], '#1c1f24',
          'Roda forjada traseira esquerda larga para tração.', ('suspensao_te', 'pinca_te'),
          group='external', order=18, kind='cylinder', rot=(0, 0, 90), roughness=0.4, metalness=0.5, explodeVector=[-1.2, 0, -.2])
    _peca(o, 'roda_td', 'Roda traseira direita aro 21 com pneu', [.98, 0, -1.05], [.62, .62, .26], '#1c1f24',
          'Roda forjada traseira direita larga.', ('suspensao_td', 'pinca_td'),
          group='external', order=19, kind='cylinder', rot=(0, 0, 90), roughness=0.4, metalness=0.5, explodeVector=[1.2, 0, -.2])
    _peca(o, 'coluna_direcao', 'Coluna de direção e volante de comando', [.32, .52, .62], [.42, .42, .08], '#212529',
          'Volante estilo manche com controle digital fly-by-wire.', ('chassi_base',),
          group='external', order=20, kind='ring', rot=(25, 0, 0), roughness=0.3, metalness=0.6, explodeVector=[.4, .8, .6])
    steps = [dict(title='Chassi Skateboard e Bateria Estrutural', text='O piso plano acomoda o pack de baterias 800V rebaixando o centro de gravidade.', selected='chassi_base', view='top'),
             dict(title='Motores Elétricos Dianteiro e Traseiro', text='Tração integral (AWD) independente com resposta instantânea de torque.', selected='motor_traseiro', view='side'),
             dict(title='Suspensão Duplo A e Rodas de Alta Performance', text='Rodas de liga leve com pinças de freio esportivas e barra de direção.', selected='roda_de', view='front'),
             dict(title='Modo Explodido da Plataforma', text='Separação mecânica dos motores, pack de bateria, rodas e suspensões.', selected='pack_bateria', exploded=True)]
    return _cena('carro_eletrico', 'Plataforma EV Skateboard',
                 'Plataforma e chassi skate de veículo elétrico (EV Skateboard): pack estrutural de baterias 800V, dois motores elétricos dianteiro/traseiro, suspensões independentes e freios com pinças vermelhas; modelo educativo aproximado.',
                 o, steps, 'veículo elétrico skateboard')


_FABRICAS = {
    'xbox': _console_compacto,
    'console': _console_generico,
    'playstation': _console_escuro,
    'celular': _celular,
    'controle': _controle,
    'placa_mae': _placa_mae,
    'gabinete': _gabinete,
    'monitor': _monitor,
    'teclado': _teclado,
    'headset': _headset,
    'mesa': _mesa,
    'suporte_celular': _suporte_celular,
    'motor_v8': _motor_v8,
    'notebook': _notebook,
    'turbina_aviao': _turbina_aviao,
    'smartphone_desmontado': _smartphone_desmontado,
    'drone_quadricoptero': _drone_quadricoptero,
    'coracao_humano': _coracao_humano,
    'carro_eletrico': _carro_eletrico,
}


def cena(chave, education=None):
    """Cena nova do catálogo local. `education` sobrescreve a família."""
    fabrica = _FABRICAS.get(chave)
    if not fabrica:
        raise KeyError('Dispositivo fora do catálogo local: ' + str(chave))
    if education is None:
        return fabrica()
    return fabrica(education=education)


def cena_para_computador(texto):
    """Sub-cena específica para pedidos da família 'computer' (ou None)."""
    t = _norm(texto)
    if re.search(r'notebook|laptop', t):
        return _notebook(education='computer')
    if re.search(r'placa[- ]?mae|motherboard', t):
        return _placa_mae(education='computer')
    return None
