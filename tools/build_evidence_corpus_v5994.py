"""Freeze labeled synthetic fixtures before calibration; never external quotations.

Group splits prevent document variants crossing boundaries. The holdout is sealed
operationally, not an independently human-annotated gold standard.
"""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def build():
    # Each group has a different entity/document and a separate provenance ID.
    groups = [
        ('news', 'Jornal Aurora', 'products', 'O Jornal Aurora produz boletins e reportagens locais.', 'O Jornal Aurora foi fundado em 1998.'),
        ('history', 'Revolta do Porto', 'causes', 'A Revolta do Porto foi motivada pelos castigos físicos impostos aos trabalhadores.', 'A Revolta do Porto resultou na mudança da legislação.'),
        ('companies', 'Fábrica Horizonte', 'products', 'A Fábrica Horizonte makes cookware, cutlery and furniture.', 'A Fábrica Horizonte foi fundada em 1950.'),
        ('technology', 'Orbe.copy', 'behavior', 'Orbe.copy returns a new array without modifying the original array.', 'Orbe.copy is a documented operation.'),
        ('documentation', 'Vector.prototype.clone', 'behavior', 'Vector.prototype.clone returns a new vector without modifying the original vector.', 'Vector.prototype.clone has a documentation page.'),
        ('products', 'Câmera Prisma II', 'weight', 'A Câmera Prisma II pesa 658 g com bateria e cartão.', 'A Câmera Prisma II usa bateria AB-50.'),
        ('services', 'Serviço Nimbo', 'foundation_date', 'O Serviço Nimbo is a public service founded in 2008.', 'O Serviço Nimbo produz relatórios.'),
        ('economy', 'Banco Vale', 'founders', 'O Banco Vale foi fundado por Ana Santos e Bruno Lima.', 'O Banco Vale foi fundado em 1920.'),
        ('culture', 'Museu das Dunas', 'foundation_date', 'O Museu das Dunas foi criado em 1975.', 'O Museu das Dunas produz catálogos.'),
        ('entertainment', 'Estúdio Cobalto', 'products', 'O Estúdio Cobalto manufactures games and animation tools.', 'O Estúdio Cobalto foi fundado em 2002.'),
        ('places', 'Parque Serra Clara', 'foundation_date', 'O Parque Serra Clara foi criado em 1986.', 'O Parque Serra Clara produz guias de visitação.'),
        ('events', 'Festival Lume', 'causes', 'O Festival Lume foi motivado pela demanda de artistas por espaço cultural.', 'O Festival Lume resultou na abertura de uma escola de arte.'),
    ]
    descriptions = {'products': 'produtos', 'causes': 'causas', 'behavior': 'comportamento',
                    'weight': 'peso com bateria e cartão', 'foundation_date': 'em que ano foi criado', 'founders': 'fundadores'}
    rows = []
    for i, (domain, entity, attribute, direct, other) in enumerate(groups):
        split = 'TRAIN_OR_DEV' if i < 8 else 'VALIDATION'
        # This split is fixed before any classifier change. Labels are specified
        # from the fixture text, never obtained from the engine being evaluated.
        query = f'{entity}, {descriptions[attribute]}?'
        variants = [
            ('DIRECT_SUPPORT', direct, 'READ', 'A relação solicitada está explícita.'),
            ('WRONG_ENTITY', direct.replace(entity, 'Entidade Alheia'), 'READ', 'O predicado pertence a outra entidade.'),
            ('WRONG_ATTRIBUTE', other, 'READ', 'Entidade correta; predicado responde outro atributo.'),
            ('TOPIC_ONLY', f'{entity}: introdução e informações sobre {descriptions[attribute]}.', 'READ', 'Menciona assunto, sem valor ou relação.'),
            ('UNREAD', direct, 'UNREAD', 'Apenas snippet; não houve leitura.'),
            ('UNREAD', direct, 'METADATA_ONLY', 'Metadados não substituem a página.'),
            ('INSUFFICIENT_CONTEXT', direct.replace(entity, 'Ela'), 'READ', 'Pronome sem antecedente recuperado.'),
            ('IRRELEVANT', 'Guia de jardinagem e receitas de pão.', 'READ', 'Nenhuma relação com entidade ou atributo.'),
        ]
        if attribute == 'weight':
            variants += [('PARTIAL_SUPPORT', f'A {entity} pesa 658 g.', 'READ', 'Peso presente; inclusão de bateria/cartão não informada.')]
        if attribute == 'foundation_date':
            variants += [('CONTRADICTORY', f'O {entity} não foi criado em 1975.', 'READ', 'Negação explícita não confirma ano positivo.')]
        for j, (label, passage, read, reason) in enumerate(variants):
            rows.append(dict(id=f'ec-{i+1:02}-{j+1:02}', split=split, domain=domain,
                question=query, requirement=descriptions[attribute], entity=entity,
                attribute=attribute, relation=attribute, passage=passage, necessary_context='',
                source=f'https://example.org/synthetic/document-{i+1}', source_type='SYNTHETIC',
                read_state=read, label=label, justification=reason,
                mandatory_conditions=['battery_and_card'] if attribute == 'weight' else [],
                origin_reference=f'SYNTHETIC:build_evidence_corpus_v5994:group-{i+1}',
                document_group=f'group-{i+1}'))
    # Additional dev fixtures for local context and multi-paragraph relations.
    for index, (query, entity, attr, passage, label, reason) in enumerate([
        ('Companhia Boreal, produtos?', 'Companhia Boreal', 'products', 'A Companhia Boreal foi fundada em 1952.\n\nEla fabrica motores e geradores.', 'DIRECT_SUPPORT', 'Antecedente explícito no parágrafo imediatamente anterior.'),
        ('Companhia Boreal, produtos?', 'Companhia Boreal', 'products', 'A Companhia Boreal vende peças. A Empresa Delta foi fundada em 1954.\n\nEla fabrica motores.', 'INSUFFICIENT_CONTEXT', 'Antecedente ambíguo; não transferir predicado.'),
        ('Marca Alfa II, peso?', 'Marca Alfa II', 'weight', 'A Marca Alfa III pesa 500 g.', 'WRONG_ENTITY', 'Variante de produto diferente.'),
        ('Pacote.Cache.get comportamento?', 'Pacote.Cache.get', 'behavior', 'Pacote.Map.get returns a new value from the store.', 'WRONG_ENTITY', 'Interface qualificada diferente.'),
        ('Companhia Boreal, fundadores?', 'Companhia Boreal', 'founders', 'A Companhia Boreal não foi fundada por Maria Teste.', 'CONTRADICTORY', 'Negação explícita.'),
        ('Companhia Boreal, em que ano foi criada?', 'Companhia Boreal', 'foundation_date', 'A Companhia Boreal é uma companhia que foi fundada no Brasil em 1952.', 'DIRECT_SUPPORT', 'Auxiliares e modificadores entre sujeito e predicado.'),
        ('Pacote.Array.copy comportamento?', 'Pacote.Array.copy', 'behavior', 'Pacote.Array.copy()\nReturns a new array without modifying the original.', 'DIRECT_SUPPORT', 'Nome e descrição em linhas adjacentes, mesmo bloco.'),
        ('Câmera Neblina, peso com bateria e cartão?', 'Câmera Neblina', 'weight', 'A Câmera Neblina pesa 510 g sem bateria e cartão.', 'PARTIAL_SUPPORT', 'Condição contrária não sustenta peso com acessórios.'),
    ]):
        rows.append(dict(id=f'edge-{index+1:02}',split='TRAIN_OR_DEV',domain='edge',question=query,
            requirement=attr,entity=entity,attribute=attr,relation=attr,passage=passage,
            necessary_context='',source=f'https://example.org/synthetic/edge-{index+1}',
            source_type='SYNTHETIC',read_state='READ',label=label,justification=reason,
            mandatory_conditions=['battery_and_card'] if 'bateria e cartão' in query else [],
            origin_reference='SYNTHETIC:authored-before-calibration',document_group=f'edge-{index+1}'))
    return rows


def main():
    out = ROOT/'benchmarks/evidence_corpus_v5994.json'
    if out.exists():
        raise SystemExit('Refusing to overwrite frozen corpus')
    corpus = dict(version='1.0',annotation_origin='agent_authored_and_reviewed_not_independent_human_gold',
                  scope='SYNTHETIC relation fixtures; no external quotation or population accuracy estimate',examples=build())
    out.write_text(json.dumps(corpus,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    # Operationally sealed additional groups, never used by the development run.
    # Same annotator/templates: this is NOT independent human gold.
    sealed=[]
    for i,(entity,attribute,positive,partial,negative) in enumerate([
        ('Editora Castanha','products','A Editora Castanha fabrica livros e revistas.','', 'A Editora Castanha foi fundada em 2001.'),
        ('Instituto Lago Azul','foundation_date','O Instituto Lago Azul was established in 1982.','', 'O Instituto Lago Azul publica relatórios em 1982.'),
        ('Câmera Brisa III','weight','A Câmera Brisa III pesa 700 g com bateria e cartão.','A Câmera Brisa III pesa 700 g.','A Câmera Brisa II pesa 700 g com bateria e cartão.'),
        ('Store.Collection.copy','behavior','Store.Collection.copy returns a new collection without modifying the original collection.','', 'Store.Table.copy returns a new table without modifying the original table.'),
    ]):
        variants=[('DIRECT_SUPPORT',positive,'READ'),('WRONG_ATTRIBUTE' if i<2 else 'WRONG_ENTITY',negative,'READ'),
                  ('UNREAD',positive,'UNREAD'),('TOPIC_ONLY',entity+': informações gerais e detalhes.','READ')]
        if partial:variants.append(('PARTIAL_SUPPORT',partial,'READ'))
        for j,(label,text,read) in enumerate(variants):
            sealed.append(dict(id=f'sealed-{i+1}-{j+1}',split='BLIND_HOLDOUT',domain='sealed',
                question=entity+', '+('peso com bateria e cartão' if attribute=='weight' else attribute)+'?',
                requirement=attribute,entity=entity,attribute=attribute,relation=attribute,passage=text,
                necessary_context='',source=f'https://example.org/synthetic/sealed-{i+1}',source_type='SYNTHETIC',
                read_state=read,label=label,justification='Relation, entity and reading state explicitly specified in synthetic fixture.',
                mandatory_conditions=['battery_and_card'] if attribute=='weight' else [],
                origin_reference='SYNTHETIC:sealed-before-calibration-same-annotator',document_group=f'sealed-{i+1}'))
    (out.parent/'evidence_corpus_v5994_sealed.json').write_text(json.dumps(dict(
        scope='OPERATIONALLY_SEALED_NOT_INDEPENDENT_HUMAN_GOLD',examples=sealed),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    live=['Quem fundou a Embraer, em que ano e quais produtos ela fabrica?',
          'Como funciona Python dict.get, qual a sintaxe e se altera o dicionário original?',
          'Em que ano foi criada a Fundação Oswaldo Cruz?',
          'Quais foram as causas e as consequências da Revolta da Vacina?',
          'Quem fundou a Nintendo e quais são seus produtos?',
          'Qual o peso com bateria e cartão da Canon EOS R8?',
          'Qual a sintaxe e o comportamento de JavaScript Array.prototype.toReversed?',
          'Quais produtos a Marcopolo fabrica e em que ano foi fundada?',
          'Notícias de transporte público em Lauro de Freitas BA nos últimos sete dias',
          'Qual a data de inauguração do Museu do Amanhã no Rio de Janeiro?',
          'Como funciona Python pathlib.Path.unlink e quais são suas limitações?',
          'Quais foram as causas e consequências da Revolução dos Cravos?']
    (out.parent/'evidence_live_v5994_holdout.json').write_text(json.dumps(dict(
        scope='LIVE_EXTERNAL_NEW_QUESTIONS_FROZEN_BEFORE_IMPLEMENTATION_NOT_ANNOTATED_GOLD',
        queries=[dict(id=f'ei-{i+1:02}',query=q,category='universal') for i,q in enumerate(live)]),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('Frozen examples:',len(corpus['examples']), 'sha256:',hashlib.sha256(out.read_bytes()).hexdigest())


if __name__ == '__main__':main()
