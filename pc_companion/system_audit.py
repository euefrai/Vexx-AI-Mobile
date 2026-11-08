"""Bounded local inventory for the user's explicit Vexx PC system audit."""
import os
import subprocess
import time
from pathlib import Path

from .files import fingerprint


def _startup_count():
    if os.name!='nt':return None
    import winreg
    count=0
    keys=((winreg.HKEY_CURRENT_USER,r'Software\Microsoft\Windows\CurrentVersion\Run'),
          (winreg.HKEY_LOCAL_MACHINE,r'Software\Microsoft\Windows\CurrentVersion\Run'))
    for hive,path in keys:
        try:
            with winreg.OpenKey(hive,path,0,winreg.KEY_READ) as key:
                count+=min(winreg.QueryInfoKey(key)[1],500)
        except OSError:continue
    return count


def _power_plan():
    if os.name!='nt':return 'Indisponível neste sistema.'
    try:
        result=subprocess.run(['powercfg','/getactivescheme'],capture_output=True,timeout=2,
                              creationflags=subprocess.CREATE_NO_WINDOW)
        return result.stdout.decode(errors='replace').strip()[:300] if result.returncode==0 else 'Não foi possível consultar.'
    except (OSError,subprocess.TimeoutExpired):return 'Não foi possível consultar.'


def _windows_recycle_bin():
    if os.name!='nt':return None
    import ctypes
    class RecycleInfo(ctypes.Structure):
        _fields_=[('cbSize',ctypes.c_long),('i64Size',ctypes.c_longlong),('i64NumItems',ctypes.c_longlong)]
    info=RecycleInfo();info.cbSize=ctypes.sizeof(info)
    try:
        result=ctypes.windll.shell32.SHQueryRecycleBinW(None,ctypes.byref(info))
        return {'count':max(0,info.i64NumItems),'size':max(0,info.i64Size)} if result==0 else None
    except (AttributeError,OSError):return None


def collect(index,files,system,apps):
    system=system or {}
    indexed=index.status()
    large=index.search('',0,'files','largest')['items']
    folders=index.search('',0,'folders','largest')['items']
    trash=files.trash_items(0)
    file_actions=[]
    for item in large:
        if item.get('directory') or (item.get('size') or 0)<256*1024**2 or not files.removable(item['path']):continue
        try:
            path=files.paths.check(item['path'],write=True)
            identity=fingerprint(path)
        except (OSError,ValueError):continue
        file_actions.append({'id':'file:'+str(len(file_actions)),'kind':'file','name':item['name'],'path':item['path'],
                             'size':item['size'],'fingerprint':identity,'description':'Mover para a Lixeira Vexx; restaurável.'})
        if len(file_actions)>=10:break
    processes=[]
    for app in (system.get('processes') or []):
        if app.get('rss',0)<512*1024**2:continue
        processes.append({'id':'process:'+str(len(processes)),'kind':'process','name':app['name'],'size':app['rss'],
                          'processes':app.get('processes',[]),'description':'Encerrar o processo libera RAM; trabalho não salvo pode ser perdido.'})
        if len(processes)>=5:break
    heavy_apps=[{'name':app['name'],'size':app['size'],'publisher':app.get('publisher','')}
                for app in apps if app.get('size',0)>=1024**3][:8]
    sync=[];sync_roots=[]
    providers={'OneDrive':('OneDrive','OneDriveCommercial','OneDriveConsumer'),
               'Google Drive':('GoogleDrive',),'Dropbox':('Dropbox',),'iCloud Drive':('iCloudDrive',)}
    for provider,keys in providers.items():
        for key in keys:
            value=os.environ.get(key)
            if value:sync_roots.append((provider,Path(value)))
    profile=Path.home()
    sync_roots.extend((('Dropbox',profile/'Dropbox'),('Google Drive',profile/'Google Drive'),
                       ('iCloud Drive',profile/'iCloudDrive'),('OneDrive',profile/'OneDrive')))
    for provider,path in sync_roots:
        try:
            if path.is_dir() and not any(str(path.resolve())==x['path'] for x in sync):sync.append({'provider':provider,'path':str(path.resolve())})
        except OSError:continue
    drives=[{'path':d.get('path'),'total':d.get('total'),'free':d.get('free'),'used_percent':d.get('percent')}
            for d in system.get('disks',[])]
    cloud_note=('Pastas de sincronização locais encontradas; o conteúdo remoto/da conta na nuvem não foi acessado.' if sync
                else 'Nenhuma pasta local conhecida do OneDrive, Google Drive, Dropbox ou iCloud foi detectada. Contas e arquivos remotos não foram acessados.')
    return {'created_at':time.time(),'computer':system.get('name',''),'os':system.get('os',''),'cpu_percent':system.get('cpu_percent'),
            'cores':system.get('cpu_cores'),'ram':system.get('ram',{}),'uptime':system.get('uptime',0),'drives':drives,
            'network':system.get('adapters',[]),'ssid':system.get('ssid',''),'power_plan':_power_plan(),
            'startup_count':_startup_count(),'index':{'count':indexed.get('count',0),'skipped':indexed.get('skipped',0),
                'running':indexed.get('running',False),'paused':indexed.get('paused',False),'roots':indexed.get('roots',[])},
            'processes':processes,'files':file_actions,'apps':heavy_apps,
            'folders':[{'path':x['path'],'name':x['name'],'size':x.get('size')} for x in folders[:5] if (x.get('size') or 0)>=1024**3],
            'trash':{'count':trash['count'],'size':trash['size']},'windows_trash':_windows_recycle_bin(),
            'sync':sync,'cloud_note':cloud_note,
            'settings':[{'id':'storage','name':'Armazenamento do Windows','description':'Revise arquivos temporários e uso do disco.','uri':'ms-settings:storage'},
                        {'id':'startup','name':'Aplicativos de inicialização','description':'Revise programas que iniciam com o Windows.','uri':'ms-settings:startupapps'},
                        {'id':'power','name':'Energia e suspensão','description':'Revise as configurações de energia.','uri':'ms-settings:powersleep'},
                        {'id':'network','name':'Rede e Internet','description':'Revise conexões e adaptadores.','uri':'ms-settings:network-status'},
                        {'id':'windows-trash','name':'Lixeira do Windows','description':'Revise e esvazie pelo Explorer.','uri':'shell:RecycleBinFolder'}]}


def report(audit):
    def size(value):
        value=max(0,int(value or 0));unit='B'
        for candidate in ('KB','MB','GB','TB'):
            if value<1024:break
            value/=1024;unit=candidate
        return f'{value:.1f} {unit}'
    lines=['## Diagnóstico local do sistema',f"Computador: {audit['computer'] or 'desconhecido'} · {audit['os'] or 'sistema indisponível'}"]
    if audit.get('ram'):lines.append(f"CPU: {audit.get('cpu_percent','—')}% em {audit.get('cores','—')} núcleos lógicos · RAM: {size(audit['ram'].get('used'))} de {size(audit['ram'].get('total'))} ({audit['ram'].get('percent','—')}%) · Ligado: {int((audit.get('uptime') or 0)//3600)} h")
    lines.append('### Discos')
    lines.extend(f"- {d['path']}: {size(d['free'])} livres de {size(d['total'])} ({d['used_percent']}% usados)" for d in audit['drives'])
    lines.append('### Rede')
    lines.append('- Wi-Fi: '+(audit.get('ssid') or 'SSID não detectado ou Wi-Fi não conectado.'))
    if audit['network']:
        lines.extend(f"- {item['name']}: {', '.join(item['addresses'])} · {item.get('speed_mbps',0)} Mbps." for item in audit['network'])
    else:lines.append('- Nenhum adaptador de rede ativo detectado.')
    lines.append(f"### Arquivos e índice\n- {audit['index']['count']:,} entradas indexadas; {audit['index']['skipped']:,} inacessíveis. Raízes: {', '.join(audit['index']['roots']) or 'nenhuma'}." + (' Indexação ainda em andamento.' if audit['index']['running'] else ''))
    lines.append(f"### Lixeiras\n- Lixeira Vexx: {audit['trash']['count']:,} itens · {size(audit['trash']['size'])} ocupados.")
    if audit.get('windows_trash') is not None:lines.append(f"- Lixeira do Windows: {audit['windows_trash']['count']:,} itens · {size(audit['windows_trash']['size'])} ocupados. A revisão/exclusão acontece pelo próprio Windows.")
    lines.append(f"### Configurações\n- Itens de inicialização registrados: {audit['startup_count'] if audit['startup_count'] is not None else 'indisponível'}.\n- Plano de energia: {audit['power_plan']}")
    lines.append('### Nuvem\n- '+audit['cloud_note'])
    if audit['sync']:lines.extend(f"- Pasta sincronizada local: {x['path']} ({x['provider']})." for x in audit['sync'])
    if audit['processes']:
        lines.append('### Processos com uso alto de RAM')
        lines.extend(f"- {x['name']}: {size(x['size'])} de RAM." for x in audit['processes'])
    if audit['apps']:
        lines.append('### Aplicativos instalados grandes (tamanho estimado)')
        lines.extend(f"- {x['name']}: {size(x['size'])}." for x in audit['apps'])
    if audit['files']:
        lines.append('### Arquivos grandes revisáveis')
        lines.extend(f"- {x['path']}: {size(x['size'])}." for x in audit['files'])
    if audit['folders']:
        lines.append('### Pastas grandes no índice')
        lines.extend(f"- {x['path']}: até {size(x['size'])} indexados." for x in audit['folders'])
    lines.append('### Próximas ações\nOs itens marcados para liberar espaço são movidos à Lixeira Vexx e podem ser restaurados. Encerrar processos pode perder trabalho não salvo. Apps abrem o gerenciador do Windows. Nenhuma mudança acontece até você selecionar e confirmar. A cobertura dos arquivos depende das raízes e do estado do índice.')
    return '\n\n'.join(lines)
