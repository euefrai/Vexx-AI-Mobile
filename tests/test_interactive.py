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


def test_presentation_engine():
    E = pc_agent.FAJULTOPresentationEngine
    assert E.sugerir('Crie uma calculadora que funcione aqui no chat') == 'calculator'
    assert E.sugerir('quero um quiz de matemática com 6 perguntas') == 'quiz'
    assert E.sugerir('monte minha rotina de estudos') == 'checklist'
    assert E.sugerir('compare Python, Java e JavaScript') == 'cards'
    assert E.sugerir('mostre um diagrama de como o app se conecta') == 'diagram'
    assert E.sugerir('qual a capital do Peru?') == ''
    assert E.sugerir('o que é uma variável?') == ''
    # legado redireciona para JDUI
    assert pc_agent.intencao_widget('crie uma calculadora simples') == 'calculator'


def test_quiz_proibe_codigo_e_oferece_fonte():
    db = _db()
    cfg = {'proxy': 'http://127.0.0.1:9/v1', 'model': 'm', 'system': 'BASE',
           'context': 5, 'max_tokens': 50, 'memoria_global': False, 'pesquisa_web': False}
    msgs, _ = pc_agent.ai_montar_mensagens(db, 'conv-q', cfg, 'crie um quiz de Python')
    sistema = msgs[0]['content']
    assert 'REGRA DURA DO QUIZ' in sistema
    assert 'Quer ver o código-fonte' in sistema
    db.close()


def test_followup_codigo_injeta_ultimo_quiz():
    import json as _json
    db = _db()
    quiz = {"version": "FAJULTO-ui-message/v1", "blocks": [
        {"type": "ui", "component": "quiz", "props": {"title": "Py", "questions": [
            {"q": "2+2?", "options": ["3", "4"], "answer": 1}]}}]}
    pc_agent.persist_messages(db, [
        {'id': 'ucalculada01', 'origin': 'mobile', 'role': 'user', 'text': 'crie um quiz de Python',
         'created_at': '2026-10-13T10:00:00.000Z', 'conversation_id': 'conv-c'},
        {'id': 'acalculada01', 'origin': 'mobile', 'role': 'assistant',
         'text': 'Aqui está:\n\n```jdui\n' + _json.dumps(quiz) + '\n```',
         'created_at': '2026-10-13T10:01:00.000Z', 'conversation_id': 'conv-c'}])
    cfg = {'proxy': 'http://127.0.0.1:9/v1', 'model': 'm', 'system': 'BASE',
           'context': 5, 'max_tokens': 50, 'memoria_global': False, 'pesquisa_web': False}
    msgs, _ = pc_agent.ai_montar_mensagens(db, 'conv-c', cfg, 'sim, quero o código')
    assert 'GERAR CÓDIGO-FONTE' in msgs[0]['content']
    assert '2+2?' in msgs[0]['content']
    # sem interface anterior: sem injeção
    msgs2, _ = pc_agent.ai_montar_mensagens(db, 'conv-outra', cfg, 'sim, quero o código')
    assert 'GERAR CÓDIGO-FONTE' not in msgs2[0]['content']
    db.close()


def test_montar_injeta_diretiva_jdui():
    db = _db()
    cfg = {'proxy': 'http://127.0.0.1:9/v1', 'model': 'm', 'system': 'BASE',
           'context': 5, 'max_tokens': 50, 'memoria_global': False, 'pesquisa_web': False}
    msgs, extras = pc_agent.ai_montar_mensagens(db, 'conv-w', cfg, 'crie uma calculadora simples')
    sistema = msgs[0]['content']
    assert '```jdui' in sistema and 'calculator' in sistema
    assert 'widget-html' not in sistema  # modelo não deve gerar JS
    msgs2, _ = pc_agent.ai_montar_mensagens(db, 'conv-w', cfg, 'qual a capital do Peru?')
    assert '```jdui' not in msgs2[0]['content']
    db.close()


def test_sintetizar_jdui_converte_texto():
    import json as _json
    quiz_json = _json.dumps({"version": "FAJULTO-ui-message/v1", "blocks": [
        {"type": "ui", "component": "quiz", "props": {"title": "Py", "questions": [
            {"q": "2+2?", "options": ["3", "4"], "answer": 1}]}}]})
    cfg = {'proxy': 'http://127.0.0.1:9/v1', 'model': 'm'}
    import hermes_bridge
    real = hermes_bridge.chat_complete
    try:
        hermes_bridge.chat_complete = lambda *a, **k: {"texto": quiz_json, "latencia_s": 0.1}
        fence = pc_agent.sintetizar_jdui(cfg, 'quiz', 'crie um quiz de Python básico',
                                         'Pergunta 1: quanto é 2+2? a) 3 b) 4. '
                                         'Pergunta 2: qual o tipo de []? a) list b) dict.')
        assert fence.startswith('\n\n```jdui\n') and fence.endswith('\n```')
        ok, norm, _ = __import__('jdui').validar_mensagem(
            _json.loads(fence.split('```jdui\n', 1)[1].rsplit('\n```', 1)[0]))
        assert ok
        hermes_bridge.chat_complete = lambda *a, **k: {"texto": 'não-json', "latencia_s": 0.1}
        assert pc_agent.sintetizar_jdui(cfg, 'quiz', 'q', 'texto longo o suficiente aqui ok') == ''
        assert pc_agent.sintetizar_jdui(cfg, 'tabela', 'q', 'x' * 100) == ''
        assert pc_agent.sintetizar_jdui(cfg, 'quiz', 'q', 'curto') == ''
    finally:
        hermes_bridge.chat_complete = real


def test_ai_completa_sintetiza_quiz_sem_fence(monkeypatch):
    import json as _json
    db = _db()
    pc_agent.persist_messages(db, [{
        'id': 'quiz-user-01', 'origin': 'mobile', 'role': 'user',
        'text': 'crie um quiz de Python com 2 perguntas',
        'created_at': '2026-10-13T12:00:00.000Z', 'conversation_id': 'conv-qz'}])
    cfg = {'proxy': 'http://127.0.0.1:9/v1', 'model': 'm', 'system': 's',
           'context': 5, 'max_tokens': 500}
    quiz_json = _json.dumps({"version": "FAJULTO-ui-message/v1", "blocks": [
        {"type": "ui", "component": "quiz", "props": {"title": "Py", "questions": [
            {"q": "2+2?", "options": ["3", "4"], "answer": 1}]}}]})
    chamadas = []

    def fake_complete(*a, **k):
        chamadas.append(1)
        if len(chamadas) == 1:
            return {"texto": "Aqui está o quiz em Python:\n```python\nprint('oi')\n```", "latencia_s": 0.5}
        return {"texto": quiz_json, "latencia_s": 0.5}

    monkeypatch.setattr('hermes_bridge.chat_complete', fake_complete)
    monkeypatch.setattr('pc_agent.aprender_com_conversa', lambda *a, **k: None)
    r = pc_agent.ai_completa(db, {'message_id': 'quiz-user-01', 'conversation_id': 'conv-qz'}, cfg)
    assert len(chamadas) == 2  # resposta + síntese
    assert '```jdui' in r['response_text'] and '```python' in r['response_text']
    db.close()


def test_ai_completa_nao_sintetiza_quando_ja_tem_fence(monkeypatch):
    import json as _json
    db = _db()
    quiz_json = _json.dumps({"version": "FAJULTO-ui-message/v1", "blocks": [
        {"type": "ui", "component": "quiz", "props": {"title": "Py", "questions": [
            {"q": "2+2?", "options": ["3", "4"], "answer": 1}]}}]})
    pc_agent.persist_messages(db, [{
        'id': 'quiz-user-02', 'origin': 'mobile', 'role': 'user',
        'text': 'crie um quiz de Python com 2 perguntas',
        'created_at': '2026-10-13T12:00:00.000Z', 'conversation_id': 'conv-qz'}])
    cfg = {'proxy': 'http://127.0.0.1:9/v1', 'model': 'm', 'system': 's',
           'context': 5, 'max_tokens': 500}
    chamadas = []

    def fake_complete(*a, **k):
        chamadas.append(1)
        return {"texto": 'Pronto!\n\n```jdui\n' + quiz_json + '\n```', "latencia_s": 0.5}

    monkeypatch.setattr('hermes_bridge.chat_complete', fake_complete)
    monkeypatch.setattr('pc_agent.aprender_com_conversa', lambda *a, **k: None)
    r = pc_agent.ai_completa(db, {'message_id': 'quiz-user-02', 'conversation_id': 'conv-qz'}, cfg)
    assert len(chamadas) == 1  # sem chamada extra
    assert '```jdui' in r['response_text']
    db.close()


QUIZ_CODIGO = '''
def quiz_python():
    print("=== QUIZ DE PYTHON ===\\n")
    pontuacao = 0

    # Pergunta 1
    print("1. Qual é o resultado de 5 // 2?")
    print("a) 2.5  b) 2  c) 3  d) 2.0")
    resp = input("Sua resposta: ").strip().lower()
    if resp == "b":
        pontuacao += 1

    # Pergunta 2
    print("2. Qual define lista vazia?")
    print("a) []")
    print("b) {}")
    print("c) ()")
    print("d) x")
    resp = input("Sua resposta: ").strip().lower()
    if resp == 'c':
        pontuacao += 1
'''

QUIZ_TEXTO = '''Quiz de Python
Pergunta 1: Qual será a saída de print(2 + 3 * 4)?
a) 20
b) 14
c) 12
d) 10
Resposta: b

Pergunta 2: Como se define uma função?
a) function f():
b) def f():
Resposta correta: b
'''


def _valida_fence(fence, componente):
    import json as _json
    assert fence.startswith('\n\n```jdui\n') and fence.endswith('\n```')
    obj = _json.loads(fence.split('```jdui\n', 1)[1].rsplit('\n```', 1)[0])
    import jdui as _j
    ok, norm, _ = _j.validar_mensagem(obj)
    assert ok and norm['blocks'][0]['component'] == componente
    return norm


def test_extracao_deterministica_quiz_codigo():
    fence = pc_agent.extrair_quiz_codigo(QUIZ_CODIGO)
    norm = _valida_fence(fence, 'quiz')
    qs = norm['blocks'][0]['props']['questions']
    assert len(qs) == 2
    assert qs[0]['answer'] == 1 and qs[0]['options'][1] == '2'
    assert qs[1]['answer'] == 2 and len(qs[1]['options']) == 4


def test_extracao_deterministica_quiz_texto():
    fence = pc_agent.extrair_quiz_texto(QUIZ_TEXTO)
    norm = _valida_fence(fence, 'quiz')
    qs = norm['blocks'][0]['props']['questions']
    assert len(qs) == 2
    assert qs[0]['answer'] == 1
    assert qs[1]['answer'] == 1 and qs[1]['options'] == ['function f():', 'def f():']
    # código não contamina o parser de texto
    assert pc_agent.extrair_quiz_texto(QUIZ_CODIGO) == ''


def test_sintese_sem_llm_quando_deterministico():
    import hermes_bridge
    chamadas = []
    real = hermes_bridge.chat_complete
    try:
        hermes_bridge.chat_complete = lambda *a, **k: (chamadas.append(1), {"texto": "x"})[1]
        assert pc_agent.sintetizar_calculadora('crie uma calculadora de IMC').count('imc') >= 1
        assert 'basic' in pc_agent.sintetizar_calculadora('calculadora simples')
        fence = pc_agent.sintetizar_jdui({}, 'quiz', 'crie um quiz', QUIZ_CODIGO)
        assert fence.startswith('\n\n```jdui\n')
        assert chamadas == []  # zero chamadas LLM no caminho determinístico
        itens = pc_agent.extrair_checklist('- Estudar Python\ntexto solto sem bullet')
        assert itens == ''
        ok = pc_agent.extrair_checklist('- Estudar Python\n- Fazer exercícios\n- Revisar')
        assert 'Estudar Python' in ok
    finally:
        hermes_bridge.chat_complete = real


def test_envios_concorrentes_serializados():
    """Regressão: threads de stream + loop principal não entrelaçam frames."""
    import json as _json
    import threading as _th
    import time as _time

    class SockFalhaSeConcorrente:
        def __init__(self):
            self.dentro = False
            self.lock = _th.Lock()
            self.recebidos = []
            self.violacoes = 0

        def send(self, texto):
            with self.lock:
                if self.dentro:
                    self.violacoes += 1
                self.dentro = True
            _time.sleep(0.002)  # alarga a janela de corrida
            _json.loads(texto)  # frame íntegro: JSON válido
            with self.lock:
                self.recebidos.append(texto)
                self.dentro = False

    sock = SockFalhaSeConcorrente()
    erros = []

    def worker(n):
        try:
            for i in range(25):
                pc_agent.enviar_ws(sock, {"request_id": f"r{n}", "type": "ai_delta",
                                          "seq": i, "trecho": "olá"})
        except Exception as exc:  # noqa: BLE001
            erros.append(exc)

    ts = [_th.Thread(target=worker, args=(n,)) for n in range(4)]
    # loop principal intercalado
    def principal():
        try:
            for i in range(25):
                with pc_agent.ENVIO_LOCK:
                    sock.send(_json.dumps({"request_id": "main", "type": "ack"}))
        except Exception as exc:  # noqa: BLE001
            erros.append(exc)

    ts.append(_th.Thread(target=principal))
    [t.start() for t in ts]
    [t.join(timeout=30) for t in ts]
    assert not erros
    assert sock.violacoes == 0
    assert len(sock.recebidos) == 125


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
