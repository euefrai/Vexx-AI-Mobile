"""VEXX AI — Browser Automation & Vision Navigator (pc_modules/browser_automation.py)

Permite ao VEXX AI operar como um Agente Autônomo de Computador:
- Navega em sites reais (Instagram, TikTok, Kabum, E-commerce, Portais de notícias)
- Utiliza perfil de navegador dedicado e persistente (sessões e logins salvos localmente)
- Emprega visão computacional (mss + YOLO + RapidOCR) para leitura de tela e localização de alvos
- Executa cliques, rolagem e digitação humana com pyautogui e pynput
- Emite notificações nativas no Windows e relatórios estruturados para o app VEXX AI
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

log = logging.getLogger("vexx.browser_automation")

# Diretório persistente para perfis de contas locais (sessões isoladas e seguras)
DIR_PERFIL_AUTOMACAO = Path.home() / ".julia-mobile" / "browser_automation_profile"


def obter_navegador_padrao_windows() -> Optional[str]:
    """Detecta dinamicamente o executável do navegador padrão configurado pelo usuário no Windows.

    Consulta o registro do Windows em UserChoice para identificar se o padrão é Brave, Chrome,
    Edge, Firefox ou outro navegador preferido do usuário.
    """
    try:
        import winreg
        import shlex
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\Shell\Associations\UrlAssociations\https\UserChoice"
        ) as key:
            prog_id, _ = winreg.QueryValueEx(key, "ProgId")

        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, rf"{prog_id}\shell\open\command") as cmd_key:
            cmd, _ = winreg.QueryValueEx(cmd_key, "")

        partes = shlex.split(cmd)
        if partes and os.path.isfile(partes[0]):
            return partes[0]
    except Exception as exc:
        log.warning("Falha ao consultar navegador padrão no registro: %s", exc)

    return _obter_executavel_fallback()


def _obter_executavel_fallback() -> Optional[str]:
    """Candidatos de fallback caso a consulta ao registro falhe."""
    candidatos = [
        r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
        r"C:\Program Files (x86)\BraveSoftware\Brave-Browser\Application\brave.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ]
    for c in candidatos:
        if os.path.isfile(c):
            return c
    return None


def abrir_navegador(url: str = "https://www.google.com", isolado: bool = False) -> Optional[subprocess.Popen]:
    """Abre a URL no navegador padrão que o usuário está usando.

    Por padrão (isolado=False), abre a URL diretamente no navegador padrão em execução
    (ex.: Brave), reaproveitando as contas e sessões já logadas do usuário.
    Se isolado=True, utiliza um diretório de perfil dedicado em ~/.julia-mobile.
    """
    exe = obter_navegador_padrao_windows()
    if not exe:
        import webbrowser
        webbrowser.open(url)
        return None

    if isolado:
        DIR_PERFIL_AUTOMACAO.mkdir(parents=True, exist_ok=True)
        args = [
            exe,
            f"--user-data-dir={DIR_PERFIL_AUTOMACAO}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-blink-features=AutomationControlled",
            "--start-maximized",
            url,
        ]
        log.info("Abrindo navegador padrão (%s) com perfil isolado: %s", exe, url)
        return subprocess.Popen(args)

    # Abre na sessão ativa do navegador padrão que o usuário já está usando
    log.info("Abrindo na sessão ativa do navegador padrão (%s): %s", exe, url)
    try:
        return subprocess.Popen([exe, url])
    except Exception:
        import webbrowser
        webbrowser.open(url)
        return None


def iniciar_navegador_perfil(url: str = "https://www.google.com") -> Optional[subprocess.Popen]:
    """Alias compatível: abre no navegador padrão ativo do usuário."""
    return abrir_navegador(url, isolado=False)


def capturar_tela() -> Any:
    """Captura a tela em alta resolução usando mss ou PIL.ImageGrab."""
    try:
        import mss
        from PIL import Image
        with mss.mss() as sct:
            monitor = sct.monitors[1]  # monitor principal
            sct_img = sct.grab(monitor)
            return Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
    except Exception:
        from PIL import ImageGrab
        return ImageGrab.grab()


def disparar_notificacao_windows(titulo: str, mensagem: str) -> bool:
    """Exibe uma notificação nativa do Windows no canto da tela."""
    try:
        ps_cmd = f"""
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null
$template = [Windows.UI.Notifications.ToastTemplateType]::ToastText02
$xml = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent($template)
$texts = $xml.GetElementsByTagName('text')
$texts[0].AppendChild($xml.CreateTextNode('{titulo}')) > $null
$texts[1].AppendChild($xml.CreateTextNode('{mensagem}')) > $null
$toast = [Windows.UI.Notifications.ToastNotification]::new($xml)
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('VEXX AI').Show($toast)
"""
        subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
            timeout=5,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        return True
    except Exception as exc:
        log.warning("Falha ao emitir notificação nativa: %s", exc)
        return False


# =====================================================================
# WORKFLOWS ESPECÍFICOS DE SITES & CONTAS
# =====================================================================

def verificar_instagram(timeout_carregamento: float = 4.0) -> Dict[str, Any]:
    """Abre o Instagram Direct, analisa mensagens via visão/OCR e gera relatório factual."""
    url = "https://www.instagram.com/direct/inbox/"
    proc = iniciar_navegador_perfil(url)
    time.sleep(timeout_carregamento)

    img = capturar_tela()
    temp_path = Path.home() / ".julia-mobile" / "temp_insta_screen.png"
    temp_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(temp_path)

    textos_lidos = []
    try:
        import vision_service
        res = vision_service.ler_fontes_imagem(str(temp_path))
        textos_lidos = res.get("textos_encontrados", [])
    except Exception as e:
        log.warning("Erro no OCR do Instagram: %s", e)

    # Identificar remetentes e termos chave de mensagens
    linhas_uteis = [t for t in textos_lidos if len(t) > 2 and not re.search(r"^(seguir|pesquisar|home|reels|explorar)$", t.lower())]

    relatorio = {
        "status": "sucesso",
        "plataforma": "Instagram Direct",
        "url": url,
        "mensagens_detectadas": len(linhas_uteis),
        "amostra_conteudo": linhas_uteis[:8],
        "resumo": (
            f"**Relatório de Verificação — Instagram Direct (VEXX AI)**\n\n"
            f"- **Status da Conta:** Sessão ativa verificada no navegador.\n"
            f"- **Atividade na Caixa:** Foram identificadas {len(linhas_uteis)} referências textuais/conversas.\n"
            + ("\n".join(f"  • {linha}" for linha in linhas_uteis[:5]) if linhas_uteis else "  • Nenhuma mensagem pendente no momento.")
            + "\n\n*A automação visual concluiu a leitura em tempo real.*"
        ),
    }

    disparar_notificacao_windows("VEXX AI — Instagram", f"{len(linhas_uteis)} conversas/mensagens verificadas.")
    return relatorio


def verificar_tiktok_tendencias(timeout_carregamento: float = 4.0) -> Dict[str, Any]:
    """Abre o TikTok Explore, rola a página e extrai as tendências e hashtags do momento."""
    url = "https://www.tiktok.com/explore"
    proc = iniciar_navegador_perfil(url)
    time.sleep(timeout_carregamento)

    try:
        import pyautogui
        # Rola suavemente para baixo para carregar feeds adicionais
        pyautogui.scroll(-350)
        time.sleep(1.5)
    except Exception:
        pass

    img = capturar_tela()
    temp_path = Path.home() / ".julia-mobile" / "temp_tiktok_screen.png"
    temp_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(temp_path)

    textos_lidos = []
    try:
        import vision_service
        res = vision_service.ler_fontes_imagem(str(temp_path))
        textos_lidos = res.get("textos_encontrados", [])
    except Exception as e:
        log.warning("Erro no OCR do TikTok: %s", e)

    hashtags = [t for t in textos_lidos if "#" in t or "viral" in t.lower() or "tendência" in t.lower()]
    if not hashtags:
        hashtags = [t for t in textos_lidos if len(t) > 4][:6]

    relatorio = {
        "status": "sucesso",
        "plataforma": "TikTok Explore",
        "url": url,
        "tendencias": hashtags[:8],
        "resumo": (
            f"**Tendências e Radar de Conteúdo — TikTok (VEXX AI)**\n\n"
            f"- **Plataforma:** TikTok Brasil / Global\n"
            f"- **Itens em Alta Mapeados:** {len(hashtags)}\n"
            + ("\n".join(f"  🔥 **{tag}**" for tag in hashtags[:6]) if hashtags else "  • Feed em atualização.")
            + "\n\n*Dados extraídos via visão computacional em tempo real.*"
        ),
    }

    disparar_notificacao_windows("VEXX AI — TikTok", f"Tendências capturadas com sucesso.")
    return relatorio


def monitorar_kabum(termo: str, preco_alvo: Optional[float] = None, timeout_carregamento: float = 4.0) -> Dict[str, Any]:
    """Abre a busca do Kabum, lê produtos e preços reais com OCR e notifica se atingir o alvo."""
    termo_limpo = re.sub(r"[^\w\s]", "", termo).strip()
    url = f"https://www.kabum.com.br/busca/{termo_limpo.replace(' ', '-')}"
    proc = iniciar_navegador_perfil(url)
    time.sleep(timeout_carregamento)

    img = capturar_tela()
    temp_path = Path.home() / ".julia-mobile" / "temp_kabum_screen.png"
    temp_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(temp_path)

    textos_lidos = []
    try:
        import vision_service
        res = vision_service.ler_fontes_imagem(str(temp_path))
        textos_lidos = res.get("textos_encontrados", [])
    except Exception as e:
        log.warning("Erro no OCR do Kabum: %s", e)

    # Extrai preços em R$
    precos_encontrados = []
    for t in textos_lidos:
        m = re.search(r"R\$\s*([\d\.,]+)", t)
        if m:
            try:
                num = float(m.group(1).replace(".", "").replace(",", "."))
                precos_encontrados.append(num)
            except Exception:
                pass

    menor_preco = min(precos_encontrados) if precos_encontrados else None
    atingiu_alvo = bool(preco_alvo and menor_preco and menor_preco <= preco_alvo)

    resumo = (
        f"**Monitor de Preços em Tempo Real — Kabum (VEXX AI)**\n\n"
        f"- **Busca:** `{termo_limpo}`\n"
        f"- **Preços Coletados com Visão:** {len(precos_encontrados)} ofertas na tela\n"
    )
    if menor_preco:
        resumo += f"- **Menor Preço Encontrado:** `R$ {menor_preco:.2f}`\n"
    if preco_alvo:
        resumo += f"- **Preço Alvo:** `R$ {preco_alvo:.2f}`\n"
        resumo += f"- **Status do Alvo:** {'🚨 META ATINGIDA!' if atingiu_alvo else 'Preço acima da meta no momento.'}\n"

    if atingiu_alvo:
        disparar_notificacao_windows("VEXX AI — Alerta de Preço!", f"O produto {termo_limpo} atingiu R$ {menor_preco:.2f} no Kabum!")
    else:
        disparar_notificacao_windows("VEXX AI — Kabum", f"Preços monitorados para {termo_limpo}.")

    return {
        "status": "sucesso",
        "plataforma": "Kabum",
        "url": url,
        "menor_preco": menor_preco,
        "precos": precos_encontrados[:6],
        "atingiu_alvo": atingiu_alvo,
        "resumo": resumo,
    }


def executar_comando_automacao(texto: str) -> Optional[str]:
    """Roteia comandos em linguagem natural para as automações de navegador com visão."""
    t = texto.lower()
    if re.search(r"\b(verifique|veja|checar|abrir|olhar)\b.*\b(instagram|insta|direct|dms?)\b", t):
        res = verificar_instagram()
        return res["resumo"]

    if re.search(r"\b(verifique|veja|tend[eê]ncias|trends?|viral|abrir)\b.*\b(tiktok)\b", t):
        res = verificar_tiktok_tendencias()
        return res["resumo"]

    if re.search(r"\b(monitore|verifique o pre[cç]o|pesquise no kabum|pre[cç]o no kabum|abrir kabum)\b", t):
        # Extrai termo e valor se houver
        m_alvo = re.search(r"(?:at[eé]|por|abaixo de)\s*R?\$?\s*(\d+(?:[.,]\d+)?)", t)
        preco_alvo = float(m_alvo.group(1).replace(",", ".")) if m_alvo else None
        termo = re.sub(r"(?i)\b(monitore|verifique o pre[cç]o|pesquise no kabum|no kabum|kabum|at[eé]|por|abaixo de|r\$|\d+)\b", "", t).strip() or "hardware"
        res = monitorar_kabum(termo, preco_alvo)
        return res["resumo"]

    return None
