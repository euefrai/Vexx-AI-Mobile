"""Single source of truth for the public Vexx PC Copilot's installed features."""

FEATURES=(
    {'page':'overview','name':'Visão geral','details':'CPU, RAM, discos, rede, tempo ligado e recomendações locais de arquivos, apps e processos.'},
    {'page':'pc','name':'Arquivos','details':'Navegar e pesquisar o índice local; resumir arquivos de texto, documentos suportados e metadados de imagens.'},
    {'page':'cleaner','name':'Limpeza','details':'Filtrar candidatos, revisar apps instalados e restaurar arquivos movidos para a Lixeira Vexx.'},
    {'page':'projects','name':'Projetos','details':'Analisar, iniciar e acompanhar projetos locais compatíveis após revisão.'},
    {'page':'network','name':'Rede','details':'Consultar adaptadores, endereços e Wi-Fi; conectar a perfis Wi-Fi salvos ou abrir as configurações do Windows.'},
    {'page':'logs','name':'Logs','details':'Consultar e filtrar eventos locais da sessão.'},
    {'page':'ai','name':'IA e Copiloto','details':'Configurar provedor/modelo, pedir explicações, navegar por abas e executar ações locais com confirmação.'},
)

OPERATIONS=(
    'Controle remoto: visualização ou mouse/teclado por uma hora; autorização permanente opcional, por conta vinculada, revogável e iniciada ocultamente no login do Windows.',
    'Atualização: verificar e instalar a versão pública após confirmação.',
    'Comandos Windows: o texto exato é exibido e precisa ser confirmado antes da execução.',
    'Privacidade: inventário e análise de arquivos são locais; trechos de arquivos só vão ao provedor de IA após consentimento.',
    'Limites: sem acesso a contas ou arquivos remotos da nuvem; conexões novas de Wi-Fi pedem que a senha seja digitada nas configurações do Windows.',
)


def copilot_guide():
    features='\n'.join(f"- **{item['name']}:** {item['details']}" for item in FEATURES)
    operations='\n'.join('- '+item for item in OPERATIONS)
    return '## Capacidades instaladas no Vexx PC\n'+features+'\n'+operations


def ai_capability_context():
    features='; '.join(f"{item['name']}: {item['details']}" for item in FEATURES)
    return features+' '+ ' '.join(OPERATIONS)
