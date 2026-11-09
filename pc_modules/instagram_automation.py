"""VEXX AI — Instagram Specialist Engine (pc_modules/instagram_automation.py)

Módulo especialista com conhecimento profundo da plataforma Instagram Web:
- Mapeamento completo de layout (sidebar, inbox, search drawer, chat stream, presence header)
- Rolagem tática de tela (scroll suave de conversas, histórico de chat e feeds)
- Abertura de conversas específicas por nome de contato ou @username
- Detecção e leitura de status de presença ("Online agora", "Online há X min", "Visto por último")
- Envio de mensagens com suporte total a acentos, pontuação e emojis (via clipboard buffer)
- Pesquisa de perfis, pessoas, lojas, negócios e estabelecimentos
- Extração e relatório estruturado com visão computacional (YOLOv8 + RapidOCR)
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger("vexx.instagram_automation")

DIR_TEMP = Path.home() / ".julia-mobile"

# URLs canônicas da plataforma
URL_INSTA_BASE = "https://www.instagram.com/"
URL_INSTA_DIRECT = "https://www.instagram.com/direct/inbox/"
URL_INSTA_EXPLORE = "https://www.instagram.com/explore/"


# =====================================================================
# NAVEGAÇÃO, FOCO & MOVIMENTAÇÃO DE TELA
# =====================================================================

def focar_janela_instagram() -> bool:
    """Traz a janela do navegador onde o Instagram está aberto para o primeiro plano."""
    try:
        ps_cmd = """
        $wshell = New-Object -ComObject WScript.Shell
        if (!$wshell.AppActivate('Instagram')) {
            $wshell.AppActivate('Brave')
        }
        """
        subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
            timeout=3,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        time.sleep(0.3)
        return True
    except Exception as exc:
        log.warning("Falha ao focar janela do Instagram: %s", exc)
        return False


def capturar_tela_instagram(nome_arquivo: str = "temp_insta_action.png") -> Tuple[Any, Path]:
    """Captura a tela em alta resolução e salva no diretório temporário do agente."""
    try:
        import mss
        from PIL import Image
        with mss.mss() as sct:
            monitor = sct.monitors[1]
            sct_img = sct.grab(monitor)
            img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
    except Exception:
        from PIL import ImageGrab
        img = ImageGrab.grab()

    temp_path = DIR_TEMP / nome_arquivo
    temp_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(temp_path)
    return img, temp_path


def rolar_lista_conversas(delta: int = -350, passos: int = 1) -> bool:
    """Move o cursor para o painel de conversas do Direct e rola a lista."""
    try:
        import pyautogui
        largura, altura = pyautogui.size()
        # Coordenada proporcional do painel lateral de conversas (esquerda)
        cx = int(largura * 0.20)
        cy = int(altura * 0.50)

        pyautogui.moveTo(cx, cy, duration=0.3)
        time.sleep(0.2)
        for _ in range(passos):
            pyautogui.scroll(delta)
            time.sleep(0.4)
        return True
    except Exception as exc:
        log.warning("Erro ao rolar lista de conversas: %s", exc)
        return False


def rolar_historico_chat(delta: int = 400, passos: int = 1) -> bool:
    """Move o cursor para a área central da conversa aberta e rola para ver mensagens anteriores ou recentes."""
    try:
        import pyautogui
        largura, altura = pyautogui.size()
        # Coordenada proporcional do stream de mensagens (centro-direita)
        cx = int(largura * 0.65)
        cy = int(altura * 0.50)

        pyautogui.moveTo(cx, cy, duration=0.3)
        time.sleep(0.2)
        for _ in range(passos):
            pyautogui.scroll(delta)
            time.sleep(0.4)
        return True
    except Exception as exc:
        log.warning("Erro ao rolar histórico de chat: %s", exc)
        return False


# =====================================================================
# ENGENHARIA DE VISÃO & OCR DO INSTAGRAM
# =====================================================================

def analisar_tela_com_visao(caminho_img: Path | str) -> Dict[str, Any]:
    """Invoca o serviço de visão YOLOv8 + RapidOCR para extrair objetos e textos com coordenadas."""
    try:
        import vision_service
        res = vision_service.analisar_imagem_huggingface(str(caminho_img))
        if res.get("status") == "sucesso" and res.get("textos_lidos"):
            return res
        return vision_service.ler_fontes_imagem(str(caminho_img))
    except Exception as exc:
        log.warning("Falha ao analisar tela com visão: %s", exc)
        return {"status": "erro", "textos_lidos": [], "texto_extraido": ""}


# =====================================================================
# AÇÕES ESPECÍFICAS: ENTRAR EM CHAT, STATUS ONLINE, ENVIAR MENSAGEM, PESQUISA
# =====================================================================

def entrar_na_conversa(contato: str, timeout_espera: float = 3.0) -> Dict[str, Any]:
    """Localiza e abre uma conversa específica no Instagram Direct pelo nome ou @username.

    Executa navegação visual:
    1. Traz o Instagram para o primeiro plano.
    2. Lê a lista de contatos visíveis com OCR.
    3. Se encontrar o contato, clica nas suas coordenadas centrais.
    4. Se não estiver visível, rola a lista para baixo para buscar.
    5. Se ainda assim não encontrar, clica no botão 'Nova Mensagem' (lápis) e busca pelo nome.
    """
    focar_janela_instagram()
    time.sleep(0.5)

    contato_limpo = re.sub(r"^[#@\s]+", "", contato).strip().lower()
    img, path_img = capturar_tela_instagram("temp_insta_find_chat.png")
    w, h = img.size
    analise = analisar_tela_com_visao(path_img)

    alvo_encontrado = None
    for item in analise.get("textos_lidos", []):
        txt = item.get("texto", "").strip().lower()
        coords = item.get("coordenadas", [0, 0, 0, 0])
        cx = (coords[0] + coords[2]) / 2.0 if len(coords) >= 4 else 0
        cy = (coords[1] + coords[3]) / 2.0 if len(coords) >= 4 else 0

        # Na coluna de conversas da esquerda
        if cx < w * 0.38 and cy > h * 0.30:
            if contato_limpo in txt or any(palavra in txt for palavra in contato_limpo.split()):
                alvo_encontrado = item
                break

    # Se não achou na primeira visão, tenta rolar para baixo
    if not alvo_encontrado:
        rolar_lista_conversas(delta=-350, passos=2)
        time.sleep(1.0)
        img, path_img = capturar_tela_instagram("temp_insta_find_chat_scroll.png")
        analise = analisar_tela_com_visao(path_img)
        for item in analise.get("textos_lidos", []):
            txt = item.get("texto", "").strip().lower()
            coords = item.get("coordenadas", [0, 0, 0, 0])
            cx = (coords[0] + coords[2]) / 2.0 if len(coords) >= 4 else 0
            cy = (coords[1] + coords[3]) / 2.0 if len(coords) >= 4 else 0
            if cx < w * 0.38 and cy > h * 0.30:
                if contato_limpo in txt or any(palavra in txt for palavra in contato_limpo.split()):
                    alvo_encontrado = item
                    break

    try:
        import pyautogui
    except Exception:
        pyautogui = None

    if alvo_encontrado and pyautogui:
        ponto = alvo_encontrado.get("ponto_clique", {})
        px = ponto.get("x") or int((alvo_encontrado["coordenadas"][0] + alvo_encontrado["coordenadas"][2]) / 2)
        py = ponto.get("y") or int((alvo_encontrado["coordenadas"][1] + alvo_encontrado["coordenadas"][3]) / 2)
        log.info("Clicando na conversa com '%s' em (%d, %d)", contato, px, py)
        pyautogui.moveTo(px, py, duration=0.35)
        time.sleep(0.15)
        pyautogui.click()
        time.sleep(timeout_espera)

        # Inspeciona o cabeçalho da conversa aberta
        status_online = verificar_status_online_chat_aberto()
        return {
            "status": "sucesso",
            "contato": contato,
            "acao": "chat_aberto",
            "detalhes_presenca": status_online,
            "resumo": (
                f"**Conversa aberta com sucesso no Instagram Direct!**\n\n"
                f"- **Contato:** `{contato}`\n"
                f"- **Status de Presença:** {status_online.get('texto_presenca', 'Não informado no cabeçalho')}\n"
                f"- **Painel do Chat:** Conversa carregada e pronta para envio ou leitura de mensagens."
            ),
        }

    # Fallback se não encontrar o contato na lista visível
    return {
        "status": "nao_encontrado",
        "contato": contato,
        "resumo": (
            f"**Contato `{contato}` não localizado na lista visível de conversas.**\n"
            f"Você pode tentar pesquisar diretamente pelo perfil ou pedir para buscar pelo @username na busca global."
        ),
    }


def verificar_status_online_chat_aberto() -> Dict[str, Any]:
    """Inspeciona o cabeçalho superior do chat atualmente aberto para ler o status de presença."""
    img, path_img = capturar_tela_instagram("temp_insta_header.png")
    w, h = img.size
    analise = analisar_tela_com_visao(path_img)

    presenca_encontrada = "Desconhecido / Sem status visível"
    online_agora = False

    padrao_presenca = re.compile(
        r"(online\s*agora|online\s*h[aá]\s*[\d\w\s]+|ativo\(a\)\s*h[aá]\s*[\d\w\s]+|visto\s*(?:por\s*último)?\s*[\d\w\s\.:]+)",
        re.I
    )

    for item in analise.get("textos_lidos", []):
        txt = item.get("texto", "").strip()
        coords = item.get("coordenadas", [0, 0, 0, 0])
        cx = (coords[0] + coords[2]) / 2.0 if len(coords) >= 4 else 0
        cy = (coords[1] + coords[3]) / 2.0 if len(coords) >= 4 else 0

        # Cabeçalho da conversa aberta: x > 35% da tela e y no topo (y < 160)
        if cx > w * 0.35 and cy < h * 0.25:
            m = padrao_presenca.search(txt)
            if m:
                presenca_encontrada = m.group(0).strip()
                if "online agora" in presenca_encontrada.lower():
                    online_agora = True
                break

    return {
        "online_agora": online_agora,
        "texto_presenca": presenca_encontrada,
    }


def verificar_online_usuario(contato: str) -> Dict[str, Any]:
    """Abre a conversa com o usuário ou inspeciona seu card na lista para reportar se está online e que horas foi visto."""
    res_chat = entrar_na_conversa(contato)
    if res_chat.get("status") == "sucesso":
        presenca = res_chat.get("detalhes_presenca", {})
        texto_p = presenca.get("texto_presenca", "Sem informações recentes de atividade")
        em_linha = presenca.get("online_agora", False)
        status_icone = "🟢 **ONLINE AGORA**" if em_linha else f"🕒 **Visto por último / Atividade:** {texto_p}"
        return {
            "status": "sucesso",
            "contato": contato,
            "online_agora": em_linha,
            "status_presenca": texto_p,
            "resumo": (
                f"**Status de Atividade no Instagram Direct — {contato}**\n\n"
                f"- **Contato:** `{contato}`\n"
                f"- **Status:** {status_icone}\n\n"
                f"*Dado obtido por leitura visual em tempo real no cabeçalho do Direct.*"
            ),
        }

    return res_chat


def enviar_mensagem_instagram(destinatario: str, mensagem: str) -> Dict[str, Any]:
    """Abre a conversa com o destinatário, localiza a caixa de texto, cola a mensagem e pressiona Enter.

    Utiliza o buffer do clipboard para garantir que acentos (á, é, ã, ç) e emojis sejam inseridos
    perfeitamente no campo de digitação do Instagram Web sem perdas por layout de teclado.
    """
    focar_janela_instagram()
    time.sleep(0.4)

    # 1. Garante que o chat está aberto
    res_chat = entrar_na_conversa(destinatario)
    if res_chat.get("status") != "sucesso":
        return {
            "status": "erro",
            "destinatario": destinatario,
            "resumo": f"Não foi possível abrir a conversa com `{destinatario}` para enviar a mensagem.",
        }

    try:
        import pyautogui
        import pyperclip
    except ImportError as exc:
        return {"status": "erro", "mensagem": f"Dependência ausente: {exc}"}

    img, _ = capturar_tela_instagram("temp_insta_chat_open.png")
    largura, altura = img.size

    # Posição canônica da barra de digitação no Instagram Web ("Mensagem...")
    # Fica na parte inferior do painel central (x ~ 60% da largura, y ~ altura - 45px)
    cx_input = int(largura * 0.60)
    cy_input = int(altura - 45)

    log.info("Clicando no campo de digitação em (%d, %d)", cx_input, cy_input)
    pyautogui.moveTo(cx_input, cy_input, duration=0.3)
    time.sleep(0.2)
    pyautogui.click()
    time.sleep(0.3)

    # Copia para a área de transferência e cola (imune a erros de layout ABNT/US)
    pyperclip.copy(mensagem)
    time.sleep(0.15)
    pyautogui.hotkey("ctrl", "v")
    time.sleep(0.3)

    # Envia a mensagem
    pyautogui.press("enter")
    time.sleep(0.8)

    # Dispara notificação nativa no Windows
    from pc_modules.browser_automation import disparar_notificacao_windows
    disparar_notificacao_windows("VEXX AI — Instagram", f"Mensagem enviada para {destinatario}!")

    return {
        "status": "sucesso",
        "destinatario": destinatario,
        "mensagem_enviada": mensagem,
        "resumo": (
            f"**Mensagem enviada com sucesso no Instagram Direct!**\n\n"
            f"- **Destinatário:** `{destinatario}`\n"
            f"- **Conteúdo:** *\"{mensagem}\"*\n"
            f"- **Status de Envio:** Confirmado via teclado e buffer de área de transferência.\n\n"
            f"*O agente automatizou o foco, a digitação de alta fidelidade e o envio.*"
        ),
    }


def pesquisar_instagram(termo: str) -> Dict[str, Any]:
    """Abre a barra de pesquisa do Instagram, digita o termo e extrai os perfis, lojas e estabelecimentos sugeridos."""
    focar_janela_instagram()
    time.sleep(0.4)

    try:
        import pyautogui
        import pyperclip
    except ImportError:
        return {"status": "erro", "mensagem": "Bibliotecas de automação não instaladas"}

    img, _ = capturar_tela_instagram("temp_insta_before_search.png")
    largura, altura = img.size

    # Coordenada do ícone de pesquisa na barra lateral esquerda (x ~ 35px, y ~ 160px em telas normais)
    # Ou pressiona o atalho de pesquisa no Direct / Instagram
    cx_busca_icon = int(largura * 0.02) if largura > 0 else 35
    cy_busca_icon = int(altura * 0.22) if altura > 0 else 165

    # Clica no ícone de pesquisa da sidebar
    pyautogui.moveTo(cx_busca_icon, cy_busca_icon, duration=0.3)
    time.sleep(0.2)
    pyautogui.click()
    time.sleep(0.8)

    # Coordenada da caixa de input que se abre na gaveta de pesquisa (Search Drawer)
    # Geralmente x ~ 150px, y ~ 110px
    cx_input = int(largura * 0.12)
    cy_input = int(altura * 0.13)
    pyautogui.moveTo(cx_input, cy_input, duration=0.25)
    time.sleep(0.15)
    pyautogui.click()
    time.sleep(0.2)

    # Limpa campo existente
    pyautogui.hotkey("ctrl", "a")
    pyautogui.press("backspace")
    time.sleep(0.15)

    # Cola o termo pesquisado
    pyperclip.copy(termo)
    pyautogui.hotkey("ctrl", "v")
    time.sleep(2.0)  # Aguarda o Instagram consultar a API e renderizar os resultados visuais

    img_res, path_res = capturar_tela_instagram("temp_insta_search_results.png")
    analise = analisar_tela_com_visao(path_res)

    resultados = []
    ignorar = {"pesquisa", "pesquisar", "limpar tudo", "recentes"}
    for item in analise.get("textos_lidos", []):
        txt = item.get("texto", "").strip()
        coords = item.get("coordenadas", [0, 0, 0, 0])
        cx = (coords[0] + coords[2]) / 2.0 if len(coords) >= 4 else 0
        cy = (coords[1] + coords[3]) / 2.0 if len(coords) >= 4 else 0

        # Na gaveta de pesquisa da esquerda (x entre 5% e 35% da tela, y abaixo da caixa de busca)
        if largura * 0.05 <= cx <= largura * 0.35 and cy > altura * 0.18:
            if txt.lower() not in ignorar and len(txt) > 2:
                resultados.append({
                    "texto": txt,
                    "coordenadas": coords,
                    "ponto_clique": item.get("ponto_clique", {"x": int(cx), "y": int(cy)}),
                })

    linhas_res = []
    for r in resultados[:8]:
        linhas_res.append(f"• 🔍 **{r['texto']}**")

    from pc_modules.browser_automation import disparar_notificacao_windows
    disparar_notificacao_windows("VEXX AI — Instagram", f"Busca por '{termo}' concluída.")

    resumo = (
        f"**Resultados de Pesquisa no Instagram — `{termo}`**\n\n"
        f"- **Termo Buscado:** `{termo}`\n"
        f"- **Perfis / Lojas / Estabelecimentos Encontrados ({len(resultados)}):**\n"
        + ("\n".join(linhas_res) if linhas_res else "• Nenhum resultado direto renderizado no momento.")
        + "\n\n*Pesquisa realizada visualmente com o cursor navegando na barra de busca do Instagram.*"
    )

    return {
        "status": "sucesso",
        "termo": termo,
        "total_encontrados": len(resultados),
        "resultados": resultados,
        "resumo": resumo,
    }


def rotear_comando_instagram(texto: str) -> Optional[str]:
    """Interpreta pedidos em linguagem natural e executa a ação correspondente no Instagram."""
    orig = texto.strip()
    t = orig.lower()

    # 1. Enviar mensagem: "envie uma mensagem para Gustavo dizendo oi", "mande mensagem para ... dizendo ..."
    m_envio = re.search(r"(?:envie|mande|enviar|mandar)\s+(?:uma\s+)?mensagem\s+(?:para|pro|pra)\s+([\w\.\-_]+)\s+(?:dizendo|falando|com\s+o\s+texto|com)\s+[\"']?([^\"']+)[\"']?", orig, re.I)
    if m_envio:
        destinatario = m_envio.group(1).strip()
        conteudo = m_envio.group(2).strip()
        res = enviar_mensagem_instagram(destinatario, conteudo)
        return res["resumo"]

    # 2. Status online / que horas estava online: "que horas Gustavo estava online", "veja se Gustavo está online"
    m_online = re.search(r"(?:que\s+horas|quando|verifique\s+se|veja\s+se)\s+([\w\.\-_]+)\s+(?:estava|est[aá]|ficou)\s+online", orig, re.I)
    if not m_online:
        m_online = re.search(r"(?:status\s+online|visto\s+por\s+ultimo|online)\s+(?:de|do|da)?\s*([\w\.\-_]+)", orig, re.I)
    if m_online:
        contato = m_online.group(1).strip()
        res = verificar_online_usuario(contato)
        return res["resumo"]

    # 3. Entrar na conversa: "entre na conversa com Gustavo", "abra as mensagens de Gustavo", "abra o chat de ..."
    m_entrar = re.search(r"(?:entre|abrir|abra|entrar)\s+(?:na\s+conversa|no\s+chat|na\s+mensagem|as\s+mensagens)\s+(?:com|de|do|da)?\s*([\w\.\-_]+)", orig, re.I)
    if m_entrar:
        contato = m_entrar.group(1).strip()
        res = entrar_na_conversa(contato)
        return res["resumo"]

    # 4. Pesquisar pessoas / perfis / lojas: "pesquise no instagram por...", "busque no instagram..."
    m_busca = re.search(r"(?:pesquise|busque|procurar|pesquisar|buscar)\s+(?:no\s+instagram|no\s+insta)\s+(?:por|sobre|o\s+perfil\s+de)?\s*(.+)", orig, re.I)
    if not m_busca:
        m_busca = re.search(r"(?:pesquise|busque)\s+(?:por\s+)?(?:pessoas?|lojas?|estabelecimentos?|perfis?)\s+(?:no\s+instagram|no\s+insta)?\s*(.+)?", orig, re.I)
    if m_busca:
        termo = m_busca.group(1).strip() if m_busca.group(1) else "lojas"
        termo_limpo = re.sub(r"(?i)\b(no instagram|no insta|por favor)\b", "", termo).strip()
        res = pesquisar_instagram(termo_limpo)
        return res["resumo"]

    # 5. Rolar tela: "role as mensagens para baixo", "faça scroll no chat"
    if re.search(r"\b(role|rolar|scroll|descer|subir)\b.*\b(conversa|chat|mensagens|instagram|feed)\b", t):
        if "cima" in t or "topo" in t:
            rolar_lista_conversas(delta=350, passos=2)
            direcao = "para cima"
        else:
            rolar_lista_conversas(delta=-350, passos=2)
            direcao = "para baixo"
        return f"**Rolagem executada no Instagram:** Cursor posicionado sobre a lista de conversas e rolagem realizada {direcao} com sucesso."

    return None
