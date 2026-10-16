"""Educational contracts, operations and owner-scoped durable context."""
import copy
import json
import subprocess
from pathlib import Path

import pytest
import jdui
import model3d
from model3d_education import scene
import pc_agent

ROOT = Path(__file__).resolve().parents[1]


def mutations():
    p = scene('computer')
    values = [scene(k) for k in ('computer', 'geometry', 'solar')]
    for patch in ({'selected':'missing'}, {'hidden':['ram','ram']}, {'transparent':['other']},
                  {'speed':True}, {'speed':3}, {'step':.5}, {'step':99}, {'view':'url'},
                  {'lessonPlaying':'true'}, {'script':'alert(1)'}, {'toString':'x'}, {'__proto__':{}}):
        values.append(dict(p,interaction=patch))
    for patch in ({'related':['missing']}, {'dimensions':[0,1,1]}, {'metadata':{'url':'https://evil'}},
                  {'metadata':{'conceptual':'true'}}, {'category':'script'}):
        q=copy.deepcopy(p);q['objects'][0].update(patch);values.append(q)
    q=copy.deepcopy(p);q['steps'][0]['selected']='missing';values.append(q)
    return values


def test_contract_parity():
    code="""const fs=require('fs'),vm=require('vm');global.window=global;
    vm.runInThisContext(fs.readFileSync('public/model3d-schema.js','utf8'));
    console.log(JSON.stringify(JSON.parse(fs.readFileSync(0,'utf8')).map(p=>{
      try{return validateModel3D(p)}catch(e){return null}})));"""
    values=mutations()
    output=subprocess.run(['node','-e',code],input=json.dumps(values),capture_output=True,
                          text=True,encoding='utf-8',cwd=ROOT,check=True)
    for index,(p,js) in enumerate(zip(values,json.loads(output.stdout))):
        if index<3:
            assert model3d.validate(p)==js
        else:
            with pytest.raises(ValueError): model3d.validate(p)
            assert js is None
    geometry=model3d.validate(scene('geometry'))
    assert len(geometry['objects'])==26
    assert [sum(o['category']==k for o in geometry['objects']) for k in ('face','edge','vertex')]==[6,12,8]


@pytest.mark.parametrize('command,key,value',[
    ('Destaque a RAM','selected','ram'),('Isole a CPU','isolated','cpu'),
    ('Oculte a GPU','hidden',['gpu']),('Deixe a placa-mãe transparente','transparent',['motherboard']),
    ('Foque a RAM','focus','ram'),('Separe as peças','exploded',True),
    ('Mostre a parte traseira','view','back'),('Próximo passo','step',1),
    ('Inicie a animação educativa','lessonPlaying',True),
])
def test_commands(command,key,value):
    text,p=model3d.respond(command,scene('computer'))
    assert p['interaction'][key]==value
    assert text


def test_boundaries_and_safe_fallbacks():
    p=scene('computer')
    for command in ('Volte ao passo anterior','Destaque o SSD'):
        assert model3d.respond(command,p)[1] is None
    assert model3d.respond('Explique a CPU',p)[1]['interaction']['selected']=='cpu'
    assert model3d.respond('Gire o mouse',p) is None
    _,p=model3d.respond('Oculte a RAM',p)
    _,p=model3d.respond('Revele todas as partes',p)
    assert p['interaction']['hidden']==[]
    for n in (float('nan'),float('inf')):
        with pytest.raises(ValueError):model3d.validate_interaction({'speed':n},['ram'],4)


def unpack(text):
    return json.loads(jdui.extrair_fences(text)[0])['blocks'][0]['props']


def test_context_owner_conversation_and_latest_unsynced_state(tmp_path,monkeypatch):
    db=pc_agent.open_db(tmp_path/'v54.sqlite3')
    monkeypatch.setattr(pc_agent,'gerar_texto',lambda *a,**k:pytest.fail('Educational commands must not use LLM'))
    payload=dict(message_id='education-user-01',conversation_id='edu-conv',owner='u-alice',text='Mostre um computador em 3D')
    first=pc_agent.ai_completa(db,payload,{'model':'test'})
    p=unpack(first['response_text'])
    hint=dict(messageId=first['reply_id'],scene=p['id'],interaction={'selected':'ram','hidden':['gpu']},rotation=[0,1,0],distance=5)
    # A later scene must not override the explicitly active older message.
    pc_agent.ai_completa(db,dict(payload,message_id='education-user-02',text='Mostre um cubo didático em 3D'),{'model':'test'})
    response=pc_agent.cmd_model3d(db,'Separe as peças','u-alice','edu-conv',json.dumps(hint))
    updated=unpack(response)
    assert updated['education']=='computer'
    assert updated['interaction']['selected']=='ram' and updated['interaction']['hidden']==['gpu']
    assert updated['interaction']['exploded'] and updated['camera']['distance']==5
    for owner,conv in [('u-bob','edu-conv'),('u-alice','other')]:
        assert 'indisponível' in pc_agent.cmd_model3d(db,'Separe as peças',owner,conv,json.dumps(hint))
    bad=copy.deepcopy(hint);bad['interaction']['selected']='foreign'
    assert 'inválido' in pc_agent.cmd_model3d(db,'Separe as peças','u-alice','edu-conv',json.dumps(bad))
    assert 'inválida' in pc_agent.cmd_model3d(db,'Separe as peças','u-alice','edu-conv','[]')
    # Persisted UI state is used when an older client sends no immediate scene context.
    latest=db.execute("SELECT id FROM messages WHERE role='assistant' ORDER BY created_at DESC LIMIT 1").fetchone()[0]
    geometry=model3d.validate(scene('geometry'))
    state=dict(scene=geometry['id'],interaction={'selected':geometry['objects'][0]['id'],'exploded':True})
    db.execute("INSERT INTO ui_state(k,message_id,slot,state,updated_at,owner_id) VALUES(?,?,?,?,?,?)",
               ('u-alice:test',latest,'0:0:model3d',json.dumps(state),'2026-10-16T20:00:00Z','u-alice'))
    db.commit()
    assert unpack(pc_agent.cmd_model3d(db,'Vista frontal','u-alice','edu-conv'))['interaction']['exploded']
    db.close()
