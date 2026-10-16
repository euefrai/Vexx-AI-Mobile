"""V5.3: contrato 3D limitado e comandos locais; nenhuma rede ou execução gráfica."""
import copy
import json
import math
import re
import unicodedata

KINDS = ('cube', 'sphere', 'cylinder', 'pyramid')
MODEL_ID = 'demo-cube'


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

    obj(p, 'id version title description objects model color scale rotation camera lighting annotations autoRotate details source')
    if type(p.get('version')) not in (int, float) or p['version'] != 1:
        raise ValueError('model3d: versão inválida')
    color = p.get('color', '#8b9cf7')
    if not isinstance(color, str) or not re.fullmatch(r'#[a-fA-F0-9]{6}', color):
        raise ValueError('model3d: cor inválida')
    model = p.get('model', '')
    if model not in ('', MODEL_ID):
        raise ValueError('model3d: modelo não autorizado')
    objects = p.get('objects', [])
    if not isinstance(objects, list) or not (0 if model else 1) <= len(objects) <= 8 or (model and objects):
        raise ValueError('model3d: use 1..8 primitivas ou um modelo autorizado')
    items, ids = [], set()
    for item in objects:
        obj(item, 'id kind position rotation scale label description')
        iid = ident(item.get('id'))
        if iid in ids or item.get('kind') not in KINDS:
            raise ValueError('model3d: objeto inválido ou duplicado')
        ids.add(iid)
        items.append(dict(id=iid, kind=item['kind'], position=vector(item.get('position', [0, 0, 0]), -3, 3),
                          rotation=vector(item.get('rotation', [0, 0, 0]), -360, 360),
                          scale=number(item.get('scale', 1), .25, 2),
                          label=string(item.get('label', item['kind']), 100),
                          description=string(item.get('description', ''), 500)))
    if model:
        ids.add(MODEL_ID)
    annotations = p.get('annotations', [])
    if not isinstance(annotations, list) or len(annotations) > 8:
        raise ValueError('model3d: anotações inválidas')
    notes = []
    for note in annotations:
        obj(note, 'objectId text')
        if note.get('objectId') not in ids:
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
    if re.search(r'\b(3d|tridimensional|girando)\b', t) and re.search(r'\b(mostr\w*|crie|exiba|quero|visualiz\w*)\b', t):
        kinds = [kind for word, kind in [('cubo', 'cube'), ('esfera', 'sphere'), ('cilindro', 'cylinder'), ('piramide', 'pyramid')]
                 if re.search(r'\b' + word + r's?\b', t)]
        return {'action': 'create', 'kinds': kinds, 'model': MODEL_ID if 'glb' in t and 'cubo' in t else '',
                'animate': 'girando' in t}
    return None


def respond(text, previous=None):
    req = request(text)
    if not req:
        return None
    if req['action'] == 'create':
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
    if previous is None:
        return None  # Sem referência 3D: não captura ações de PC/arquivos.
    props = copy.deepcopy(validate(previous))
    action = req['action']
    if action == 'rotate':
        props['rotation'][1] = (props['rotation'][1] + 45) % 360
        props['autoRotate'] = True
    elif action == 'zoom':
        props['camera']['distance'] = max(3, props['camera']['distance'] / 1.25)
    elif action == 'pause':
        props['autoRotate'] = False
    elif action == 'reset':
        props.update(rotation=[15, 25, 0], camera={'distance': 6}, autoRotate=False, details=False)
    elif action == 'details':
        props['details'] = True
    return {'rotate': 'Rotação ativada.', 'zoom': 'Visualização ampliada.', 'pause': 'Animação pausada.',
            'reset': 'Visualização restaurada.', 'details': 'Selecione uma parte para ler os detalhes disponíveis.'}[action], validate(props)
