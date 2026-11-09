"""Módulo de Execução e Orquestração de Ferramentas (Tool Calling) do VEXX AI.

Compatível com Qwen 2.5 3B Instruct, Hermes / ChatML (<tool_call>),
e acionamento determinístico de visão, automação de navegador, Instagram,
modelagem 3D generativa, pesquisa de produtos e memória.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger("JULIA-tool-execution")

FERRAMENTAS_CATALOGO = [
    {
        "type": "function",
        "function": {
            "name": "navegador_instagram",
            "description": "Controla automação no Instagram Web: abre direct, verifica mensagens não lidas, entra em conversas, envia mensagens e pesquisa pessoas ou perfis.",
            "parameters": {
                "type": "object",
                "properties": {
                    "acao": {
                        "type": "string",
                        "enum": ["abrir_inbox", "verificar_mensagens", "entrar_conversa", "enviar_mensagem", "pesquisar", "verificar_online", "rolar"],
                        "description": "Ação a executar no Instagram."
                    },
                    "contato": {"type": "string", "description": "Nome do contato para abrir conversa, enviar mensagem ou checar status online."},
                    "mensagem": {"type": "string", "description": "Texto da mensagem a ser enviada no chat."},
                    "termo": {"type": "string", "description": "Termo de busca para a barra de pesquisa do Instagram."},
                    "direcao": {"type": "string", "enum": ["baixo", "cima"], "description": "Direção de rolagem (padrão: baixo)."}
                },
                "required": ["acao"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "navegador_web",
            "description": "Abre páginas no navegador padrão, pesquisa na web ou interage com a tela.",
            "parameters": {
                "type": "object",
                "properties": {
                    "acao": {"type": "string", "enum": ["abrir_url", "pesquisar", "rolar"], "description": "Ação de navegação."},
                    "url": {"type": "string", "description": "URL completa a ser aberta no navegador padrão."},
                    "termo": {"type": "string", "description": "Termo de pesquisa na web."},
                    "direcao": {"type": "string", "enum": ["baixo", "cima"], "description": "Direção da rolagem."}
                },
                "required": ["acao"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "gerar_modelo_3d",
            "description": "Gera um modelo 3D mecânico, científico, espacial ou mapa interativo com materiais PBR e separação explodida.",
            "parameters": {
                "type": "object",
                "properties": {
                    "prompt": {"type": "string", "description": "Descrição detalhada do objeto, máquina, órgão ou mapa 3D a ser gerado."},
                    "tipo": {"type": "string", "enum": ["modelo", "mapa", "especificacao"], "description": "Tipo de síntese 3D."}
                },
                "required": ["prompt"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "pesquisa_produtos_e_precos",
            "description": "Pesquisa produtos, preços e ofertas em tempo real em lojas como KaBuM!, Amazon e Mercado Livre.",
            "parameters": {
                "type": "object",
                "properties": {
                    "termo": {"type": "string", "description": "Nome do produto ou especificação procurada."},
                    "preco_maximo": {"type": "number", "description": "Orçamento máximo em Reais (R$)."}
                },
                "required": ["termo"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "visao_computacional",
            "description": "Analisa a tela do computador ou imagem fornecida utilizando YOLOv8 e RapidOCR para detectar alvos e botões de clique.",
            "parameters": {
                "type": "object",
                "properties": {
                    "alvo": {"type": "string", "description": "Texto ou objeto a ser localizado na tela."},
                    "clicar": {"type": "boolean", "description": "Se verdadeiro, move o cursor e clica no alvo localizado."}
                },
                "required": ["alvo"]
            }
        }
    }
]


def extrair_chamadas_tool_call(texto: str) -> List[Dict[str, Any]]:
    """Extrai chamadas estruturadas de ferramentas no formato <tool_call> ou ```tool_calls."""
    chamadas: List[Dict[str, Any]] = []
    if not texto:
        return chamadas

    # 1. Formato <tool_call>{"name": ..., "arguments": ...}</tool_call>
    matches_tags = re.findall(r"<tool_call>([\s\S]*?)(?:</tool_call>|$)", texto, re.I)
    for bloco in matches_tags:
        bloco_clean = bloco.strip()
        inicio_json = bloco_clean.find("{")
        if inicio_json >= 0:
            fim_json = bloco_clean.rfind("}")
            if fim_json > inicio_json:
                json_str = bloco_clean[inicio_json:fim_json + 1]
                try:
                    parsed = json.loads(json_str)
                    if isinstance(parsed, dict) and "name" in parsed:
                        chamadas.append(parsed)
                    elif isinstance(parsed, list):
                        chamadas.extend([p for p in parsed if isinstance(p, dict) and "name" in p])
                except Exception:
                    pass

    # 2. Formato ```tool_calls [...] ```
    matches_code = re.findall(r"```tool_calls\s*([\s\S]*?)\s*```", texto, re.I)
    for bloco in matches_code:
        try:
            parsed = json.loads(bloco.strip())
            if isinstance(parsed, list):
                chamadas.extend([p for p in parsed if isinstance(p, dict) and "name" in p])
            elif isinstance(parsed, dict) and "name" in parsed:
                chamadas.append(parsed)
        except Exception:
            pass

    return chamadas


def executar_ferramenta(nome: str, argumentos: Dict[str, Any]) -> Dict[str, Any]:
    """Despacha a chamada da ferramenta para os módulos nativos correspondentes."""
    args = argumentos if isinstance(argumentos, dict) else {}
    nome_norm = (nome or "").strip().lower()

    log.info("EXECUTANDO_FERRAMENTA nome=%s args=%s", nome_norm, args)

    # 1. Instagram
    if "instagram" in nome_norm:
        from pc_modules import instagram_automation
        acao = str(args.get("acao") or "").lower()
        contato = str(args.get("contato") or "").strip()
        msg = str(args.get("mensagem") or "").strip()
        termo = str(args.get("termo") or "").strip()
        direcao = str(args.get("direcao") or "baixo").lower()

        if any(v in acao for v in ("inbox", "abrir_inbox", "abrir")):
            return instagram_automation.abrir_instagram_direct()
        elif any(v in acao for v in ("verificar", "ler", "checar", "notificac")):
            return instagram_automation.verificar_mensagens_instagram_visual()
        elif any(v in acao for v in ("entrar", "conversa")):
            if not contato:
                return {"status": "erro", "mensagem": "Nome do contato obrigatório para entrar na conversa."}
            return instagram_automation.entrar_na_conversa(contato)
        elif any(v in acao for v in ("enviar", "mandar", "msg")):
            if not contato or not msg:
                return {"status": "erro", "mensagem": "Contato e texto da mensagem são obrigatórios."}
            return instagram_automation.enviar_mensagem_instagram(contato, msg)
        elif any(v in acao for v in ("pesquisar", "buscar")):
            if not termo:
                return {"status": "erro", "mensagem": "Termo de busca obrigatório."}
            return instagram_automation.pesquisar_instagram(termo)
        elif any(v in acao for v in ("online", "visto")):
            if not contato:
                return {"status": "erro", "mensagem": "Contato obrigatório para checar status online."}
            return instagram_automation.verificar_online_usuario(contato)
        elif "rolar" in acao or "scroll" in acao:
            return instagram_automation.interagir_e_rolar_mouse(direcao=direcao, passos=5)
        else:
            return instagram_automation.verificar_mensagens_instagram_visual()

    # 2. Navegador Web
    elif "navegador" in nome_norm or "browser" in nome_norm:
        from pc_modules import browser_automation, instagram_automation
        acao = str(args.get("acao") or "").lower()
        url = str(args.get("url") or "").strip()
        termo = str(args.get("termo") or "").strip()
        direcao = str(args.get("direcao") or "baixo").lower()

        if "rolar" in acao or "scroll" in acao:
            return instagram_automation.interagir_e_rolar_mouse(direcao=direcao, passos=5)
        elif url:
            return browser_automation.abrir_url_navegador_padrao(url)
        elif termo:
            return browser_automation.abrir_pesquisa_navegador_padrao(termo)
        return {"status": "ok", "mensagem": "Navegador focado com sucesso."}

    # 3. Modelagem 3D e Mapas
    elif "3d" in nome_norm or "mapa" in nome_norm:
        import model3d_generative
        prompt = str(args.get("prompt") or "").strip()
        tipo = str(args.get("tipo") or "modelo").lower()
        if tipo == "mapa" or "mapa" in prompt.lower():
            cena = model3d_generative.gerar_mapa_3d(prompt)
        else:
            cena = model3d_generative.gerar_modelo_3d(prompt)
        fence = f"````model3d\n{json.dumps(cena, ensure_ascii=False, indent=2)}\n````"
        return {
            "status": "sucesso",
            "tipo": "model3d",
            "titulo": cena.get("title", "Modelo 3D VEXX"),
            "fence": fence,
            "descricao": cena.get("description", "")
        }

    # 4. Produtos e Preços (Shopping)
    elif "produto" in nome_norm or "shopping" in nome_norm or "preco" in nome_norm:
        import shopping
        termo = str(args.get("termo") or args.get("produto") or "").strip()
        p_max = float(args.get("preco_maximo") or 0)
        return shopping.pesquisar_produtos(termo, preco_maximo=p_max if p_max > 0 else None)

    # 5. Visão Computacional
    elif "visao" in nome_norm or "tela" in nome_norm:
        import vision_service
        alvo = str(args.get("alvo") or "").strip()
        clicar = bool(args.get("clicar", False))
        if clicar and alvo:
            return vision_service.clicar_alvo_tela(alvo, autorizado=True)
        return vision_service.analisar_imagem_tela(alvo)

    return {"status": "desconhecido", "mensagem": f"Ferramenta '{nome}' não catalogada."}


def formatar_resultado_ferramenta(nome: str, res: Dict[str, Any]) -> str:
    """Gera uma apresentação limpa e agradável em markdown para o resultado da ferramenta."""
    nome_norm = (nome or "").lower()

    if "3d" in nome_norm or res.get("tipo") == "model3d":
        fence = res.get("fence", "")
        tit = res.get("titulo", "Modelo 3D Interativo VEXX")
        desc = res.get("descricao", "")
        return f"\n\n### {tit}\n{desc}\n\n{fence}\n"

    if "instagram" in nome_norm:
        from pc_modules import instagram_automation
        return instagram_automation.formatar_relatorio_instagram(res)

    if "produto" in nome_norm or "shopping" in nome_norm:
        prods = res.get("produtos") or []
        if prods:
            linhas = [
                "### Ofertas e Comparativo de Produtos Verificados",
                "| Produto | Preço | Loja | Avaliação | Link |",
                "| :--- | :--- | :--- | :--- | :--- |"
            ]
            for p in prods[:5]:
                nome_p = p.get("nome", "Produto")[:40]
                preco_p = f"R$ {p.get('preco', 0):.2f}"
                loja_p = p.get("loja", "Loja Online")
                nota_p = f"⭐ {p.get('nota', 4.8)}"
                link_p = f"[Ver Oferta]({p.get('link', '#')})"
                linhas.append(f"| **{nome_p}** | {preco_p} | {loja_p} | {nota_p} | {link_p} |")
            return "\n\n" + "\n".join(linhas) + "\n\n"

    if isinstance(res, dict) and "mensagem" in res:
        return f"\n\n*Ação concluída:* {res['mensagem']}\n\n"

    return f"\n\n```json\n{json.dumps(res, ensure_ascii=False, indent=2)}\n```\n\n"


def processar_e_executar_chamadas(texto: str) -> Tuple[str, List[Dict[str, Any]]]:
    """Detecta, executa e substitui blocos de tool call pelo resultado renderizado."""
    chamadas = extrair_chamadas_tool_call(texto)
    if not chamadas:
        return texto, []

    resultados: List[Dict[str, Any]] = []
    texto_limpo = texto

    # Remove os blocos brutos de tool call
    texto_limpo = re.sub(r"<tool_call>[\s\S]*?</tool_call>", "", texto_limpo, flags=re.I)
    texto_limpo = re.sub(r"```tool_calls[\s\S]*?```", "", texto_limpo, flags=re.I)
    texto_limpo = texto_limpo.strip()

    adicoes: List[str] = []
    for call in chamadas:
        nome = call.get("name") or call.get("nome") or ""
        args = call.get("arguments") or call.get("argumentos") or {}
        try:
            res = executar_ferramenta(nome, args)
            resultados.append({"chamada": call, "resultado": res})
            bloco_fmt = formatar_resultado_ferramenta(nome, res)
            if bloco_fmt:
                adicoes.append(bloco_fmt)
        except Exception as exc:
            log.warning("Falha na execucao da ferramenta %s: %s", nome, exc)
            adicoes.append(f"\n\n> *Aviso:* Não foi possível concluir a ação '{nome}': {exc}\n\n")

    texto_final = (texto_limpo + "\n" + "\n".join(adicoes)).strip()
    return texto_final, resultados
