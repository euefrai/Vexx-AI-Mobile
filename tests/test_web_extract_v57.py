"""V5.7 — Extração web: trecho usado não pode vir de referências/bibliografia.

Regressão real coberta (auditoria V5.7, 2026-10-17): em artigos com seção de
referências (ex.: Wikipédia), o trecho exibido vinha de "Consultado em …
Cópia arquivada …" porque citações citam o tema em frases curtas e ganhavam
o ranking de palavras-chave.
"""
import web_extract


def test_trecho_nao_vem_de_referencias():
    corpo = ("O sistema de travagem antibloqueio evita que as rodas bloqueiem "
             "durante travagens bruscas. O ABS atua bombeando a pressão do freio "
             "para manter a dirigibilidade do veículo em piso escorregadio. ")
    refs = ("«Freios ABS e Airbag obrigatório». Consultado em 15 de outubro de "
            "2014. Cópia arquivada em 3 de março de 2016. ↑ Jusbrasil. "
            "Consultado em 3 de janeiro de 2024. Cópia arquivada em 3 de "
            "janeiro de 2024. «O Código de Trânsito e o ABS». Consultado em 27 "
            "de fevereiro de 2014.")
    trecho = web_extract.melhor_trecho(corpo + refs, "freio ABS", 200)
    assert "travagem" in trecho or "rodas bloqueiem" in trecho
    assert "Cópia arquivada" not in trecho
    assert "Consultado em" not in trecho


def test_trecho_sem_termos_usa_inicio():
    texto = "Primeiro parágrafo do documento. Segundo parágrafo do documento."
    assert web_extract.melhor_trecho(texto, "", 40).startswith("Primeiro parágrafo")


def test_trecho_normal_continua_escolhendo_por_termo():
    texto = ("Introdução sem relação alguma. Depois falamos de notebook com "
             "processador rápido e memória. Mais texto irrelevante adiante. "
             "Outra seção qualquer para preencher o restante do conteúdo.")
    trecho = web_extract.melhor_trecho(texto, "notebook memória", 60)
    assert "notebook" in trecho


def test_penalidade_citacoes_e_limitada():
    pedaco = ("Consultado em 2020. Cópia arquivada. Consultado em 2021. "
              "Cópia arquivada. Consultado em 2022. Cópia arquivada. "
              "Consultado em 2023. Cópia arquivada.")
    assert web_extract._penalidade_citacoes(pedaco) <= 30.0
    assert web_extract._penalidade_citacoes(pedaco) > web_extract._penalidade_citacoes(
        "mencionado em uma referência: Consultado em 2020.")
    assert web_extract._penalidade_citacoes("texto normal sem citações") == 0.0
