"""V5.3: contrato 3D limitado e comandos locais; nenhuma rede ou execução gráfica."""
import copy
import json
import math
import re
import unicodedata

KINDS = ('cube', 'sphere', 'cylinder', 'pyramid')
MODEL_ID = 'demo-cube'
VIEWS = ('free', 'front', 'back', 'side', 'top')


def validate_interaction(state, ids, count):
    defaults = dict(selected='', hidden=[], isolated='', exploded=False, transparent=[],
                    view='free', focus='', step=0, speed=1, lessonPlaying=False)
    if not isinstance(state, dict) or set(state) - set(defaults):
        raise ValueError('Estado 3D desconhecido')
    s = dict(defaults, **state)
    for key in ('selected','isolated','focus'):
        if not isinstance(s[key], str) or (s[key] and s[key] not in ids):
            raise ValueError('Parte inexistente')
    for key in ('hidden','transparent'):
        if not isinstance(s[key],list) or len(s[key]) > 32 or any(not isinstance(v,str) or v not in ids for v in s[key]) or len(set(s[key])) != len(s[key]):
            raise ValueError('Lista de partes inválida')
    if s['view'] not in VIEWS or type(s['exploded']) is not bool or type(s['lessonPlaying']) is not bool:
        raise ValueError('Visualização inválida')
    if type(s['step']) not in (int,float) or not math.isfinite(s['step']) or int(s['step']) != s['step'] or not 0 <= s['step'] < max(count,1):
        raise ValueError('Etapa inexistente')
    if type(s['speed']) not in (int,float) or not math.isfinite(s['speed']) or not .5 <= s['speed'] <= 2:
        raise ValueError('Velocidade inválida')
    if s['lessonPlaying'] and not count:
        raise ValueError('Cena sem etapas')
    s['step'] = int(s['step'])
    return s


def validate(p):
    def obj(v, allowed):
        if not isinstance(v, dict) or set(v) - set(allowed.split()):
            raise ValueError('model3d: estrutura ou propriedade não autorizada')
        return v

    def string(v, limit):
        if not isinstance(v, str) or len(v) > limit:
            raise ValueError('model3d: texto inválido')
        return v

    def number(v, low, high):
        if type(v) not in (int, float) or not math.isfinite(v) or not low <= v <= high:
            raise ValueError('model3d: número fora do limite')
        return v

    def vector(v, low, high):
        if not isinstance(v, list) or len(v) != 3:
            raise ValueError('model3d: vetor inválido')
        return [number(n, low, high) for n in v]

    def ident(v):
        if not isinstance(v, str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,40}', v):
            raise ValueError('model3d: id inválido')
        return v

    def boolean(v):
        if type(v) is not bool:
            raise ValueError('model3d: booleano inválido')
        return v

    obj(p, 'id version title description objects model color scale rotation camera lighting annotations autoRotate details source education steps interaction')
    education = p.get('education', '')
    if education not in ('','computer','geometry','solar') or (not education and any(k in p for k in ('steps','interaction'))):
        raise ValueError('Cena educativa inválida')
    if type(p.get('version')) not in (int, float) or p['version'] != 1:
        raise ValueError('model3d: versão inválida')
    color = p.get('color', '#8b9cf7')
    if not isinstance(color, str) or not re.fullmatch(r'#[a-fA-F0-9]{6}', color):
        raise ValueError('model3d: cor inválida')
    model = p.get('model', '')
    if model not in ('', MODEL_ID):
        raise ValueError('model3d: modelo não autorizado')
    objects = p.get('objects', [])
    if not isinstance(objects, list) or not (0 if model else 1) <= len(objects) <= (32 if education else 8) or (model and (objects or education)):
        raise ValueError('model3d: use 1..8 primitivas ou um modelo autorizado')
    items, ids = [], set()
    for item in objects:
        obj(item, 'id kind position rotation scale label description' + (' dimensions color category related metadata' if education else ''))
        iid = ident(item.get('id'))
        if iid in ids or item.get('kind') not in KINDS:
            raise ValueError('model3d: objeto inválido ou duplicado')
        ids.add(iid)
        items.append(dict(id=iid, kind=item['kind'], position=vector(item.get('position', [0, 0, 0]), -3, 3),
                          rotation=vector(item.get('rotation', [0, 0, 0]), -360, 360),
                          scale=number(item.get('scale', 1), .25, 2),
                          label=string(item.get('label', item['kind']), 100),
                          description=string(item.get('description', ''), 500)))
        if education:
            meta = obj(item.get('metadata', {}), 'conceptual note')
            part_color = item.get('color', color)
            if not isinstance(part_color,str) or not re.fullmatch(r'#[a-fA-F0-9]{6}',part_color):
                raise ValueError('Cor da parte inválida')
            category = item.get('category','component')
            if category not in ('component','face','edge','vertex','body'):
                raise ValueError('Categoria inválida')
            items[-1].update(dimensions=vector(item.get('dimensions',[1,1,1]),.015,3),
                             color=part_color.lower(),category=category,related=item.get('related',[]),
                             metadata={'conceptual':boolean(meta.get('conceptual',True)), 'note':string(meta.get('note',''),200)})
    if model:
        ids.add(MODEL_ID)
    if education:
        for item in items:
            relations = item['related']
            if not isinstance(relations,list) or len(relations)>8 or any(not isinstance(v,str) or v not in ids or v==item['id'] for v in relations) or len(set(relations))!=len(relations):
                raise ValueError('Relação inválida')
    annotations = p.get('annotations', [])
    if not isinstance(annotations, list) or len(annotations) > 8:
        raise ValueError('model3d: anotações inválidas')
    notes = []
    for note in annotations:
        obj(note, 'objectId text')
        if not isinstance(note.get('objectId'),str) or note['objectId'] not in ids:
            raise ValueError('model3d: anotação sem objeto')
        notes.append(dict(objectId=note['objectId'], text=string(note.get('text'), 300)))
    camera = obj(p.get('camera', {}), 'distance')
    lighting = p.get('lighting', 'soft')
    if lighting not in ('soft', 'studio'):
        raise ValueError('model3d: iluminação inválida')
    source = 'Vexx AI — cubo GLB local original (CC0)' if model else 'Geometria procedural local'
    if 'source' in p and p['source'] != source:
        raise ValueError('model3d: fonte inválida')
    result = dict(id=ident(p.get('id')), version=1, title=string(p.get('title', 'Objeto 3D'), 120),
                description=string(p.get('description', 'Objeto tridimensional interativo.'), 500),
                objects=items, model=model, color=color.lower(), scale=number(p.get('scale', 1), .25, 2),
                rotation=vector(p.get('rotation', [15, 25, 0]), -360, 360),
                camera={'distance': number(camera.get('distance', 6), 3, 12)}, lighting=lighting,
                annotations=notes, autoRotate=boolean(p.get('autoRotate', False)),
                details=boolean(p.get('details', False)), source=source)
    if education:
        steps = p.get('steps',[])
        if not isinstance(steps,list) or len(steps)>8:
            raise ValueError('Etapas inválidas')
        normalized_steps = []
        for step in steps:
            obj(step, 'title text selected view exploded')
            s = validate_interaction({k:step[k] for k in ('selected','view','exploded') if k in step},ids,0)
            normalized_steps.append(dict(title=string(step.get('title','Etapa'),80),text=string(step.get('text',''),400),
                                         selected=s['selected'],view=s['view'],exploded=s['exploded']))
        result.update(education=education,steps=normalized_steps,
                      interaction=validate_interaction(p.get('interaction',{}),ids,len(steps)))
    if len(json.dumps(result, ensure_ascii=False, separators=(',', ':')).encode('utf-8')) > 20000:
        raise ValueError('model3d: cena excede 20 KB')
    return result


def request(text):
    t = ''.join(c for c in unicodedata.normalize('NFKD', text.lower()) if not unicodedata.combining(c))
    t = re.sub(r'^(lucas|luccas)[, :]+', '', t).strip().rstrip('.!?')
    commands = {'gire': 'rotate', 'amplie': 'zoom', 'restaure': 'reset', 'pause': 'pause',
                'mostre os detalhes': 'details', 'explique as partes desse objeto': 'details'}
    if t in commands:
        return {'action': commands[t]}
    if re.search(r'\b(arquivos?|pastas?|diretorios?|videos?|filmes?|codigo|mouse|navegador)\b', t):
        return None
    views = {'mostre a parte traseira':'back','vista traseira':'back','vista frontal':'front','mostre a frente':'front',
             'vista lateral':'side','vista superior':'top','mostre de cima':'top'}
    simple = {'separe as pecas':'explode','remonte as pecas':'assemble','revele todas as partes':'reveal',
              'volte ao passo anterior':'previous','proximo passo':'next','avance ao proximo passo':'next',
              'inicie a animacao educativa':'playLesson','pause a animacao':'pauseLesson'}
    if t in views:
        return {'action':'interact','op':'view','target':views[t]}
    if t in simple:
        return {'action':'interact','op':simple[t],'target':''}
    match = re.fullmatch(r'(destaque|selecione|isole|oculte|revele|foque|explique) (?:o |a |os |as )?(.+)',t)
    if match:
        return {'action':'interact','op':{'destaque':'select','selecione':'select','isole':'isolate','oculte':'hide','revele':'show','foque':'focus','explique':'explain'}[match[1]],'target':match[2]}
    match = re.fullmatch(r'deixe (?:o |a )?(.+) transparente',t)
    if match:
        return {'action':'interact','op':'transparent','target':match[1]}
    if re.search(r'\b(3d|tridimensional|girando)\b', t):
        verbs = re.search(
            r"\b(mostr\w*|cri\w*|exib\w*|quer\w*|visualiz\w*|vizualiz\w*|faz\w*|faca|mont\w*|"
            r"constru\w*|reconstru\w*|refac\w*|refaz\w*|recri\w*|gerar\w*|gere|"
            r"desenh\w*|renderiz\w*|modela\w*)\b", t)
        education = ('computer' if re.search(
            r'computador|\bpc\b|\bdesktop\b|\bnotebook\b|\blaptop\b|\bcpu\b|processador|placa[- ]?mae', t)
            else 'solar' if 'sistema solar' in t
            else 'geometry' if 'cubo' in t and re.search(r'didatico|faces|arestas|vertices|dimensoes', t)
            else '')
        kinds = [kind for word, kind in [('cubo', 'cube'), ('esfera', 'sphere'), ('cilindro', 'cylinder'), ('piramide', 'pyramid')]
                 if re.search(r'\b' + word + r's?\b', t)]
        model = MODEL_ID if 'glb' in t and 'cubo' in t else ''
        if verbs and education:
            return {'action':'create','education':education}
        if verbs and (kinds or model):
            return {'action': 'create', 'kinds': kinds, 'model': model, 'animate': 'girando' in t}
        # V5.4.1: continuações ("isso não está em 3D, reconstrua em 3D") não
        # podem cair no LLM nem virar arte ASCII: reconstroem a cena real.
        if re.search(r'\b(nao (esta|ta|e|ficou|ficava|parece)|reconstru\w*|refac\w*|refaz\w*|'
                     r'recri\w*|de verdade|realista)\b', t):
            return {'action': 'rebuild'}
        if verbs:
            return {'action': 'create', 'kinds': kinds, 'model': model, 'animate': 'girando' in t}
    return None


def respond(text, previous=None):
    req = request(text)
    if not req:
        return None
    if req['action'] == 'create':
        if req.get('education'):
            from model3d_education import scene
            return 'Cena educativa preparada. Abra o 3D para explorar as partes.', validate(scene(req['education']))
        if not req['kinds']:
            return 'Nesta versão posso mostrar cubo, esfera, cilindro e pirâmide em 3D. Não tenho um modelo autorizado desse objeto.', None
        labels = dict(cube='Cubo', sphere='Esfera', cylinder='Cilindro', pyramid='Pirâmide')
        props = {'id': 'scene', 'version': 1, 'title': ' · '.join(labels[k] for k in req['kinds']),
                 'model': req['model'], 'autoRotate': req['animate'], 'objects': []}
        if not req['model']:
            for i, kind in enumerate(req['kinds']):
                props['objects'].append({'id': kind, 'kind': kind, 'label': labels[kind],
                                        'position': [(i - (len(req['kinds']) - 1) / 2) * 1.8, 0, 0],
                                        'description': 'Primitiva geométrica: ' + labels[kind].lower() + '.'})
        return 'Arraste para girar, use o zoom e selecione um objeto para ver seus detalhes.', validate(props)
    if req['action'] == 'rebuild':
        if previous is None:
            return None  # cmd_model3d decide o que reconstruir (pedido anterior)
        props = copy.deepcopy(validate(previous))
        props['autoRotate'] = True
        return 'Cena reconstruída em 3D. Arraste para girar e toque nas partes para explorar.', validate(props)
    if previous is None:
        return None  # Sem referência 3D: não captura ações de PC/arquivos.
    props = copy.deepcopy(validate(previous))
    action = req['action']
    if action == 'interact':
        return interact(props, req)
    if action == 'rotate':
        props['rotation'][1] = (props['rotation'][1] + 45) % 360
        props['autoRotate'] = True
    elif action == 'zoom':
        props['camera']['distance'] = max(3, props['camera']['distance'] / 1.25)
    elif action == 'pause':
        props['autoRotate'] = False
        if props.get('education'):
            props['interaction']['lessonPlaying'] = False
    elif action == 'reset':
        props.update(rotation=[15, 25, 0], camera={'distance': 6}, autoRotate=False, details=False)
        if props.get('education'):
            props['interaction'] = validate_interaction({},[o['id'] for o in props['objects']],len(props['steps']))
    elif action == 'details':
        props['details'] = True
    return {'rotate': 'Rotação ativada.', 'zoom': 'Visualização ampliada.', 'pause': 'Animação pausada.',
            'reset': 'Visualização restaurada.', 'details': 'Selecione uma parte para ler os detalhes disponíveis.'}[action], validate(props)


def interact(props, request):
    if not props.get('education'):
        return 'Essa cena não possui partes educativas ou operações avançadas. Peça um computador simplificado ou um cubo didático em 3D.', None
    s, op = props['interaction'], request['op']
    norm = lambda t: ''.join(c for c in unicodedata.normalize('NFKD',t.lower()) if not unicodedata.combining(c)).replace('-',' ')
    target = norm(request['target'])
    aliases = {'memoria ram':'ram','placa mae':'motherboard','processador':'cpu','placa de video':'gpu'}
    target = aliases.get(target,target)
    part = next((o for o in props['objects'] if target in (norm(o['id']),norm(o['label']))),None)
    if op in ('select','isolate','hide','show','focus','explain','transparent'):
        if not part:
            return 'Não encontrei essa parte na cena ativa. Use um dos nomes exibidos em Partes; não posso inferir componentes inexistentes.', None
        key = part['id']; s['selected'] = key
        if op == 'isolate': s['isolated'] = key
        elif op == 'hide': s['hidden'] = list(dict.fromkeys(s['hidden']+[key]))
        elif op == 'transparent': s['transparent'] = list(dict.fromkeys(s['transparent']+[key]))
        elif op == 'focus': s['focus'] = key
        if op in ('show','select','focus','isolate','explain'):
            s['hidden'] = [k for k in s['hidden'] if k != key]
            if op != 'isolate': s['isolated'] = ''
        props['details'] = True
        text = part['label'] + ': ' + part['description'] if op == 'explain' else 'Ajuste visual preparado para ' + part['label'] + '.'
    elif op in ('explode','assemble'):
        if len(props['objects']) < 2:
            return 'A cena precisa de pelo menos duas partes para separar peças.',None
        s['exploded'] = op == 'explode'; text = 'Separação das peças preparada.' if s['exploded'] else 'Remontagem preparada.'
    elif op == 'reveal':
        s.update(hidden=[],isolated='',transparent=[]); text = 'Restauração da visibilidade preparada.'
    elif op == 'view':
        if request['target'] not in VIEWS: return 'Vista não suportada.',None
        s.update(view=request['target'],focus=''); text = 'Vista preparada.'
    elif op in ('next','previous','playLesson','pauseLesson'):
        if not props['steps']: return 'Esta cena não possui uma sequência educativa.',None
        if op in ('next','previous'):
            step = s['step']+(1 if op=='next' else -1)
            if not 0<=step<len(props['steps']): return 'Você já está na primeira etapa.' if step<0 else 'Você já está na última etapa.',None
            s['step'] = step; s['lessonPlaying'] = False
        else: s['lessonPlaying'] = op == 'playLesson'
        step = props['steps'][s['step']]
        s.update({k:step[k] for k in ('selected','view','exploded')})
        s.update(hidden=[],isolated='',focus='')
        text = step['title'] + ': ' + step['text']
    else:
        return 'Essa operação visual não é suportada nesta versão.',None
    return text, validate(props)
