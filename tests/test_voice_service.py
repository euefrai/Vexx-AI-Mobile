import pytest
import voice_service

def test_limpar_texto_para_fala():
    texto_raw = "Aqui está um ```python\nprint(1)\n``` e um link [Vexx](https://vexx-ai.space). Veja **isso**!"
    limpo = voice_service.limpar_texto_para_fala(texto_raw)
    assert "https://" not in limpo
    assert "```" not in limpo
    assert "Vexx" in limpo
    assert "**" not in limpo

def test_sentence_accumulator():
    acc = voice_service.SentenceAccumulator(min_chars=10, max_chars=100)
    
    # Delta 1: frase incompleta
    prontas = acc.feed("Olá mundo! Como ")
    assert len(prontas) == 1
    assert "Olá mundo!" in prontas[0]
    
    # Delta 2: conclui frase
    prontas2 = acc.feed("você está hoje?")
    assert len(prontas2) == 1
    assert "Como você está hoje?" in prontas2[0]
    
    # Delta 3: sem pontuação no fim -> flush
    acc.feed("Tudo ótimo por aqui")
    finais = acc.flush()
    assert len(finais) == 1
    assert "Tudo ótimo por aqui" in finais[0]

def test_voice_urls():
    http_url = voice_service.get_voice_api_url()
    ws_url = voice_service.get_voice_ws_url()
    assert http_url.startswith("http")
    assert ws_url.startswith("ws")
    assert "/ws/conversacao" in ws_url
