"""VEXX AI — Generative 3D Architect (model3d_generative.py)

Permite criar modelos 3D realistas, ricos em componentes e interativos
de praticamente qualquer objeto, equipamento mecânico, científico ou anatômico.

Cada modelo gerado inclui:
- PBR Materials (rugosidade, metalicidade, opacidade, emissividade).
- Exploded Views direccionais (explodeVector por eixo mecânico).
- Separação semântica (peças internas vs carcaça externa / estrutural).
- Etapas educativas interativas (Bill of Materials / montagem).
- Validação estrita por `model3d.validate()`.
"""

import json
import math
import re
import unicodedata
import model3d
import model3d_catalog


def _norm(texto):
    return ''.join(c for c in unicodedata.normalize('NFKD', (texto or '').lower())
                   if not unicodedata.combining(c))


def _clean_slug(texto):
    s = _norm(texto)
    s = re.sub(r'[^a-z0-9]+', '_', s).strip('_')
    return s[:35] or 'objeto_3d'


def _peca(objects, key, label, pos, dims, color, desc, related=(), role='functional',
          group='', order=0, kind='cube', rot=(0, 0, 0),
          roughness=0.45, metalness=0.15, opacity=1.0, transparent=False,
          wireframe=False, emissive=None, explodeVector=None):
    p = dict(id=key, kind=kind, label=label, position=list(pos), dimensions=list(dims),
             color=color, description=desc, related=list(related), role=role, group=group,
             order=order, rotation=list(rot),
             metadata={'conceptual': True, 'note': 'Arquiteto Generativo 3D VEXX AI'})
    if roughness is not None:
        p['roughness'] = max(0.0, min(1.0, float(roughness)))
    if metalness is not None:
        p['metalness'] = max(0.0, min(1.0, float(metalness)))
    if opacity is not None and opacity < 1.0:
        p['opacity'] = max(0.0, min(1.0, float(opacity)))
        p['transparent'] = True
    elif transparent:
        p['transparent'] = True
        p['opacity'] = 0.5
    if wireframe:
        p['wireframe'] = True
    if emissive:
        p['emissive'] = emissive
    if explodeVector is not None:
        p['explodeVector'] = [round(float(v), 2) for v in explodeVector]
    objects.append(p)


# =====================================================================
# ARQUÉTIPOS PROCEDURAIS ESPECIAIS (Engenharia, Espaço e Ciência)
# =====================================================================

def _satelite_orbital():
    o = []
    _peca(o, 'chassi_bus', 'Estrutura Central do Barramento (Bus)', [0, 0, 0], [0.9, 1.2, 0.9], '#343a40',
          'Chassi cúbico de suporte com mantas térmicas de isolamento multicamadas (MLI) e barramentos.',
          ('painel_esq', 'painel_dir', 'antena_dish', 'propulsor_ionico'),
          role='structural', group='external', order=1, metalness=0.8, roughness=0.3)
    _peca(o, 'painel_esq', 'Asa Solar Fotovoltaica Esquerda', [-1.6, 0, 0], [1.8, 0.04, 0.85], '#1d3557',
          'Painel de células solares de arsenieto de gálio com eficiência de 32% e rotação solar.', ('chassi_bus',),
          role='functional', group='external', order=2, metalness=0.6, roughness=0.2, explodeVector=[-1.2, 0, 0])
    _peca(o, 'painel_dir', 'Asa Solar Fotovoltaica Direita', [1.6, 0, 0], [1.8, 0.04, 0.85], '#1d3557',
          'Painel fotovoltaico direito para geração de energia de órbita.', ('chassi_bus',),
          role='functional', group='external', order=3, metalness=0.6, roughness=0.2, explodeVector=[1.2, 0, 0])
    _peca(o, 'antena_dish', 'Antena Refletora Parabólica de Banda Ka', [0, 0.85, 0.35], [0.75, 0.75, 0.2], '#e9ecef',
          'Refletor de comunicações de alto ganho com terra para telemetria e dados científicos.', ('chassi_bus',),
          role='functional', group='external', order=4, kind='ring', rot=(35, 0, 0), metalness=0.85, roughness=0.2, explodeVector=[0, 0.8, 0.6])
    _peca(o, 'feedhorn', 'Alimentador do Refletor da Antena', [0, 1.1, 0.52], [0.12, 0.25, 0.12], '#e63946',
          'Guia de onda alimentador focal.', ('antena_dish',),
          group='external', order=5, kind='cylinder', rot=(35, 0, 0), metalness=0.9, roughness=0.2, explodeVector=[0, 1.0, 0.8])
    _peca(o, 'telescopio_payload', 'Payload Óptico / Câmera Multiespectral', [0, 0, 0.48], [0.42, 0.42, 0.35], '#212529',
          'Conjunto de espelhos e sensores CMOS de alta resolução para observação da Terra.', ('chassi_bus',),
          group='external', order=6, kind='cylinder', rot=(90, 0, 0), metalness=0.8, roughness=0.2, explodeVector=[0, 0, 0.8])
    _peca(o, 'propulsor_ionico', 'Propulsor Iônico a Plasma de Efeito Hall', [0, -0.65, 0], [0.38, 0.32, 0.38], '#495057',
          'Sistema de propulsão elétrica para manutenção de órbita com gás xenônio ionizado.', ('chassi_bus',),
          group='external', order=7, kind='cylinder', emissive='#00b4d8', metalness=0.9, roughness=0.2, explodeVector=[0, -0.7, 0])
    _peca(o, 'rodas_reacao', 'Rodas de Reação de Controle de Atitude (ADCS)', [0, 0.15, 0], [0.55, 0.55, 0.55], '#457b9d',
          'Três volantes de inércia ortogonais para estabilização giroscópica de 3 eixos.', ('chassi_bus',),
          group='internal', order=8, metalness=0.7, roughness=0.3)
    _peca(o, 'computador_bordo', 'Computador de Bordo e Rádios (OBC)', [0, -0.15, 0], [0.65, 0.35, 0.65], '#2a9d8f',
          'Módulos eletrônicos redundantes com tolerância à radiação cósmica.', ('chassi_bus',),
          group='internal', order=9, metalness=0.5, roughness=0.4)
    _peca(o, 'tanque_xenonio', 'Tanque de Xenônio Comprimido em Titânio', [0, -0.38, 0], [0.45, 0.45, 0.45], '#e76f51',
          'Esfera de titânio envolta em fibra de carbono para armazenar o propelente gasoso.', ('propulsor_ionico',),
          group='internal', order=10, kind='sphere', metalness=0.7, roughness=0.3)
    steps = [
        dict(title='Barramento e Cargas Úteis', text='O corpo central acomoda os sistemas de energia, navegação e carga científica.', selected='chassi_bus', view='front'),
        dict(title='Painéis Solares Orientáveis', text='Geração de energia elétrica com até 1.8m de envergadura por asa.', selected='painel_esq', view='top'),
        dict(title='Comunicações e Propulsão Hall', text='Antena parabólica focal e motor elétrico de propulsão iônica.', selected='antena_dish', view='side'),
        dict(title='Desmontagem Orbital', text='Visão interna das rodas de reação giroscópicas e tanque de xenônio.', selected='rodas_reacao', exploded=True, xray=True)
    ]
    return dict(id='dev-satelite_orbital', version=1, title='Satélite Orbital de Observação e Telecomunicações',
                description='Modelo tridimensional educativo aproximado de um satélite de órbita baixa com painéis solares, antena parabólica, propulsor iônico e aviônica interna.',
                education='aviation', precision='aproximado',
                source='Catálogo local V5.6 — satélite orbital', objects=o, steps=steps,
                rotation=[18, 26, 0], details=True)


def _microscopio_optico():
    o = []
    _peca(o, 'base_pesada', 'Base Fundida Estabilizadora', [0, -0.85, 0], [1.3, 0.22, 1.4], '#212529',
          'Base maciça de ferro fundido com pés emborrachados antivibração.', ('haste_coluna', 'fonte_luz'),
          role='structural', group='external', order=1, metalness=0.7, roughness=0.4)
    _peca(o, 'haste_coluna', 'Braço Curvo Estrutural', [0, -0.05, -0.45], [0.35, 1.45, 0.42], '#212529',
          'Coluna curvada de sustentação ergonômica com comandos coaxiais macrométrico e micrométrico.', ('base_pesada', 'platina_stage', 'cabecote_tubo'),
          role='structural', group='external', order=2, metalness=0.7, roughness=0.4)
    _peca(o, 'platina_stage', 'Platina Mecânica com Charriot', [0, -0.22, 0.05], [1.1, 0.1, 0.95], '#343a40',
          'Mesa de suporte para lâminas biológicas com garras metálicas e pinça micrométrica X-Y.', ('haste_coluna', 'condensador_abbe'),
          role='functional', group='external', order=3, metalness=0.8, roughness=0.3, explodeVector=[0, -0.3, 0.3])
    _peca(o, 'condensador_abbe', 'Condensador de Abbe com Diafragma Íris', [0, -0.42, 0.05], [0.42, 0.25, 0.42], '#495057',
          'Sistema óptico de lentes que concentra e foca o feixe de luz sob a lâmina.', ('platina_stage', 'fonte_luz'),
          group='internal', order=4, kind='cylinder', metalness=0.85, roughness=0.25)
    _peca(o, 'fonte_luz', 'Iluminador LED de Campo Claro', [0, -0.72, 0.05], [0.38, 0.16, 0.38], '#f8f9fa',
          'Fonte emissora ajustável com temperatura de cor próxima à luz solar.', ('base_pesada',),
          group='external', order=5, kind='cylinder', emissive='#ffeeaa', metalness=0.5, roughness=0.3)
    _peca(o, 'revolver_objetivas', 'Revólver Quádruplo Giratório', [0, 0.18, 0.05], [0.65, 0.15, 0.65], '#ced4da',
          'Disco giratório porta-objetivas com encaixes de precisão paracentral.', ('cabecote_tubo', 'objetiva_10x', 'objetiva_40x', 'objetiva_100x'),
          group='external', order=6, kind='cylinder', metalness=0.9, roughness=0.15, explodeVector=[0, 0.2, 0])
    _peca(o, 'objetiva_10x', 'Objetiva Acromática 10x (Amarela)', [0, 0.02, 0.22], [0.14, 0.24, 0.14], '#ffd166',
          'Lente de ampliação média.', ('revolver_objetivas',),
          group='external', order=7, kind='cylinder', metalness=0.85, roughness=0.2, explodeVector=[0, -0.3, 0.3])
    _peca(o, 'objetiva_40x', 'Objetiva de Alta Resolução 40x (Azul)', [-0.18, 0.02, -0.05], [0.14, 0.26, 0.14], '#118ab2',
          'Lente de alta ampliação para análise celular.', ('revolver_objetivas',),
          group='external', order=8, kind='cylinder', metalness=0.85, roughness=0.2, explodeVector=[-0.4, -0.3, -0.1])
    _peca(o, 'objetiva_100x', 'Objetiva de Imersão em Óleo 100x (Branca)', [0.18, 0.02, -0.05], [0.14, 0.28, 0.14], '#e9ecef',
          'Objetiva para resolução máxima com óleo mineral.', ('revolver_objetivas',),
          group='external', order=9, kind='cylinder', metalness=0.85, roughness=0.2, explodeVector=[0.4, -0.3, -0.1])
    _peca(o, 'cabecote_tubo', 'Cabeçote Binocular Inclinado a 30°', [0, 0.55, -0.12], [0.72, 0.45, 0.65], '#212529',
          'Tubo óptico com prismas internos para divisão binocular.', ('haste_coluna', 'ocular_esq', 'ocular_dir'),
          group='external', order=10, metalness=0.7, roughness=0.35, explodeVector=[0, 0.5, 0])
    _peca(o, 'ocular_esq', 'Ocular Grande Campo 10x Esquerda', [-0.22, 0.88, 0.05], [0.16, 0.35, 0.16], '#343a40',
          'Lente ocular com ajuste dióptrico.', ('cabecote_tubo',),
          group='external', order=11, kind='cylinder', rot=(30, 0, 0), metalness=0.8, roughness=0.25, explodeVector=[-0.3, 0.8, 0.2])
    _peca(o, 'ocular_dir', 'Ocular Grande Campo 10x Direita', [0.22, 0.88, 0.05], [0.16, 0.35, 0.16], '#343a40',
          'Lente ocular direita.', ('cabecote_tubo',),
          group='external', order=12, kind='cylinder', rot=(30, 0, 0), metalness=0.8, roughness=0.25, explodeVector=[0.3, 0.8, 0.2])
    steps = [
        dict(title='Estrutura Óptica e Mecânica', text='O microscópio combina alinhamento óptico micrométrico com iluminação regulada.', selected='haste_coluna', view='front'),
        dict(title='Mesa Mecânica e Condensador', text='A platina charriot permite deslocar lâminas em frações de mícron sob o condensador de Abbe.', selected='platina_stage', view='side'),
        dict(title='Revólver e Objetivas Acromáticas', text='Seleção rápida entre ampliações de 10x, 40x e 100x de imersão.', selected='revolver_objetivas', view='front'),
        dict(title='Desmontagem dos Elementos Ópticos', text='Separação de oculares, revólver, objetivas e condensador.', selected='revolver_objetivas', exploded=True)
    ]
    return dict(id='dev-microscopio_optico', version=1, title='Microscópio Óptico de Pesquisa Binocular',
                description='Modelo tridimensional educativo aproximado de um microscópio óptico com cabeçote binocular, revólver de objetivas, platina com charriot mecânico e iluminação.',
                education='biology', precision='aproximado',
                source='Catálogo local V5.6 — microscópio óptico', objects=o, steps=steps,
                rotation=[18, 26, 0], details=True)


def _robo_braco_industrial():
    o = []
    _peca(o, 'base_pedestal', 'Pedestal de Ancoragem e Primeiro Eixo (J1)', [0, -0.85, 0], [1.1, 0.35, 1.1], '#fca311',
          'Base flangeada com servomotor de rotação azimutal contínua de 360 graus.', ('ombro_j2',),
          role='structural', group='external', order=1, kind='cylinder', metalness=0.75, roughness=0.3)
    _peca(o, 'ombro_j2', 'Articulação do Ombro com Redutor Cicloidal (J2)', [0, -0.45, 0], [0.65, 0.55, 0.65], '#14213d',
          'Mancal com redutor harmônico de alta rigidez para elevação do braço principal.', ('base_pedestal', 'braco_inferior'),
          role='structural', group='external', order=2, kind='cylinder', rot=(0, 0, 90), metalness=0.8, roughness=0.25, explodeVector=[0, 0.4, 0])
    _peca(o, 'braco_inferior', 'Braço de Elevação Inferior de Fundição Leve', [0, 0.05, 0], [0.38, 0.95, 0.42], '#fca311',
          'Segmento estrutural fundido oco com passagens internas para cabos e servoacionamentos.', ('ombro_j2', 'cotovelo_j3'),
          role='structural', group='external', order=3, metalness=0.75, roughness=0.3)
    _peca(o, 'cotovelo_j3', 'Articulação do Cotovelo (J3)', [0, 0.58, 0], [0.55, 0.45, 0.55], '#14213d',
          'Terceiro eixo de liberdade mecânica com encoder absoluto óptico.', ('braco_inferior', 'braco_superior'),
          group='external', order=4, kind='cylinder', rot=(0, 0, 90), metalness=0.8, roughness=0.25, explodeVector=[0, 0.5, 0])
    _peca(o, 'braco_superior', 'Braço Superior e Antebraço (J4)', [0, 0.88, 0.25], [0.32, 0.32, 0.85], '#fca311',
          'Segmento tubular cilíndrico de alta velocidade.', ('cotovelo_j3', 'punho_j5'),
          group='external', order=5, kind='cylinder', rot=(90, 0, 0), metalness=0.75, roughness=0.3)
    _peca(o, 'punho_j5', 'Conjunto Articulado do Pulso (J5)', [0, 0.88, 0.72], [0.38, 0.38, 0.28], '#14213d',
          'Quinto eixo de inclinação da ferramenta com proteção IP67.', ('braco_superior', 'flange_j6'),
          group='external', order=6, kind='cylinder', rot=(0, 0, 90), metalness=0.85, roughness=0.2, explodeVector=[0, 0, 0.4])
    _peca(o, 'flange_j6', 'Flange Rotativa de Acoplamento (J6)', [0, 0.88, 0.92], [0.32, 0.32, 0.12], '#e5e5e5',
          'Flange padronizada ISO para fixação de ferramentas de solda, corte ou garra.', ('punho_j5', 'garra_pinca'),
          group='external', order=7, kind='cylinder', rot=(90, 0, 0), metalness=0.9, roughness=0.15, explodeVector=[0, 0, 0.6])
    _peca(o, 'garra_pinca', 'Efetuador Terminal: Garra Paralela Pneumática', [0, 0.88, 1.15], [0.45, 0.24, 0.32], '#212529',
          'Garra de precisão industrial com dedos emborrachados para manipulação rápida.', ('flange_j6',),
          group='external', order=8, metalness=0.8, roughness=0.3, explodeVector=[0, 0, 0.9])
    _peca(o, 'motor_servodrive', 'Servomotores Brushless Internos', [0, -0.05, 0], [0.26, 0.55, 0.26], '#457b9d',
          'Motores elétricos AC síncronos de resposta ultrarrápida embutidos no chassi.', ('braco_inferior',),
          group='internal', order=9, kind='cylinder', metalness=0.9, roughness=0.2)
    _peca(o, 'controlador_base', 'Módulo de Comunicação de Campo e Barramento', [0, -0.85, -0.35], [0.45, 0.25, 0.25], '#264653',
          'Interface para barramentos industriais PROFINET e EtherCAT.', ('base_pedestal',),
          group='internal', order=10, metalness=0.6, roughness=0.4)
    steps = [
        dict(title='Braço Robótico de 6 Graus de Liberdade', text='Arquitetura antropomórfica articulada para automação de alta repetibilidade (±0.02mm).', selected='braco_inferior', view='front'),
        dict(title='Mancais e Redutores Cicloidais', text='Os eixos J1, J2 e J3 suportam as maiores cargas dinâmicas de aceleração.', selected='ombro_j2', view='side'),
        dict(title='Pulso Articulado e Garra Terminal', text='Os eixos J4, J5 e J6 posicionam a garra paralela com orientação tridimensional precisa.', selected='flange_j6', view='top'),
        dict(title='Desmontagem Cinemática', text='Separação dos elos mecânicos e exibição dos servomotores internos.', selected='garra_pinca', exploded=True)
    ]
    return dict(id='dev-robo_braco_industrial', version=1, title='Braço Robótico Articulado Industrial (6 Eixos)',
                description='Modelo tridimensional educativo aproximado de um robô industrial articulado de 6 graus de liberdade com garra pneumática paralela e servomotores internos.',
                education='robotics', precision='aproximado',
                source='Catálogo local V5.6 — braço robótico industrial', objects=o, steps=steps,
                rotation=[18, 26, 0], details=True)


# =====================================================================
# ARQUITETO PROCEDURAL UNIVERSAL (Para qualquer objeto solicitado)
# =====================================================================

def _gerar_procedural_universal(termo_busca: str) -> dict:
    """Gera um modelo 3D mecânico rico e detalhado para qualquer assunto não-catalogado."""
    slug = _clean_slug(termo_busca)
    titulo = f'{termo_busca.title()} (Modelo 3D Interativo VEXX)'
    desc = f'Composição tridimensional realista e aproximada de {termo_busca}, com peças estruturais, componentes internos, materiais PBR e separação explodida.'

    o = []
    # 1. Carcaça / Estrutura Base
    _peca(o, 'estrutura_base', 'Chassi / Estrutura Principal', [0, 0, 0], [1.8, 1.0, 1.2], '#3a404d',
          f'Estrutura principal e chassi de sustentação de {termo_busca}.',
          ('tampa_superior', 'painel_frontal', 'nucleo_interno'),
          role='structural', group='external', order=1, metalness=0.75, roughness=0.3)

    # 2. Tampa Superior
    _peca(o, 'tampa_superior', 'Carenagem / Cobertura Superior', [0, 0.65, 0], [1.75, 0.22, 1.15], '#2b303a',
          'Cobertura de proteção superior com vedação e travas mecânicas.', ('estrutura_base',),
          role='structural', group='external', order=2, metalness=0.7, roughness=0.35, explodeVector=[0, 0.9, 0])

    # 3. Painel Frontal / Interface
    _peca(o, 'painel_frontal', 'Painel Frontal / Controles', [0, 0, 0.65], [1.6, 0.75, 0.12], '#1e2128',
          'Painel de comando frontal com botões e indicadores operacionais.', ('estrutura_base', 'visor_display'),
          group='external', order=3, metalness=0.6, roughness=0.3, explodeVector=[0, 0, 0.8])

    # 4. Display / Indicador LED
    _peca(o, 'visor_display', 'Display / Indicador de Operação', [0, 0.18, 0.72], [0.8, 0.35, 0.05], '#00b4d8',
          'Área de visualização digital com dados em tempo real.', ('painel_frontal',),
          group='external', order=4, emissive='#005577', metalness=0.3, roughness=0.1, explodeVector=[0, 0, 1.1])

    # 5. Núcleo Interno / Mecanismo Principal
    _peca(o, 'nucleo_interno', 'Mecanismo / Módulo Principal', [0, -0.05, 0], [1.2, 0.6, 0.8], '#adb5bd',
          'Coração operacional e conjunto mecânico central.', ('estrutura_base', 'eixo_rotor', 'placa_circuito'),
          role='functional', group='internal', order=5, kind='cylinder', metalness=0.9, roughness=0.2)

    # 6. Eixo / Rotor Central
    _peca(o, 'eixo_rotor', 'Eixo de Transmissão / Rotor', [0, -0.05, 0], [0.25, 0.25, 1.4], '#ced4da',
          'Eixo forjado de alta precisão para transmissão mecânica.', ('nucleo_interno',),
          role='functional', group='internal', order=6, kind='cylinder', rot=(90, 0, 0), metalness=0.95, roughness=0.15)

    # 7. Placa de Controle e Potência
    _peca(o, 'placa_circuito', 'Placa de Controle / PCB', [0, -0.38, 0], [1.4, 0.06, 0.9], '#2d6a4f',
          'Placa eletrônica com circuitos integrados reguladores e sensores.', ('nucleo_interno',),
          group='internal', order=7, metalness=0.5, roughness=0.4, explodeVector=[0, -0.5, 0])

    # 8. Módulo de Alimentação / Bateria
    _peca(o, 'modulo_energia', 'Módulo de Força / Bateria', [-0.55, -0.15, -0.3], [0.45, 0.45, 0.45], '#e76f51',
          'Unidade reguladora de energia e alimentação.', ('placa_circuito',),
          group='internal', order=8, metalness=0.6, roughness=0.4)

    # 9. Conectores Traseiros
    _peca(o, 'conexoes_traseiras', 'Conexões e Entradas Traseiras', [0, 0, -0.65], [1.2, 0.45, 0.1], '#212529',
          'Portas de dados e conexões elétricas traseiras.', ('estrutura_base',),
          group='external', order=9, metalness=0.8, roughness=0.3, explodeVector=[0, 0, -0.8])

    # 10. Apoios e Pés Antivibração
    _peca(o, 'apoios_base', 'Sapatas / Pés de Fixação', [0, -0.55, 0], [1.6, 0.08, 1.0], '#14161c',
          'Apoios em elastômero para isolamento acústico e estabilidade.', ('estrutura_base',),
          role='structural', group='external', order=10, roughness=0.8, metalness=0.1, explodeVector=[0, -0.8, 0])

    steps = [
        dict(title=f'Visão Geral de {termo_busca.title()}', text='Estrutura equilibrada com chassi perimetral e acabamento de alta precisão.', selected='estrutura_base', view='front'),
        dict(title='Painel Frontal e Interface', text='Controles externos e visor operacional com iluminação ativa.', selected='painel_frontal', view='front'),
        dict(title='Mecanismo e Eletrônica Interna', text='Núcleo de operação e placa de controle protegidos na cavidade interna.', selected='nucleo_interno', view='side'),
        dict(title='Desmontagem Explodida Direcional', text='Separação mecânica em todos os eixos funcionais para inspeção das peças.', selected='tampa_superior', exploded=True, xray=True)
    ]

    return dict(id=f'dev-{slug}', version=1, title=titulo, description=desc,
                education='device', precision='aproximado',
                source=f'Catálogo local V5.6 — {termo_busca[:40]}', objects=o, steps=steps,
                rotation=[18, 26, 0], details=True)


# =====================================================================
# PONTO DE ENTRADA PÚBLICO
# =====================================================================

def gerar_modelo_3d(prompt: str) -> dict:
    """Ponto de entrada central para geração e resolução de modelos 3D sob demanda.

    Verifica o catálogo nativo, os arquétipos avançados de engenharia/ciência
    e, se necessário, sintetiza uma montagem mecânica procedural completa.
    """
    t_norm = _norm(prompt)

    # 1. Catálogo local rápido
    chave_catalogo = model3d_catalog.resolver(t_norm)
    if chave_catalogo and chave_catalogo in model3d_catalog._FABRICAS:
        return model3d.validate(model3d_catalog.cena(chave_catalogo))

    # 2. Arquétipos especiais de alta fidelidade
    if re.search(r'satelite|sonda orbital|satelite artificial', t_norm):
        return model3d.validate(_satelite_orbital())
    if re.search(r'microscopio|lupa eletronica|lente de pesquisa', t_norm):
        return model3d.validate(_microscopio_optico())
    if re.search(r'robo industrial|braco robotico|braco articulado|kuka|fanuc', t_norm):
        return model3d.validate(_robo_braco_industrial())

    # 3. Assunto extraído para construção procedural completa
    assunto = model3d_catalog.assunto(t_norm) or prompt.strip(' !.?')
    cena_sintetizada = _gerar_procedural_universal(assunto)
    return model3d.validate(cena_sintetizada)
