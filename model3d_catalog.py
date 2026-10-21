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
    ('suporte_celular', r'suporte (?:de |para )?(?:celular|telefone)'),
    ('motor_v8', r'\bv8\b'),
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
          group='', order=0, kind='cube', rot=(0, 0, 0)):
    objects.append(dict(id=key, kind=kind, label=label, position=list(pos), dimensions=list(dims),
                        color=color, description=desc, related=list(related), role=role, group=group,
                        order=order, rotation=list(rot), metadata={'conceptual': True, 'note': NOTE}))


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
    _peca(o, 'bloco', 'Bloco do motor', [0, .1, 0], [1.6, .75, .9], '#4a5568',
          'Bloco em V: a disposição dos cilindros é conceitual.', ('tampa_esq', 'tampa_dir', 'cambota', 'admissao'),
          role='structural', group='external', order=1)
    _peca(o, 'tampa_esq', 'Tampa de válvulas esquerda', [0, .62, -.3], [1.5, .12, .5], '#5b6480',
          'Tampa ilustrativa do banco esquerdo.', ('bloco', 'cilindro_e1'), group='external', order=2, rot=(28, 0, 0))
    _peca(o, 'tampa_dir', 'Tampa de válvulas direita', [0, .62, .3], [1.5, .12, .5], '#5b6480',
          'Tampa ilustrativa do banco direito.', ('bloco', 'cilindro_d1'), group='external', order=3, rot=(-28, 0, 0))
    for i, x in enumerate((-.55, -.18, .18, .55), start=1):
        _peca(o, f'cilindro_e{i}', f'Cilindro esquerdo {i}', [x, .74, -.34], [.2, .34, .2], '#9aa0ae',
              'Cilindro ilustrativo do banco esquerdo.', ('tampa_esq', 'bloco'), group='internal',
              order=3 + i, kind='cylinder', rot=(28, 0, 0))
        _peca(o, f'cilindro_d{i}', f'Cilindro direito {i}', [x, .74, .34], [.2, .34, .2], '#9aa0ae',
              'Cilindro ilustrativo do banco direito.', ('tampa_dir', 'bloco'), group='internal',
              order=7 + i, kind='cylinder', rot=(-28, 0, 0))
    _peca(o, 'admissao', 'Admissão', [0, .82, 0], [1.2, .18, .5], '#5b6480',
          'Coletor de admissão entre os bancos.', ('bloco', 'tampa_esq', 'tampa_dir'), group='internal', order=12)
    _peca(o, 'cambota', 'Virabrequim', [0, -.05, 0], [.18, 1.25, .18], '#9aa0ae',
          'Eixo do virabrequim, girando no eixo do comprimento.', ('bloco',), group='internal', order=13,
          kind='cylinder', rot=(0, 0, 90))
    _peca(o, 'polia', 'Polia', [.92, -.05, 0], [.3, .06, .3], '#3a3f4c',
          'Polia na frente do motor.', ('cambota',), group='internal', order=14, kind='cylinder', rot=(0, 0, 90))
    steps = [dict(title='Bloco em V', text='Os dois bancos formam o V característico.', selected='bloco'),
             dict(title='Cilindros', text='Oito cilindros ilustrativos compõem os bancos.', selected='cilindro_e1'),
             dict(title='Virabrequim', text='O virabrequim é um eixo conceitual; sem movimento real.',
                  selected='cambota', exploded=True),
             dict(title='Montagem', text='Admissão e polia completam a visão educativa.', selected='admissao')]
    return _cena('motor-v8', 'Motor V8 ilustrativo',
                 'Composição educativa de um motor V8 em V; formas, ângulos e dimensões são aproximados, '
                 'sem qualquer precisão mecânica.', o, steps, 'motor V8 ilustrativo')


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
