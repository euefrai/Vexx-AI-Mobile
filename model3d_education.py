"""Catálogo educativo procedural original; medidas ilustrativas, sem compatibilidade real."""
def scene(kind):
    objects, steps = [], []
    def part(key, name, category, position, dimensions, color, description, related=()):
        objects.append(dict(id=key, kind='sphere' if category in ('vertex','body') else 'cube',
                            label=name, category=category, position=position, dimensions=dimensions,
                            color=color, description=description, related=list(related),
                            metadata={'conceptual':True, 'note':'Ilustração educativa original.'}))
    if kind == 'computer':
        title = 'Computador simplificado'
        description = 'Ilustração conceitual: disposição, medidas e conexões não demonstram compatibilidade real entre peças.'
        part('motherboard','Placa-mãe','component',[0,0,0],[2.5,.12,2.5],'#4b9c80',
             'A placa-mãe conecta componentes por circuitos e interfaces. Os encaixes aqui são ilustrativos.',('cpu','ram','gpu'))
        part('cpu','Processador','component',[-.4,.2,-.35],[.65,.25,.65],'#c3c9d7',
             'A CPU executa instruções e coordena tarefas. Esta representação não especifica socket ou modelo.',('motherboard','ram'))
        part('ram','Memória RAM','component',[.7,.4,0],[.12,.7,1.4],'#a99be8',
             'A RAM mantém temporariamente dados usados pelos programas. Perde seu conteúdo sem alimentação.',('motherboard','cpu'))
        part('gpu','Placa de vídeo','component',[0,.35,.9],[1.8,.45,.2],'#6b9fd6',
             'A GPU processa operações paralelas e gráficos. A geometria não comprova compatibilidade ou desempenho.',('motherboard',))
        steps = [dict(title='Conexões',text='A placa-mãe interliga os componentes.',selected='motherboard'),
                 dict(title='Processamento',text='A CPU executa instruções usando dados da memória.',selected='cpu'),
                 dict(title='Memória',text='A RAM guarda dados temporários.',selected='ram'),
                 dict(title='Gráficos',text='A GPU processa gráficos. Separe as peças para observar a disposição.',selected='gpu',exploded=True)]
    elif kind == 'geometry':
        title = 'Cubo: faces, arestas e vértices'
        description = 'Cubo ideal de lado 2 unidades ilustrativas: 6 faces, 12 arestas, 8 vértices; volume 8 unidades cúbicas. Espessuras visuais são artificiais.'
        for axis in range(3):
            for side in (-1,1):
                pos=[0,0,0]; pos[axis]=side
                dims=[2,2,2]; dims[axis]=.025
                key=f'face-{axis}-{side+1}'
                part(key,f'Face {len(objects)+1}','face',pos,dims,'#7589cb','Face quadrada: lado 2 unidades; área 4 unidades quadradas.')
        for axis in range(3):
            others=[n for n in range(3) if n!=axis]
            for a in (-1,1):
                for b in (-1,1):
                    pos=[0,0,0]; pos[others[0]]=a; pos[others[1]]=b
                    dims=[.045,.045,.045]; dims[axis]=2
                    part(f'edge-{len(objects)-5}',f'Aresta {len(objects)-5}','edge',pos,dims,'#dfb66b',
                         'Segmento de comprimento 2 unidades, encontro entre duas faces.')
        for x in (-1,1):
            for y in (-1,1):
                for z in (-1,1):
                    n=len(objects)-17
                    part(f'vertex-{n}',f'Vértice {n}','vertex',[x,y,z],[.13,.13,.13],'#e6e8f4',
                         'Ponto de encontro de três arestas do cubo.')
        steps=[dict(title='Faces',text='Há seis faces quadradas.',selected='face-2-2'),
               dict(title='Arestas',text='Há doze arestas de mesmo comprimento.',selected='edge-1'),
               dict(title='Vértices',text='Há oito vértices.',selected='vertex-8'),
               dict(title='Dimensões',text='Lado 2; área total 24 unidades quadradas; volume 8 unidades cúbicas.',selected='face-2-2',exploded=True)]
    elif kind == 'solar':
        title = 'Sistema solar didático'
        description = 'Recorte conceitual com Sol, Terra e Marte. Tamanhos, distâncias, períodos e órbitas NÃO estão em escala física exata.'
        part('sun','Sol','body',[0,0,0],[.8,.8,.8],'#efbd65','Estrela central do Sistema Solar.')
        part('earth','Terra','body',[1.5,0,0],[.55,.55,.55],'#71aada','Planeta representado em órbita circular ilustrativa.',('sun',))
        part('mars','Marte','body',[2.5,0,0],[.42,.42,.42],'#d98e74','Planeta representado em órbita circular ilustrativa.',('sun',))
        steps=[dict(title='Estrela',text='O Sol é uma estrela.',selected='sun'),
               dict(title='Terra',text='A órbita circular é uma simplificação educativa.',selected='earth'),
               dict(title='Marte',text='Velocidades e dimensões são ilustrativas, sem escala física.',selected='mars')]
    else:
        raise ValueError('Cena educativa inexistente')
    return dict(id='edu-'+kind,version=1,title=title,description=description,education=kind,
                objects=objects,steps=steps,rotation=[25,25,0],details=True)
