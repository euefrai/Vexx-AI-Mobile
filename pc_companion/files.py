"""Bounded local browsing and reversible, reviewed file removal. No recursive delete."""
import os
import secrets
import sqlite3
import stat
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

BLOCKED = {'windows','program files','program files (x86)','programdata','appdata',
           '$recycle.bin','system volume information','recovery','boot','.git','.venv','.vexx-venv','venv'}
TRASH = '.vexx-trash'
CATEGORIES = {
    'installers':{'.exe','.msi','.msix','.msixbundle','.appx','.appxbundle','.apk','.aab'},
    'images':{'.jpg','.jpeg','.png','.gif','.webp','.bmp','.svg','.heic','.tiff','.avif'},
    'videos':{'.mp4','.mkv','.mov','.avi','.webm','.m4v','.wmv','.mpeg'},
    'audio':{'.mp3','.wav','.flac','.m4a','.ogg','.aac'},
    'archives':{'.zip','.7z','.rar','.tar','.gz','.bz2','.xz','.iso'},
    'temporary':{'.tmp','.temp','.bak','.old','.log'},
}


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
        return not (any(p.casefold() in BLOCKED or p.casefold()==TRASH for p in path.parts) or path.parent==Path(path.anchor)
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
