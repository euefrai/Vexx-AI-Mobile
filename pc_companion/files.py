"""Bounded local browsing and reversible, reviewed file removal. No recursive delete."""
import os
import re
import secrets
import sqlite3
import stat
import threading
import time
import uuid
import zipfile
import xml.etree.ElementTree as ET
from contextlib import contextmanager
from pathlib import Path

BLOCKED = {'windows','program files','program files (x86)','programdata','appdata',
           '$recycle.bin','system volume information','recovery','boot','.git','.venv','.vexx-venv','venv'}
PROTECTED_NAMES={'pagefile.sys','hiberfil.sys','swapfile.sys','bootmgr','bootnxt','ntldr','boot.ini'}
TRASH = '.vexx-trash'
CATEGORIES = {
    'installers':{'.exe','.msi','.msix','.msixbundle','.appx','.appxbundle','.apk','.aab'},
    'images':{'.jpg','.jpeg','.png','.gif','.webp','.bmp','.svg','.heic','.tiff','.avif'},
    'videos':{'.mp4','.mkv','.mov','.avi','.webm','.m4v','.wmv','.mpeg'},
    'audio':{'.mp3','.wav','.flac','.m4a','.ogg','.aac'},
    'archives':{'.zip','.7z','.rar','.tar','.gz','.bz2','.xz','.iso'},
    'temporary':{'.tmp','.temp','.bak','.old','.log'},
}
TEXT_TYPES={'.txt','.md','.py','.js','.mjs','.cjs','.ts','.tsx','.jsx','.html','.css','.json','.yaml','.yml','.toml','.ini','.cfg','.csv','.log','.sql','.sh','.ps1','.bat','.cmd','.xml','.rst'}
DOCUMENT_TYPES={'.pdf','.docx','.xlsx','.pptx'}


def _document_text(path,size):
    ext=path.suffix.casefold()
    if ext=='.pdf':
        if size>25_000_000:return 'PDF maior que 25 MB; conteúdo não lido para preservar desempenho.'
        try:
            from pypdf import PdfReader
            reader=PdfReader(str(path),strict=False)
            if reader.is_encrypted:return 'PDF protegido por senha; conteúdo não lido.'
            if len(reader.pages)>500:return f'PDF com {len(reader.pages)} páginas; o conteúdo excede o limite de análise.'
            pages=[]
            for page in reader.pages[:10]:
                text=page.extract_text() or ''
                if text:pages.append(text[:6000])
            return f'PDF com {len(reader.pages)} páginas. Trechos das primeiras 10 páginas:\n'+'\n'.join(pages)[:20000]
        except Exception:return 'PDF detectado, mas não foi possível extrair texto. Pode conter apenas imagens, estar danificado ou usar codificação não suportada.'
    try:
        with zipfile.ZipFile(path) as archive:
            infos=archive.infolist()
            if len(infos)>2000 or sum(item.file_size for item in infos)>25_000_000:return 'Documento compactado excede os limites de análise.'
            if ext=='.docx':
                info=archive.getinfo('word/document.xml')
                if info.file_size>8_000_000:return 'Documento Word contém uma parte grande demais para leitura local.'
                root=ET.fromstring(archive.read(info));text=' '.join(node.text or '' for node in root.iter() if node.tag.rsplit('}',1)[-1]=='t')
                return 'Documento Word: '+text[:20000]
            if ext=='.pptx':
                slides=sorted(x for x in archive.namelist() if re.fullmatch(r'ppt/slides/slide\d+\.xml',x))[:20]
                result=[]
                for name in slides:
                    root=ET.fromstring(archive.read(name));text=' '.join(n.text or '' for n in root.iter() if n.tag.rsplit('}',1)[-1]=='t')
                    if text:result.append(name.rsplit('/',1)[-1]+': '+text[:2000])
                return f'Apresentação PowerPoint com {len(infos)} partes; texto de até 20 slides:\n'+'\n'.join(result)[:20000]
            if ext=='.xlsx':
                shared=[]
                if 'xl/sharedStrings.xml' in archive.namelist():
                    root=ET.fromstring(archive.read('xl/sharedStrings.xml'));shared=[''.join(n.text or '' for n in item.iter() if n.tag.rsplit('}',1)[-1]=='t') for item in list(root)[:3000]]
                sheets=sorted(x for x in archive.namelist() if re.fullmatch(r'xl/worksheets/sheet\d+\.xml',x))[:10];result=[]
                for name in sheets:
                    root=ET.fromstring(archive.read(name));rows=[]
                    for row in list(root):
                        if row.tag.rsplit('}',1)[-1]!='sheetData':continue
                        for record in list(row)[:30]:
                            if record.tag.rsplit('}',1)[-1]!='row':continue
                            values=[]
                            for cell in list(record)[:20]:
                                if cell.tag.rsplit('}',1)[-1]!='c':continue
                                raw=next((n.text or '' for n in list(cell) if n.tag.rsplit('}',1)[-1]=='v'),'')
                                if cell.attrib.get('t')=='s' and raw.isdigit() and int(raw)<len(shared):raw=shared[int(raw)]
                                if raw:values.append(cell.attrib.get('r','')+'='+raw[:160])
                            if values:rows.append(' | '.join(values))
                            if len(rows)>=20:break
                    result.extend([name+':',*rows])
                return 'Planilha Excel; amostra limitada de células (fórmulas não são executadas):\n'+'\n'.join(result)[:20000]
    except Exception:return 'Documento Office detectado, mas não foi possível ler sua estrutura interna com segurança.'
    return 'Formato de documento não reconhecido.'


def _image_info(path):
    try:
        from PIL import Image
        with Image.open(path) as image:return f'Imagem {image.format or "desconhecida"} · {image.width} × {image.height} pixels.'
    except Exception:return 'Imagem detectada; dimensões não disponíveis.'


def referenced_local_paths(files,text,explicit=()):
    values=list(explicit)
    for match in re.finditer(r'(?i)(?:"((?:[a-z]:[\\/]|\\\\)[^"\r\n]+)"|((?:[a-z]:[\\/]|\\\\)[^\r\n<>|?*]+))',text):
        value=match.group(1) or match.group(2)
        candidates=[value.strip().rstrip('.,;:!?)]}')]
        if not match.group(1):
            parts=candidates[0].split()
            candidates += [' '.join(parts[:end]).rstrip('.,;:!?)]}') for end in range(len(parts)-1,0,-1)]
        for candidate in candidates:
            try:
                checked=files.paths.check(candidate)
                if checked.is_file() or checked.is_dir():
                    values.append(str(checked));break
            except (OSError,ValueError):continue
    return list(dict.fromkeys(values))[:10]


def _file_description(path,size):
    name=path.name.casefold();ext=path.suffix.casefold()
    if name=='pagefile.sys':return 'Arquivo de paginação do Windows, usado para memória virtual. O Windows gerencia esse arquivo; não o exclua manualmente.'
    if name=='hiberfil.sys':return 'Arquivo de hibernação do Windows, controlado pelo sistema. Não o exclua manualmente.'
    if name=='swapfile.sys':return 'Arquivo de memória virtual do Windows, controlado pelo sistema. Não o exclua manualmente.'
    types={'.py':'código Python','.js':'código JavaScript','.ts':'código TypeScript','.html':'página HTML','.css':'folha de estilos CSS',
           '.json':'dados JSON','.csv':'tabela CSV','.md':'documentação Markdown','.pdf':'documento PDF','.docx':'documento Word',
           '.xlsx':'planilha Excel','.pptx':'apresentação PowerPoint','.exe':'programa executável','.msi':'instalador do Windows',
           '.apk':'aplicativo Android','.dll':'biblioteca do Windows','.sys':'arquivo de sistema ou driver','.db':'banco de dados',
           '.sqlite':'banco de dados SQLite','.zip':'arquivo compactado','.mp4':'vídeo','.mkv':'vídeo','.jpg':'imagem','.jpeg':'imagem','.png':'imagem'}
    return types.get(ext,'arquivo '+(ext or 'sem extensão'))


def _text_outline(path,content):
    lines=content.splitlines();result=[f'{len(lines)} linhas.']
    if path.suffix.casefold() in {'.py','.js','.mjs','.ts','.tsx','.jsx'}:
        symbols=[line.strip() for line in lines if re.match(r'\s*(?:async\s+)?(?:def|class|function)\s+\w+|\s*(?:export\s+)?(?:const|let)\s+\w+\s*=\s*(?:async\s*)?\(',line)][:12]
        if symbols:result.append('Pontos de entrada e símbolos: '+', '.join(symbols))
        imports=[line.strip() for line in lines if re.match(r'\s*(?:import|from|require\s*\()',line)][:8]
        if imports:result.append('Dependências mencionadas: '+', '.join(imports))
    headings=[line.strip().lstrip('#').strip() for line in lines if line.lstrip().startswith('#')][:8]
    if headings:result.append('Títulos: '+', '.join(headings))
    if path.suffix.casefold()=='.json':
        try:
            import json
            value=json.loads(content)
            if isinstance(value,dict):result.append('Chaves principais: '+', '.join(str(key)[:80] for key in list(value)[:20]))
            elif isinstance(value,list):result.append('Lista com '+str(len(value))+' itens.')
        except ValueError:result.append('O conteúdo não pôde ser interpretado como JSON válido.')
    if not headings and not any(s in ' '.join(result) for s in ('símbolos','Chaves','Lista com')):
        excerpt=' '.join(line.strip() for line in lines[:4] if line.strip())[:500]
        if excerpt:result.append('Início: '+excerpt)
    return ' '.join(result)


def analyze_local_paths(files,values,include_content=False):
    found=[];metadata=[];total=0;truncated=False
    values=list(dict.fromkeys(values))
    for value in values:
        path=files.paths.check(value)
        candidates=[]
        if path.is_file():candidates=[path]
        elif path.is_dir():
            start=time.monotonic()
            for folder,dirs,names in os.walk(path,followlinks=False):
                dirs[:]=[d for d in dirs if d.casefold() not in BLOCKED and d!=TRASH and not (Path(folder)/d).is_symlink()]
                for name in names:
                    item=Path(folder)/name
                    if not item.is_symlink():candidates.append(item)
                    if len(candidates)>=500 or time.monotonic()-start>2:truncated=True;break
                if truncated or len(candidates)>=500:break
        else:raise ValueError('Selecione um arquivo ou pasta.')
        if len(candidates)>40:truncated=True
        for item in candidates[:40]:
            checked=files.paths.check(str(item));size=checked.stat().st_size
            ext=checked.suffix.casefold()
            content=''
            if ext in TEXT_TYPES:
                if size>1_000_000 or total+size>10_000_000:truncated=True
                elif len(found)<12:
                    total+=size
                    content=checked.read_text('utf-8',errors='replace')[:12000]
            elif ext in DOCUMENT_TYPES and size<=25_000_000 and len(found)<12:
                total+=size
                content=_document_text(checked,size)
            elif ext in CATEGORIES['images']:
                content=_image_info(checked)
            if len(metadata)<40:metadata.append((str(checked),size,ext.lstrip('.') or 'sem extensão',content))
            if content and len(found)<12:found.append((checked,content))
    if not metadata:return 'Os caminhos foram verificados. Não encontrei arquivos acessíveis para resumo.'
    summary=[f"Análise local de {len(values)} caminho(s). Inventário de até {len(metadata)} arquivos; conteúdo de {len(found)} arquivos lido localmente ({total} bytes). Arquivos binários são descritos por tipo e metadados, sem executar seu conteúdo."]
    if truncated:summary.append('A leitura foi limitada por segurança e desempenho.')
    summary.extend('\n- '+name+' · '+str(size)+' bytes · '+kind+' · '+_file_description(Path(name),size) for name,size,kind,_ in metadata)
    for path,content in found:
        summary.extend(['\n### '+str(path),_text_outline(path,content)])
        if include_content:summary.extend(['Conteúdo fornecido à IA a pedido do usuário:','```\n'+content+'\n```'])
    return '\n'.join(summary)[:50000]


class Paths:
    def __init__(self, roots, protected=()):
        self.roots = [Path(p).resolve() for p in roots]
        self.protected = [Path(p).resolve() for p in protected]

    def check(self, value, *, write=False, trash=False):
        if not isinstance(value,str) or not value or len(value)>2000 or '\x00' in value:
            raise ValueError('Caminho inválido.')
        if os.name=='nt' and (value.startswith('\\\\') or ':' in value[2:]):
            raise ValueError('Somente caminhos locais comuns são permitidos.')
        path = Path(os.path.abspath(value))
        for part in (path,*path.parents):
            info = part.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info,'st_file_attributes',0)&0x400:
                raise ValueError('Atalhos, junctions e arquivos virtuais não são alterados.')
        path = path.resolve(strict=True)
        if not any(path.is_relative_to(root) for root in self.roots):
            raise ValueError('Escolha um caminho nas raízes locais disponíveis.')
        if TRASH in {p.casefold() for p in path.parts} and not trash:
            raise ValueError('Use a aba Lixeira para acessar os itens removidos.')
        if write:
            if path.name.casefold() in PROTECTED_NAMES:
                raise ValueError('Arquivos controlados pelo Windows não podem ser removidos.')
            if any(path==p or path.is_relative_to(p) for p in self.protected):
                raise ValueError('Os arquivos do Vexx PC não podem ser removidos aqui.')
            if any(p.casefold() in BLOCKED for p in path.parts) or path==Path(path.anchor) or (path.is_file() and path.parent==Path(path.anchor)):
                raise ValueError('Arquivos do sistema, aplicativos e ambientes são protegidos.')
        return path


def fingerprint(path):
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise ValueError('Selecione arquivos comuns, sem links. Pastas não entram na exclusão em lote.')
    return (info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns)


class Files:
    def __init__(self, directory, index):
        self.directory,self.index = Path(directory).resolve(),index
        self.paths = Paths(index.roots, (directory,Path(__file__).resolve().parents[1]))
        self.path = self.directory/'trash.sqlite3'
        self.guard = threading.RLock()
        self.previews = {}
        with self.db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS trash (id TEXT PRIMARY KEY,original TEXT,stored TEXT,size INTEGER,modified REAL,created REAL)')

    @contextmanager
    def db(self):
        db=sqlite3.connect(self.path,timeout=2)
        try:
            with db:yield db
        finally:db.close()

    def stored_path(self, stored, original, identity):
        path=Path(stored)
        if path.name!=identity or path.parent not in (self.directory/TRASH,Path(original).parent/TRASH):
            raise ValueError('Registro da Lixeira inválido.')
        if path.parent==self.directory/TRASH:
            return Paths([self.directory]).check(str(path),trash=True)
        return self.paths.check(str(path),write=True,trash=True)

    def browse(self, path='', offset=0, sort='name'):
        if not path:
            return {'path':'','parent':'','items':[{'path':str(p),'name':str(p),'directory':True,'size':None,'modified':None} for p in self.paths.roots], 'more':False}
        folder = self.paths.check(path)
        if not folder.is_dir():raise ValueError('Escolha uma pasta.')
        offset = max(0,min(int(offset),5000));rows=[];started=time.monotonic();truncated=False
        with os.scandir(folder) as entries:
            for entry in entries:
                if len(rows)>=5000 or time.monotonic()-started>1:
                    truncated=True;break
                if entry.name==TRASH or entry.is_symlink() or getattr(os.path,'isjunction',lambda _:False)(entry.path):continue
                try:
                    info=entry.stat(follow_symlinks=False)
                    if getattr(info,'st_file_attributes',0)&0x400:continue
                    rows.append({'path':entry.path,'name':entry.name,'directory':entry.is_dir(follow_symlinks=False),
                                 'size':None if entry.is_dir(follow_symlinks=False) else info.st_size,'modified':info.st_mtime})
                except OSError:continue
        rows.sort(key=lambda r:(not r['directory'], -(r['size'] or 0) if sort=='largest' else
                               -(r['modified'] or 0) if sort=='newest' else (r['modified'] or 0) if sort=='oldest' else r['name'].casefold(),r['name'].casefold()))
        page=rows[offset:offset+60]
        with self.index.db() as db:
            for item in page:
                if item['directory']:
                    row=db.execute('SELECT size FROM files WHERE path=?',(item['path'],)).fetchone()
                    item['size']=row[0] if row else None
        parent=str(folder.parent) if any(folder.parent.is_relative_to(r) for r in self.paths.roots) else ''
        return {'path':str(folder),'parent':parent,'items':page,'more':len(rows)>offset+60,'partial':truncated}

    def trash_items(self, offset=0):
        offset=max(0,min(int(offset),100000))
        with self.db() as db:
            rows=db.execute('SELECT id,original,size,modified,created FROM trash ORDER BY created DESC LIMIT 61 OFFSET ?',(offset,)).fetchall()
            count,size=db.execute('SELECT COUNT(*),COALESCE(SUM(size),0) FROM trash').fetchone()
        return {'items':[dict(zip(('id','path','size','modified','removed'),row)) for row in rows[:60]], 'count':count,'size':size,'more':len(rows)>60}

    def removable(self,value):
        path=Path(value)
        return not (path.name.casefold() in PROTECTED_NAMES or path==Path(path.anchor) or path.parent==Path(path.anchor)
                    or any(p.casefold() in BLOCKED or p.casefold()==TRASH for p in path.parts)
                    or any(path==p or path.is_relative_to(p) for p in self.paths.protected))

    def prepare(self, mode, values):
        if mode not in ('trash','restore','purge') or not isinstance(values,list) or not 1<=len(values)<=100 or not all(isinstance(v,str) for v in values):
            raise ValueError('Selecione de 1 a 100 arquivos.')
        with self.guard:
            records=[]
            for value in dict.fromkeys(values):
                if mode=='trash':
                    path=self.paths.check(value,write=True)
                    records.append({'path':str(path),'fingerprint':fingerprint(path),'size':path.stat().st_size})
                else:
                    with self.db() as db:
                        row=db.execute('SELECT id,original,stored,size FROM trash WHERE id=?',(value,)).fetchone()
                    if not row:raise ValueError('Um item não está mais na Lixeira. Atualize a lista.')
                    path=self.stored_path(row[2],row[1],row[0])
                    records.append({'id':row[0],'path':str(path),'original':row[1],'size':row[3],'fingerprint':fingerprint(path)})
            now=time.monotonic();self.previews={k:v for k,v in self.previews.items() if v['until']>now}
            if len(self.previews)>=8:raise ValueError('Feche uma revisão anterior ou aguarde alguns minutos.')
            token=secrets.token_urlsafe(24)
            self.previews[token]={'mode':mode,'records':records,'until':now+300}
            return {'token':token,'mode':mode,'count':len(records),'size':sum(r['size'] for r in records),
                    'items':[{'path':r.get('original',r['path']),'size':r['size']} for r in records]}

    def execute(self, token, confirmation=''):
        with self.guard:
            job=self.previews.get(token)
            if not job or job['until']<time.monotonic():raise ValueError('A revisão expirou. Selecione e revise novamente.')
            if job['mode']=='purge' and confirmation!='EXCLUIR':raise ValueError('Digite EXCLUIR para confirmar a exclusão definitiva.')
            self.previews.pop(token)
            # Validate the entire selection again before moving or deleting anything.
            for item in job['records']:
                path=self.paths.check(item['path'],write=True) if job['mode']=='trash' else self.stored_path(item['path'],item['original'],item['id'])
                if fingerprint(path)!=item['fingerprint']:raise ValueError('Um arquivo mudou desde a revisão. Nenhum item foi processado; revise novamente.')
            done=[];failed=[]
            with self.db() as db:
                for item in job['records']:
                    path=Path(item['path'])
                    try:
                        if job['mode']=='trash':
                            bin_path=(self.directory if self.directory.stat().st_dev==path.stat().st_dev else path.parent)/TRASH
                            if bin_path.exists() and (bin_path.is_symlink() or getattr(os.path,'isjunction',lambda _:False)(bin_path)):
                                raise ValueError('A pasta da Lixeira foi substituída.')
                            bin_path.mkdir(mode=0o700,exist_ok=True)
                            if os.name=='nt':
                                import ctypes
                                attrs=ctypes.windll.kernel32.GetFileAttributesW(str(bin_path))
                                if attrs!=-1:ctypes.windll.kernel32.SetFileAttributesW(str(bin_path),attrs|2)
                            identity=uuid.uuid4().hex;target=bin_path/identity
                            # Persist the recovery record before the atomic same-volume rename.
                            db.execute('INSERT INTO trash VALUES (?,?,?,?,?,?)',(identity,str(path),str(target),item['size'],path.stat().st_mtime,time.time()));db.commit()
                            try:os.rename(path,target)
                            except OSError:
                                db.execute('DELETE FROM trash WHERE id=?',(identity,));db.commit();raise
                        elif job['mode']=='restore':
                            destination=Path(item['original'])
                            parent=destination.parent
                            while not parent.exists():parent=parent.parent
                            self.paths.check(str(parent),write=True)
                            destination.parent.mkdir(parents=True,exist_ok=True)
                            self.paths.check(str(destination.parent),write=True)
                            if destination.exists() or destination.is_symlink():raise ValueError('Já existe outro arquivo no caminho original.')
                            if os.name=='nt':os.rename(path,destination)
                            else:os.link(path,destination);path.unlink()
                            db.execute('DELETE FROM trash WHERE id=?',(item['id'],));db.commit()
                        else:
                            # Only an individually reviewed file in our own bin is unlinked.
                            path.unlink();db.execute('DELETE FROM trash WHERE id=?',(item['id'],));db.commit()
                        done.append(item.get('original',item['path']))
                    except (OSError,ValueError):
                        failed.append({'path':item.get('original',item['path']),'error':'Não foi possível processar. Confira permissões, arquivo em uso ou conflito no destino.'})
            if done and job['mode'] in ('trash','restore'):
                try:
                    with self.index.write_lock,self.index.db() as db:
                        if job['mode']=='trash':
                            self.index.removed.update(done)
                            db.executemany('DELETE FROM files WHERE path=?',((p,) for p in done))
                        else:
                            self.index.removed.difference_update(done)
                            for value in done:
                                p=Path(value);info=p.stat()
                                db.execute('''INSERT INTO files(path,name,size,directory,modified,generation,parent,extension)
                                    VALUES (?,?,?,0,?,?,?,?) ON CONFLICT(path) DO UPDATE SET name=excluded.name,size=excluded.size,
                                    modified=excluded.modified,generation=excluded.generation,parent=excluded.parent,extension=excluded.extension''',
                                    (str(p),p.name,info.st_size,info.st_mtime,self.index.generation,str(p.parent),p.suffix.casefold()))
                        db.commit();self.index.count=db.execute('SELECT COUNT(*) FROM files').fetchone()[0]
                except (OSError,sqlite3.Error):
                    self.index.error='Arquivos processados; atualize o índice para atualizar os resultados.'
            return {'done':done,'failed':failed,'mode':job['mode']}


def installed_apps():
    if os.name!='nt':return {'items':[],'supported':False}
    import winreg
    rows={}
    for hive in (winreg.HKEY_CURRENT_USER,winreg.HKEY_LOCAL_MACHINE):
        for view in (winreg.KEY_WOW64_32KEY,winreg.KEY_WOW64_64KEY):
            try:
                with winreg.OpenKey(hive,r'Software\Microsoft\Windows\CurrentVersion\Uninstall',0,winreg.KEY_READ|view) as parent:
                    for i in range(min(winreg.QueryInfoKey(parent)[0],3000)):
                        try:
                            with winreg.OpenKey(parent,winreg.EnumKey(parent,i)) as key:
                                def read(name,default=''):
                                    try:return winreg.QueryValueEx(key,name)[0]
                                    except OSError:return default
                                name=read('DisplayName')
                                if name and not read('SystemComponent',0):
                                    rows[(str(name),str(read('DisplayVersion')))]= {'name':str(name)[:150],'version':str(read('DisplayVersion'))[:80],
                                        'publisher':str(read('Publisher'))[:150],'size':max(0,int(read('EstimatedSize',0)))*1024,'installed':str(read('InstallDate'))[:12]}
                        except (OSError,ValueError,TypeError):continue
            except OSError:continue
    return {'items':sorted(rows.values(),key=lambda r:r['size'],reverse=True)[:600],'supported':True}
