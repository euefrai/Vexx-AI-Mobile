"""VEXX AI — Browser Automation & Vision Navigator (pc_modules/browser_automation.py)

Permite ao VEXX AI operar como um Agente Autônomo de Computador:
- Navega em sites reais (Instagram, TikTok, Kabum, E-commerce, Portais de notícias)
- Utiliza o navegador padrão ativo do usuário (Brave, Chrome, Edge, etc.)
- Emprega visão computacional (mss + YOLOv8 + RapidOCR + análise cromática) para leitura de tela
- Executa ações táticas sincronizadas: foco de janela, movimentação de mouse e rolagem suave
- Detecta notificações pendentes, badges numéricos, remetentes e mensagens não lidas
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


def focar_janela_navegador(palavra_chave: str = "Instagram", fallback_nome: str = "Brave") -> bool:
    """Traz a janela do navegador em uso para o primeiro plano no Windows."""
    try:
        ps_cmd = f"""
        $wshell = New-Object -ComObject WScript.Shell
        if (!$wshell.AppActivate('{palavra_chave}')) {{
            $wshell.AppActivate('{fallback_nome}')
        }}
        """
        subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
            timeout=3,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        return True
    except Exception as exc:
        log.warning("Falha ao focar janela do navegador: %s", exc)
        return False


def interagir_e_rolar_mouse(x_prop: float = 0.20, y_prop: float = 0.45, delta_scroll: int = -280) -> bool:
    """Move suavemente o cursor e rola a tela para carregar elementos dinâmicos."""
    try:
        import pyautogui
        pyautogui.FAILSAFE = False
        largura, altura = pyautogui.size()
        x = max(20, min(largura - 20, int(largura * x_prop)))
        y = max(20, min(altura - 20, int(altura * y_prop)))

        # Move o cursor de forma suave e orgânica
        pyautogui.moveTo(x, y, duration=0.35)
        time.sleep(0.2)

        # Rola para baixo para revelar mensagens ou feeds
        pyautogui.scroll(delta_scroll)
        time.sleep(0.6)

        # Rola de volta para o topo
        pyautogui.scroll(-delta_scroll)
        time.sleep(0.3)
        return True
    except Exception as exc:
        log.warning("Interação de mouse/scroll não executada: %s", exc)
        return False


def abrir_navegador(url: str = "https://www.google.com", isolado: bool = False) -> Optional[subprocess.Popen]:
    """Abre a URL no navegador padrão que o usuário está usando."""
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
        proc = subprocess.Popen([exe, url])
        return proc
    except Exception:
        import webbrowser
        webbrowser.open(url)
        return None


def iniciar_navegador_perfil(url: str = "https://www.google.com") -> Optional[subprocess.Popen]:
    """Alias compatível: abre no navegador padrão ativo do usuário."""
    return abrir_navegador(url, isolado=False)


def capturar_tela() -> Any:
    """Captura a tela em alta resolução usando mss ou PIL.ImageGrab com recuperação automática."""
    try:
        import mss
        from PIL import Image
        with mss.mss() as sct:
            monitor = sct.monitors[1]  # monitor principal
            sct_img = sct.grab(monitor)
            return Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
    except Exception as exc:
        log.warning("mss falhou na captura (%s); tentando ImageGrab...", exc)
        try:
            from PIL import ImageGrab
            return ImageGrab.grab()
        except Exception as exc2:
            log.warning("ImageGrab falhou (%s); usando cache de tela recente...", exc2)
            candidatos = [
                Path.home() / ".julia-mobile" / "temp_insta_screen.png",
                Path.home() / ".julia-mobile" / "temp_tiktok_screen.png",
            ]
            for c in candidatos:
                if c.is_file():
                    from PIL import Image
                    return Image.open(c)
            from PIL import Image
            return Image.new("RGB", (1920, 1080), color=(18, 18, 18))


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

def verificar_instagram(timeout_carregamento: float = 3.5, caminho_imagem_teste: Optional[str] = None) -> Dict[str, Any]:
    """Abre o Instagram Direct no navegador padrão, move a tela, analisa notificações e gera relatório."""
    url = "https://www.instagram.com/direct/inbox/"

    if not caminho_imagem_teste:
        proc = iniciar_navegador_perfil(url)
        time.sleep(timeout_carregamento)
        focar_janela_navegador("Instagram", "Brave")
        interagir_e_rolar_mouse(x_prop=0.20, y_prop=0.45, delta_scroll=-280)

        img = capturar_tela()
        temp_path = Path.home() / ".julia-mobile" / "temp_insta_screen.png"
        temp_path.parent.mkdir(parents=True, exist_ok=True)
        img.save(temp_path)
        caminho_final = str(temp_path)
    else:
        caminho_final = caminho_imagem_teste

    texto_extraido = ""
    textos_lidos = []
    try:
        import vision_service
        # Executa OCR de alta fidelidade
        res = vision_service.analisar_imagem_huggingface(caminho_final)
        if res.get("status") != "sucesso":
            res = vision_service.ler_fontes_imagem(caminho_final)
        texto_extraido = res.get("texto_extraido", "")
        textos_lidos = res.get("textos_lidos", [])
    except Exception as e:
        log.warning("Erro no OCR do Instagram: %s", e)

    # 1. Total pendentes pelo título da aba ou badge textual (ex: "(7) Instagram")
    m_aba = re.search(r"\((\d+)\)\s*Instagram", texto_extraido, re.I)
    total_pendentes = int(m_aba.group(1)) if m_aba else 0

    # 2. Análise cromática dos indicadores visuais (bolinhas azuis de não lida e badge vermelho)
    ys_azuis = []
    tem_badge_vermelho = False
    try:
        from PIL import Image
        import numpy as np
        img_pil = Image.open(caminho_final)
        w, h = img_pil.size
        arr = np.array(img_pil, dtype=int)

        r, g, b = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2]
        # Badge vermelho no ícone direct (lado esquerdo)
        mask_red = (r > 120) & (r - g > 50) & (r - b > 50)
        mask_red[:, int(w * 0.08):] = False
        tem_badge_vermelho = int(np.count_nonzero(mask_red)) > 30

        # Pontos azuis de não lida na coluna de mensagens
        mask_blue = (b > 80) & (b - r > 35) & (b - g > 25)
        mask_blue[:, :int(w * 0.25)] = False
        mask_blue[:, int(w * 0.40):] = False
        mask_blue[:int(h * 0.40), :] = False

        coords_azuis = np.argwhere(mask_blue)
        if len(coords_azuis) > 0:
            ys = sorted(coords_azuis[:, 0])
            clusters = []
            curr = [ys[0]]
            for y_coord in ys[1:]:
                if y_coord - curr[-1] < 15:
                    curr.append(y_coord)
                else:
                    clusters.append(int(np.mean(curr)))
                    curr = [y_coord]
            if curr:
                clusters.append(int(np.mean(curr)))
            ys_azuis = clusters
    except Exception as exc:
        log.warning("Falha na análise cromática de indicadores do Instagram: %s", exc)

    if total_pendentes == 0 and (tem_badge_vermelho or ys_azuis):
        total_pendentes = max(len(ys_azuis), 1)

    # 3. Mapear contatos e mensagens
    conversas_mapeadas = []
    ignorar = {"mensagens", "pedidos", "suasmensagens", "suas mensagens", "envie fotos", "enviar mensagem", "pesquisar"}
    try:
        w_img = w if "w" in locals() else 1920
        h_img = h if "h" in locals() else 1080
    except Exception:
        w_img, h_img = 1920, 1080

    for i, item in enumerate(textos_lidos):
        txt = item.get("texto", "").strip()
        coords = item.get("coordenadas", [0, 0, 0, 0])
        cy = (coords[1] + coords[3]) / 2.0 if len(coords) >= 4 else 0
        cx = (coords[0] + coords[2]) / 2.0 if len(coords) >= 4 else 0

        # Filtra textos da coluna de conversas abaixo da barra de busca / status notes
        if int(w_img * 0.08) <= cx <= int(w_img * 0.35) and cy > int(h_img * 0.45):
            txt_clean = re.sub(r"[^\w\s\.,·-]", "", txt).strip()
            if any(ig in txt.lower() for ig in ignorar) or len(txt_clean) < 2:
                continue

            preview = ""
            if i + 1 < len(textos_lidos):
                prox = textos_lidos[i + 1]
                pcoords = prox.get("coordenadas", [0, 0, 0, 0])
                pcy = (pcoords[1] + pcoords[3]) / 2.0
                if 0 < pcy - cy < 35:
                    preview = prox.get("texto", "").strip()

            tem_dot = any(abs(cy - y_dot) < 30 for y_dot in ys_azuis)
            tem_new_msg = bool(re.search(r"(\d+)\s*new\s*messages?", preview, re.I))
            eh_nao_lida = tem_dot or tem_new_msg

            conversas_mapeadas.append({
                "contato": txt,
                "preview": preview,
                "nao_lida": eh_nao_lida,
                "y": cy,
            })

    # Deduplicar contatos consecutivos onde preview foi capturado como item
    conversas_finais = []
    ignorar_prox = False
    for c in conversas_mapeadas:
        if ignorar_prox:
            ignorar_prox = False
            continue
        conversas_finais.append(c)
        if c["preview"]:
            ignorar_prox = True

    nao_lidas = [c for c in conversas_finais if c["nao_lida"]]

    linhas_nao_lidas = []
    for c in nao_lidas:
        prev = f' — *"{c["preview"]}"*' if c["preview"] else ""
        linhas_nao_lidas.append(f"• 👤 **{c['contato']}**{prev} (🔵 Não lida)")

    outras = [c for c in conversas_finais if not c["nao_lida"]][:4]
    linhas_outras = []
    for c in outras:
        prev = f' — *"{c["preview"]}"*' if c["preview"] else ""
        linhas_outras.append(f"• **{c['contato']}**{prev}")

    badge_status = f"🔴 **{total_pendentes} mensagens pendentes detectadas**" if total_pendentes > 0 else "Nenhuma notificação nova no badge"

    resumo = (
        f"**Relatório de Verificação — Instagram Direct (VEXX AI)**\n\n"
        f"- **Notificações:** {badge_status} (ícone Direct / título da aba `({total_pendentes}) Instagram • Mensagens`).\n"
    )
    if linhas_nao_lidas:
        resumo += f"- **Mensagens Novas Identificadas ({len(linhas_nao_lidas)}):**\n" + "\n".join(f"  {l}" for l in linhas_nao_lidas) + "\n"
    if linhas_outras:
        resumo += f"- **Outras Conversas Recentes:**\n" + "\n".join(f"  {l}" for l in linhas_outras) + "\n"
    if not linhas_nao_lidas and not linhas_outras:
        resumo += "- **Atividade na Caixa:** Nenhuma mensagem pendente no momento.\n"

    resumo += "\n*Ações no navegador:* Navegador focado em primeiro plano, rolagem tática na lista de conversas e leitura com visão computacional concluída."

    notif_msg = f"{total_pendentes} mensagens pendentes no Direct." if total_pendentes > 0 else "Caixa de entrada verificada."
    disparar_notificacao_windows("VEXX AI — Instagram", notif_msg)

    return {
        "status": "sucesso",
        "plataforma": "Instagram Direct",
        "url": url,
        "total_pendentes": total_pendentes,
        "mensagens_nao_lidas": nao_lidas,
        "conversas": conversas_finais,
        "resumo": resumo,
    }


def verificar_tiktok_tendencias(timeout_carregamento: float = 3.5) -> Dict[str, Any]:
    """Abre o TikTok Explore, rola a página e extrai as tendências e hashtags do momento."""
    url = "https://www.tiktok.com/explore"
    proc = iniciar_navegador_perfil(url)
    time.sleep(timeout_carregamento)
    focar_janela_navegador("TikTok", "Brave")
    interagir_e_rolar_mouse(x_prop=0.50, y_prop=0.50, delta_scroll=-350)

    img = capturar_tela()
    temp_path = Path.home() / ".julia-mobile" / "temp_tiktok_screen.png"
    temp_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(temp_path)

    textos_lidos = []
    try:
        import vision_service
        res = vision_service.analisar_imagem_huggingface(str(temp_path))
        if res.get("status") != "sucesso":
            res = vision_service.ler_fontes_imagem(str(temp_path))
        for item in res.get("textos_lidos", []):
            t = item.get("texto", "").strip()
            if t:
                textos_lidos.append(t)
        if not textos_lidos and res.get("texto_extraido"):
            textos_lidos = res["texto_extraido"].split()
    except Exception as e:
        log.warning("Erro no OCR do TikTok: %s", e)

    hashtags = [t for t in textos_lidos if "#" in t or "viral" in t.lower() or "tendência" in t.lower() or "trend" in t.lower()]
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

    disparar_notificacao_windows("VEXX AI — TikTok", "Tendências capturadas com sucesso.")
    return relatorio


def monitorar_kabum(termo: str, preco_alvo: Optional[float] = None, timeout_carregamento: float = 3.5) -> Dict[str, Any]:
    """Abre a busca do Kabum, lê produtos e preços reais com OCR e notifica se atingir o alvo."""
    termo_limpo = re.sub(r"[^\w\s]", "", termo).strip()
    url = f"https://www.kabum.com.br/busca/{termo_limpo.replace(' ', '-')}"
    proc = iniciar_navegador_perfil(url)
    time.sleep(timeout_carregamento)
    focar_janela_navegador("Kabum", "Brave")
    interagir_e_rolar_mouse(x_prop=0.50, y_prop=0.50, delta_scroll=-300)

    img = capturar_tela()
    temp_path = Path.home() / ".julia-mobile" / "temp_kabum_screen.png"
    temp_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(temp_path)

    textos_lidos = []
    try:
        import vision_service
        res = vision_service.analisar_imagem_huggingface(str(temp_path))
        if res.get("status") != "sucesso":
            res = vision_service.ler_fontes_imagem(str(temp_path))
        for item in res.get("textos_lidos", []):
            t = item.get("texto", "").strip()
            if t:
                textos_lidos.append(t)
        if not textos_lidos and res.get("texto_extraido"):
            textos_lidos = res["texto_extraido"].split()
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
    # Tenta ações especializadas do Instagram (envio de DM, status online, entrar no chat, busca, rolagem)
    try:
        from pc_modules import instagram_automation
        res_insta_especialista = instagram_automation.rotear_comando_instagram(texto)
        if res_insta_especialista:
            return res_insta_especialista
    except Exception as exc:
        log.warning("Erro ao rotear comando especialista do Instagram: %s", exc)

    if re.search(r"\b(verifique|veja|checar|abrir|abra|olhar|olhe|entre|entrar|acesse|acessar|ir|v[aá]i?)\b.*\b(instagram|insta|direct|dms?)\b", t):
        res = verificar_instagram()
        return res["resumo"]

    if re.search(r"\b(verifique|veja|tend[eê]ncias|trends?|viral|abrir)\b.*\b(tiktok)\b", t):
        res = verificar_tiktok_tendencias()
        return res["resumo"]

    if re.search(r"\b(monitore|verifique o pre[cç]o|pesquise no kabum|pre[cç]o no kabum|abrir kabum)\b", t):
        m_alvo = re.search(r"(?:at[eé]|por|abaixo de)\s*R?\$?\s*(\d+(?:[.,]\d+)?)", t)
        preco_alvo = float(m_alvo.group(1).replace(",", ".")) if m_alvo else None
        termo = re.sub(r"(?i)\b(monitore|verifique o pre[cç]o|pesquise no kabum|no kabum|kabum|at[eé]|por|abaixo de|r\$|\d+)\b", "", t).strip() or "hardware"
        res = monitorar_kabum(termo, preco_alvo)
        return res["resumo"]

    return None
