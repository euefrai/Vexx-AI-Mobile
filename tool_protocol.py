"""Separação entre resposta ao usuário e chamadas internas de ferramentas.

O Hermes (e modelos OpenAI-compatible) pode devolver chamadas de ferramenta
como texto no conteúdo, por exemplo:

    <tool_call>tools.webresearch{"query":"..."}

Isso não é resposta ao usuário. Também não é uma autorização para executar
nada: este módulo apenas remove a chamada do texto e registra um erro de
protocolo. A execução de ferramentas continua sendo feita somente pelos
caminhos internos determinísticos do agente.

O sanitizador é incremental (streaming), tolera marcador dividido entre
chunks e preserva menções literais em código/documentação (inline code ou
bloco cercado por crases). JSON incompleto se torna erro de protocolo; não
tentamos "consertar" e executar uma chamada malformada.
"""
from __future__ import annotations

import json
import re

ABERTURA = "<tool_call>"
FECHAMENTO = "</tool_call>"
MARCADORES = {ABERTURA: FECHAMENTO, '<longcat_tool_call>': '</longcat_tool_call>'}
MAX_BUFFER = 200_000

_RX_NOME = re.compile(r"^\s*(?:[A-Za-z_][\w.-]*\s*[:.]?\s*)?", re.S)
_RX_JSON_INICIO = re.compile(r"\{")
_RX_MENCAO_CODIGO = re.compile(r"`[^`\n]{0,80}<tool_call>[^`\n]{0,80}`", re.I)
# Chamada sem JSON (stream cortado): "tools.webresearch" / "functions.web_search".
_RX_CHAMADA_SEM_PAYLOAD = re.compile(
    r"^\s*(?:(?:tools?|functions?)\s*\.\s*[A-Za-z_][\w.-]*|"
    r"[A-Za-z_][\w-]*(?:\.[A-Za-z_][\w-]*)+)\b", re.I)


def _erro(codigo: str, ferramenta: str = "", detalhe: str = "") -> dict:
    # Nunca inclui o payload inteiro: argumentos podem conter dados do usuário.
    return {"codigo": codigo, "ferramenta": (ferramenta or "")[:80],
            "detalhe": (detalhe or "")[:160]}


def _fim_json(texto: str, inicio: int) -> int | None:
    """Índice após o objeto JSON balanceado, ou None se ainda incompleto."""
    profundidade = 0
    em_string = False
    escape = False
    for i in range(inicio, len(texto)):
        c = texto[i]
        if em_string:
            if escape:
                escape = False
            elif c == "\\":
                escape = True
            elif c == '"':
                em_string = False
            continue
        if c == '"':
            em_string = True
        elif c == "{":
            profundidade += 1
        elif c == "}":
            profundidade -= 1
            if profundidade == 0:
                return i + 1
    return None


def _dentro_de_codigo(prefixo: str) -> bool:
    """Menciona o marcador dentro de bloco/inline code? (documentação legítima)"""
    if prefixo.count("```") % 2 == 1:
        return True
    # Crase inline aberta imediatamente antes do marcador (documentação).
    return bool(re.search(r"`[^`\n]{0,120}$", prefixo))


def _prefixo_marcador(texto: str) -> int:
    """Tamanho do sufixo que pode ser o começo de `<tool_call>` (sem caixa)."""
    baixo = (texto or "").lower()
    for n in range(min(max(map(len, MARCADORES)) - 1, len(baixo)), 0, -1):
        if any(marker.startswith(baixo[-n:]) for marker in MARCADORES):
            return n
    return 0


def _classificar_corpo(corpo: str) -> dict:
    """Classifica o corpo de uma chamada delimitada (nunca executa nada)."""
    nome = (_RX_NOME.match(corpo).group(0) if _RX_NOME.match(corpo) else "").strip()
    inicio = _RX_JSON_INICIO.search(corpo)
    if inicio is None:
        if _RX_CHAMADA_SEM_PAYLOAD.match(corpo):
            return _erro("tool_call_sem_payload", nome or corpo[:40].strip(),
                         "chamada interna sem JSON descartada")
        return _erro("tool_call_removida", nome,
                     "chamada interna não é resposta ao usuário")
    fim = _fim_json(corpo, inicio.start())
    if fim is None:
        return _erro("tool_call_json_incompleto", nome,
                     "JSON de ferramenta incompleto descartado")
    bruto = corpo[inicio.start():fim].strip()
    try:
        obj = json.loads(bruto)
        if not isinstance(obj, (dict, list)):
            raise ValueError("payload não é objeto/lista")
    except (ValueError, TypeError):
        return _erro("tool_call_json_invalido", nome,
                     "JSON inválido descartado sem execução")
    return _erro("tool_call_removida", nome, "chamada interna não executada")


class Sanitizador:
    """Filtro incremental de chamadas de ferramenta no conteúdo do modelo."""

    def __init__(self):
        self.buffer = ""
        self.erros: list[dict] = []
        self.contexto = ""
        self.descartar_ate = ""

    def _processar(self, final: bool) -> str:
        saida: list[str] = []
        while True:
            matches = [(self.buffer.lower().find(marker), marker) for marker in MARCADORES]
            pos, abertura = min((m for m in matches if m[0] >= 0), default=(-1, ABERTURA))
            fechamento = MARCADORES[abertura]
            if pos < 0:
                if final:
                    saida.append(self.buffer)
                    self.buffer = ""
                else:
                    n = _prefixo_marcador(self.buffer)
                    if n:
                        saida.append(self.buffer[:-n])
                        self.buffer = self.buffer[-n:]
                    else:
                        saida.append(self.buffer)
                        self.buffer = ""
                break
            prefixo = self.buffer[:pos]
            # Documentação/código que cita o marcador é conteúdo legítimo.
            contexto = self.contexto + "".join(saida) + prefixo
            if _dentro_de_codigo(contexto):
                saida.append(self.buffer[:pos + len(abertura)])
                self.buffer = self.buffer[pos + len(abertura):]
                continue
            saida.append(prefixo)
            corpo_inicio = pos + len(abertura)
            resto = self.buffer[corpo_inicio:]
            fecha = resto.lower().find(fechamento)
            if abertura != ABERTURA:
                # Native dialects are protocol errors, never executable tools.
                if fecha < 0 and not final:
                    self.buffer = self.buffer[pos:]
                    return ''.join(saida)
                corpo = resto[:fecha] if fecha >= 0 else resto
                native = re.match(r'\s*([A-Za-z_][\w.:-]{0,79})', corpo)
                is_call = fecha >= 0 or '<longcat_arg_' in corpo.lower() or bool(
                    native and '_' in native[1])
                if is_call:
                    self.erros.append(_erro('tool_call_nativa_removida', native[1] if native else '',
                                             'chamada nativa descartada'))
                    self.buffer = resto[fecha + len(fechamento):] if fecha >= 0 else ''
                    continue
                saida.append(self.buffer[pos:])
                self.buffer = ''
                break
            if fecha >= 0:
                self.erros.append(_classificar_corpo(resto[:fecha]))
                self.buffer = resto[fecha + len(FECHAMENTO):]
                continue
            # Sem fechamento: a chamada do Hermes costuma ser apenas
            # `<tool_call>nome{json}`. Só removemos quando há JSON reconhecível
            # (ou nome de ferramenta inequívoco, mesmo sem payload).
            inicio = _RX_JSON_INICIO.search(resto)
            if inicio is None:
                if not final:
                    self.buffer = self.buffer[pos:]
                    return "".join(saida)
                if _RX_CHAMADA_SEM_PAYLOAD.match(resto):
                    self.erros.append(_erro(
                        "tool_call_sem_payload", resto[:40].strip(),
                        "chamada interna sem JSON descartada"))
                    self.buffer = ""
                    return "".join(saida)
                # Mencao literal sem payload (ex.: "o marcador <tool_call>"):
                # preserva, porque não há evidência de chamada real.
                saida.append(self.buffer[pos:])
                self.buffer = ""
                return "".join(saida)
            fim = _fim_json(resto, inicio.start())
            if fim is None:
                if not final:
                    self.buffer = self.buffer[pos:]
                    return "".join(saida)
                self.erros.append(_erro("tool_call_json_incompleto",
                                        resto[:40].strip(),
                                        "JSON de ferramenta incompleto descartado"))
                self.buffer = ""
                return "".join(saida)
            sobra = resto[fim:]
            sem_espaco = sobra.lstrip()
            if sem_espaco.lower().startswith("<") and \
                    len(sem_espaco) < len(FECHAMENTO) and \
                    FECHAMENTO.startswith(sem_espaco.lower()):
                if not final:
                    # Fechamento dividido entre chunks: espera o restante.
                    self.buffer = self.buffer[pos:]
                    return "".join(saida)
                # Stream morreu no meio do fechamento: descarta o fragmento.
                self.erros.append(_classificar_corpo(resto[:fim]))
                self.buffer = ""
                return "".join(saida)
            if sem_espaco.lower().startswith(FECHAMENTO):
                self.erros.append(_classificar_corpo(resto[:fim]))
                self.buffer = sem_espaco[len(FECHAMENTO):]
                continue
            self.erros.append(_classificar_corpo(resto[:fim]))
            self.buffer = sobra
        return "".join(saida)

    def alimentar(self, trecho: str) -> str:
        """Recebe um delta e devolve somente o texto seguro para o usuário."""
        if not trecho:
            return ""
        self.buffer += str(trecho)
        if self.descartar_ate:
            pos = self.buffer.lower().find(self.descartar_ate)
            if pos < 0:
                self.buffer = self.buffer[-len(self.descartar_ate):]
                return ''
            self.buffer = self.buffer[pos + len(self.descartar_ate):]
            self.descartar_ate = ''
        if len(self.buffer) > MAX_BUFFER:
            # Proteção de memória: o limite de resposta normal é bem menor.
            self.erros.append(_erro("protocolo_buffer_excedido",
                                    detalhe="buffer descartado"))
            for opening, closing in MARCADORES.items():
                pos = self.buffer.lower().find(opening)
                if pos >= 0 and self.buffer.lower().find(closing, pos) < 0:
                    self.descartar_ate = closing
                    break
            self.buffer = ''
            return ''
        result = self._processar(final=False)
        self.contexto = (self.contexto + result)[-MAX_BUFFER:]
        return result

    def finalizar(self) -> tuple[str, list[dict]]:
        """Fecha o stream; devolve (texto_restante, erros_estruturados)."""
        if self.descartar_ate:
            self.buffer = ''
            return '', list(self.erros)
        return self._processar(final=True), list(self.erros)


def sanitizar_texto(texto: str) -> tuple[str, list[dict]]:
    """Versão sem streaming. Retorna (texto_limpo, erros)."""
    s = Sanitizador()
    partes = [s.alimentar(texto or "")]
    fim, erros = s.finalizar()
    partes.append(fim)
    return "".join(partes), erros
