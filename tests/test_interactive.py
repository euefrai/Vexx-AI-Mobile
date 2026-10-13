"""Minis apps (widgets) e garantia de imagem: intents e prompt impositivo."""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pc_agent


def _db():
    tmp = Path(tempfile.mkdtemp()) / 'w.sqlite3'
    return pc_agent.open_db(tmp)


def test_intencao_widget():
    assert pc_agent.intencao_widget('Crie uma calculadora que funcione aqui no chat') == 'calculadora'
    assert pc_agent.intencao_widget('quero um quiz de matemática') == 'quiz'
    assert pc_agent.intencao_widget('faz uma lista de tarefas interativa') == 'lista de tarefas'
    assert pc_agent.intencao_widget('qual a capital do Peru?') == ''


def test_montar_injeta_diretiva_widget():
    db = _db()
    cfg = {'proxy': 'http://127.0.0.1:9/v1', 'model': 'm', 'system': 'BASE',
           'context': 5, 'max_tokens': 50, 'memoria_global': False, 'pesquisa_web': False}
    msgs, extras = pc_agent.ai_montar_mensagens(db, 'conv-w', cfg, 'crie uma calculadora simples')
    sistema = msgs[0]['content']
    assert 'widget-html' in sistema and 'PROIBIDO' in sistema
    msgs2, _ = pc_agent.ai_montar_mensagens(db, 'conv-w', cfg, 'qual a capital do Peru?')
    assert 'widget-html' not in msgs2[0]['content']
    db.close()


def test_imagem_garantida_no_texto():
    user = 'me mostre uma imagem do tom do desenho tom and jerry'
    termo = pc_agent.intencao_imagem(user)
    assert termo
    modelo_falante = '[Mostrando uma imagem de Tom e Jerry]\n\nAqui está ela!'
    final = pc_agent.anexar_fontes(modelo_falante, [], termo)
    assert '![tom do desenho tom and jerry](https://loremflickr.com/800/500/' in final
    # Se o modelo já trouxe markdown, não duplica.
    com_img = 'veja ![gato](https://x.com/g.jpg)'
    assert pc_agent.anexar_fontes(com_img, [], termo) == com_img
