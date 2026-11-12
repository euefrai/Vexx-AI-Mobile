# -*- coding: utf-8 -*-
"""
VEXX AI - Gerenciador de Provedores Personalizados & Conexões Externas
Permite cadastrar endpoints customizados (Ollama, LM Studio, vLLM, TextGen, LocalAI,
VPS remotos, túneis SSH, Cloudflare, Ngrok, Pinggy, etc.), testar latência ao vivo,
descobrir modelos e gerar comandos de túnel sob medida.
"""

import os
import sys
import json
import time
import urllib.request
import urllib.error
import urllib.parse
from pathlib import Path
from typing import Dict, List, Any, Optional

# Diretório de persistência seguro
def _obter_caminho_storage() -> Path:
    candidatos = [
        Path(os.environ.get("VEXX_DATA_DIR", "")) if os.environ.get("VEXX_DATA_DIR") else None,
        Path.home() / ".julia-mobile",
        Path(__file__).resolve().parent,
    ]
    for c in candidatos:
        if c:
            try:
                c.mkdir(parents=True, exist_ok=True)
                return c / "custom_providers.json"
            except Exception:
                continue
    temp_dir = Path(os.environ.get("TEMP", str(Path.home())))
    return temp_dir / "custom_providers.json"

CUSTOM_PROVIDERS_FILE = _obter_caminho_storage()

def carregar_custom_providers() -> Dict[str, Dict[str, Any]]:
    """Carrega todos os provedores externos cadastrados."""
    if not CUSTOM_PROVIDERS_FILE.exists():
        return {}
    try:
        with open(CUSTOM_PROVIDERS_FILE, "r", encoding="utf-8") as f:
            dados = json.load(f)
            if isinstance(dados, dict):
                return dados
    except Exception:
        pass
    return {}

def salvar_custom_provider(provider_data: Dict[str, Any]) -> Dict[str, Any]:
    """Salva ou atualiza um provedor externo customizado."""
    prov_id = str(provider_data.get("id") or "").strip().lower()
    if not prov_id:
        nome_limpo = "".join(c for c in str(provider_data.get("label", "custom")) if c.isalnum() or c in "_-").lower()
        prov_id = f"custom_{nome_limpo or 'srv'}_{int(time.time())}"
    elif not prov_id.startswith("custom_"):
        prov_id = f"custom_{prov_id}"

    base_url = str(provider_data.get("base") or "").strip().rstrip("/")
    if not base_url:
        raise ValueError("A URL Base do provedor é obrigatória (ex: http://localhost:11434/v1).")

    label = str(provider_data.get("label") or prov_id).strip()
    api_type = str(provider_data.get("api") or "openai").strip().lower()
    api_key = str(provider_data.get("api_key") or "").strip()
    device_type = str(provider_data.get("device_type") or "custom").strip()

    modelos = provider_data.get("modelos") or []
    if isinstance(modelos, str):
        modelos = [m.strip() for m in modelos.split(",") if m.strip()]
    elif not isinstance(modelos, list):
        modelos = []

    if not modelos:
        # Se não informou modelos, coloca um modelo padrão genérico
        modelos = [f"{prov_id}-default"]

    registro = {
        "id": prov_id,
        "label": label,
        "base": base_url,
        "api": api_type,
        "key_env": None,
        "api_key": api_key,
        "hosts": ("*",),
        "modelos": modelos,
        "device_type": device_type,
        "created_at": time.time(),
        "configured": True,
        "source": "custom_external"
    }

    todos = carregar_custom_providers()
    todos[prov_id] = registro

    try:
        with open(CUSTOM_PROVIDERS_FILE, "w", encoding="utf-8") as f:
            json.dump(todos, f, ensure_ascii=False, indent=2)
    except Exception as exc:
        raise RuntimeError(f"Falha ao persistir provedor personalizado: {exc}")

    return registro

def remover_custom_provider(provider_id: str) -> bool:
    """Remove um provedor externo personalizado pelo ID."""
    prov_id = str(provider_id).strip().lower()
    todos = carregar_custom_providers()
    if prov_id in todos:
        del todos[prov_id]
        try:
            with open(CUSTOM_PROVIDERS_FILE, "w", encoding="utf-8") as f:
                json.dump(todos, f, ensure_ascii=False, indent=2)
            return True
        except Exception:
            return False
    return False

def obter_custom_provider(provider_id: str) -> Optional[Dict[str, Any]]:
    """Recupera a definição de um provedor customizado."""
    todos = carregar_custom_providers()
    return todos.get(provider_id.strip().lower())

def testar_conexao_externa(base_url: str, api_key: str = "", model_id: str = "") -> Dict[str, Any]:
    """
    Testa a conectividade com qualquer endpoint HTTP/REST de IA externo (Ollama, vLLM, LM Studio, etc.),
    mede a latência real em ms e tenta descobrir os modelos disponíveis em /models ou /v1/models.
    """
    url_limpa = str(base_url or "").strip().rstrip("/")
    if not url_limpa:
        return {"status": "erro", "mensagem": "URL Base não informada."}
    parte = urllib.parse.urlsplit(url_limpa)
    if parte.scheme not in ("http", "https") or not parte.hostname:
        return {"status": "erro", "mensagem": "URL Base inválida: use http:// ou https:// com host válido."}

    # Prepara cabeçalhos
    headers = {"User-Agent": "VexxAI-Probe/2.0"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    t0 = time.perf_counter()
    modelos_encontrados = []
    detalhes_servidor = "Endpoint acessível"
    base_sugerida = url_limpa

    # 1. Tenta listar modelos via /models ou /v1/models ou /api/tags
    alvos_models = [url_limpa + "/models"]
    if not url_limpa.endswith("/v1"):
        alvos_models.append(url_limpa + "/v1/models")
    alvos_models.append(url_limpa + "/api/tags")  # Endpoint nativo Ollama

    conectou = False
    erro_ultimo = ""

    for u in alvos_models:
        try:
            req = urllib.request.Request(u, headers=headers)
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                conectou = True
                latencia_ms = round((time.perf_counter() - t0) * 1000)
                raw = resp.read().decode("utf-8", errors="replace")
                dados = json.loads(raw)

                # Formato OpenAI (/models -> {"data": [{"id": "..."}]})
                if isinstance(dados, dict) and "data" in dados and isinstance(dados["data"], list):
                    for item in dados["data"]:
                        if isinstance(item, dict) and item.get("id"):
                            modelos_encontrados.append(str(item["id"]))
                    detalhes_servidor = f"API compatível com OpenAI (código {resp.status})"
                    if u.endswith("/v1/models") and not url_limpa.endswith("/v1"):
                        base_sugerida = url_limpa + "/v1"
                    break

                # Formato Ollama (/api/tags -> {"models": [{"name": "..."}]})
                elif isinstance(dados, dict) and "models" in dados and isinstance(dados["models"], list):
                    for item in dados["models"]:
                        if isinstance(item, dict) and item.get("name"):
                            modelos_encontrados.append(str(item["name"]))
                    detalhes_servidor = f"Servidor Ollama Detectado (código {resp.status})"
                    if not url_limpa.endswith("/v1"):
                        base_sugerida = url_limpa + "/v1"
                    break

        except urllib.error.HTTPError as he:
            conectou = True
            latencia_ms = round((time.perf_counter() - t0) * 1000)
            if he.code in (401, 403):
                return {
                    "status": "erro_auth",
                    "latencia_ms": latencia_ms,
                    "mensagem": f"O servidor respondeu com HTTP {he.code} (Autenticação recusada. Verifique sua chave de API)."
                }
            erro_ultimo = f"HTTP {he.code}"
        except Exception as exc:
            erro_ultimo = str(exc)

    if not conectou:
        # Se os endpoints de modelos falharam, tenta um teste direto na raiz da URL base
        try:
            t0 = time.perf_counter()
            req = urllib.request.Request(url_limpa, headers=headers)
            with urllib.request.urlopen(req, timeout=4.0) as resp:
                latencia_ms = round((time.perf_counter() - t0) * 1000)
                return {
                    "status": "sucesso",
                    "latencia_ms": latencia_ms,
                    "mensagem": f"Conexão estabelecida com sucesso ({resp.status}). Nenhum catálogo público retornado.",
                    "modelos": modelos_encontrados,
                    "base_sugerida": base_sugerida,
                }
        except Exception as exc:
            return {
                "status": "erro",
                "mensagem": f"Não foi possível conectar a {url_limpa}: {exc or erro_ultimo}"
            }

    latencia_ms = round((time.perf_counter() - t0) * 1000)
    return {
        "status": "sucesso",
        "latencia_ms": latencia_ms,
        "mensagem": f"{detalhes_servidor} · Latência: {latencia_ms} ms",
        "modelos": modelos_encontrados[:50],
        "base_sugerida": base_sugerida,
    }

def gerar_instrucoes_tunel(tipo_tunel: str = "ssh", porta_local: int = 8008, host_ssh: str = "usuario@seu-pc-ou-vps") -> Dict[str, Any]:
    """
    Gera comandos prontos para cópia e instruções passo a passo para conectar
    qualquer dispositivo externo ao Vexx AI.
    """
    porta = int(porta_local or 8008)
    user_host = host_ssh.strip() or "usuario@ip-do-outro-computador"

    if tipo_tunel == "ssh_reverse":
        return {
            "titulo": "Túnel SSH Reverso (Outro PC/Servidor ➔ Vexx AI)",
            "descricao": f"Use este comando no OUTRO dispositivo para encaminhar a porta local {porta}. Depois adicione http://127.0.0.1:{porta}/v1 na aba Personalizado.",
            "comando": f"ssh -N -R {porta}:localhost:{porta} {user_host}",
            "dica": f"Se o outro PC estiver rodando Ollama (porta 11434), use: ssh -N -R {porta}:localhost:11434 {user_host}"
        }

    elif tipo_tunel == "cloudflare":
        return {
            "titulo": "Cloudflare Tunnel (Seguro, HTTPS Grátis, Sem Abrir Portas)",
            "descricao": "Cria um túnel HTTPS instantâneo no outro dispositivo. Cole a URL gerada (ex: https://xxx.trycloudflare.com/v1) na aba Personalizado.",
            "comando": f"cloudflared tunnel --url http://localhost:{porta}",
            "dica": "Cole a URL gerada pelo cloudflared adicionando '/v1' no final na aba Personalizado / Remoto."
        }

    elif tipo_tunel == "ngrok":
        return {
            "titulo": "Ngrok (Túnel Rápido de 1 Clique)",
            "descricao": "Exponha temporariamente seu servidor local e cole a URL HTTPS gerada (+ /v1) na aba Personalizado.",
            "comando": f"ngrok http {porta}",
            "dica": "Copie o endereço gerado pelo ngrok (ex.: https://seunome.ngrok-free.app/v1) e cadastre no Provedor Personalizado."
        }

    elif tipo_tunel == "pinggy":
        return {
            "titulo": "Pinggy (Zero Instalação via SSH)",
            "descricao": "Cria uma URL pública imediata usando apenas SSH nativo (Windows, Linux ou Mac). Cole a URL gerada (+ /v1) na aba Personalizado.",
            "comando": f"ssh -p 443 -R0:localhost:{porta} a.pinggy.io",
            "dica": "O terminal mostrará um link HTTPS com suporte a SSE/streaming pronto para uso imediato."
        }

    elif tipo_tunel == "outro_pc_agente":
        relay_url = os.environ.get("JULIA_RELAY_URL", "https://vexx-ai.space")
        cmd = (
            f"# Windows:\nset JULIA_RELAY_URL={relay_url}\nset JULIA_AGENT_TOKEN=<SEU_TOKEN_DO_AGENTE>\niniciar_vexx_pc.bat\n\n"
            f"# Linux / macOS:\nexport JULIA_RELAY_URL={relay_url}\nexport JULIA_AGENT_TOKEN=<SEU_TOKEN_DO_AGENTE>\npython3 pc_agent.py"
        )
        return {
            "titulo": "Conectar Outro Computador como Agente Completo",
            "descricao": "Execute em qualquer computador com o seu token de agente para vinculá-lo diretamente ao painel no vexx-ai.space.",
            "comando": cmd,
            "dica": "Substitua <SEU_TOKEN_DO_AGENTE> pelo token configurado no .env do seu servidor/PC."
        }

    return {
        "titulo": "Configuração Genérica",
        "descricao": f"Acesse a porta {porta} na sua rede local ou via IP público.",
        "comando": f"curl http://localhost:{porta}/v1/models"
    }
