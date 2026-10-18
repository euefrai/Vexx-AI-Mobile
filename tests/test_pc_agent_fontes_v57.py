"""V5.7 — bloco "Fontes:" anexado por estrutura, não por substring.

Regressão real (auditoria V5.7): `anexar_fontes` decidia por
`"Fontes:" not in texto` — uma menção à palavra no meio da resposta (ex.:
"As Fontes: primárias…") fazia o bloco estruturado de fontes nunca ser
anexado; e o inverso (lista real sem a palavra exata) duplicava.
"""
import pc_agent

F = [{"id": "S1", "titulo": "Doc", "url": "https://exemplo.com/doc"}]
BLOCO = "Fontes:\n- [S1 Doc](https://exemplo.com/doc)"


def test_mencao_a_fontes_sem_lista_nao_esconde_as_fontes_reais():
    texto = "Fontes: veja o estudo a seguir\n\nele explica o resultado."
    final = pc_agent.anexar_fontes(texto, F)
    assert BLOCO in final


def test_lista_fontes_do_modelo_evita_duplicar():
    texto = "Resposta.\n\n## Fontes:\n- [Doc](https://exemplo.com/doc)"
    assert pc_agent.anexar_fontes(texto, F) == texto


def test_fontes_negrito_com_link_evita_duplicar():
    texto = "Resposta.\n\n**Fontes:**\n- [Doc](https://exemplo.com/doc)"
    assert pc_agent.anexar_fontes(texto, F) == texto


def test_mencao_inline_nao_conta_como_bloco():
    texto = "As Fontes: primárias são melhores para esse caso."
    final = pc_agent.anexar_fontes(texto, F)
    assert BLOCO in final


def test_sem_mencao_anexa_normalmente():
    final = pc_agent.anexar_fontes("Resposta curta.", F)
    assert final.endswith(BLOCO)


def test_sem_fontes_nao_muda_nada():
    assert pc_agent.anexar_fontes("Texto", []) == "Texto"


def test_cabecalho_fontes_sem_link_nao_bloqueia():
    texto = "Resultado.\n\n### Fontes\n\nnão consegui abrir a página original."
    final = pc_agent.anexar_fontes(texto, F)
    assert BLOCO in final
