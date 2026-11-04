"""Explicit desktop updates from the paired HTTPS site. Never updates a source checkout."""
import asyncio
import hashlib
import io
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import time
import uuid
import zipfile
from pathlib import Path, PurePosixPath

import httpx
import psutil

from . import __version__
from .connection import relay_url

MAX_PACKAGE = 8 * 1024 * 1024
ROOT = Path(__file__).resolve().parents[1]


def version(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d{1,4}\.\d{1,4}\.\d{1,4}', value):
        raise ValueError('Versão publicada inválida.')
    return tuple(map(int, value.split('.')))


def validate_manifest(data):
    if not isinstance(data, dict):
        raise ValueError('Informações de atualização inválidas.')
    version(data.get('version'))
    if not re.fullmatch('[a-f0-9]{64}', str(data.get('sha256', ''))):
        raise ValueError('Pacote sem verificação de integridade válida.')
    if type(data.get('size')) is not int or not 1 <= data['size'] <= MAX_PACKAGE:
        raise ValueError('Pacote excede o limite permitido.')
    if data.get('url') != '/downloads/vexx-pc-agent-windows.zip':
        raise ValueError('Endereço de atualização inválido.')
    files = data.get('files')
    if not isinstance(files, list) or not 10 <= len(files) <= 100:
        raise ValueError('Lista de arquivos inválida.')
    seen = set()
    for name in files:
        if not isinstance(name, str) or '\\' in name or ':' in name or '\x00' in name:
            raise ValueError('Caminho inválido no pacote.')
        parts = PurePosixPath(name).parts
        if name != PurePosixPath(name).as_posix() or not parts or any(p in ('.', '..') or p.endswith((' ', '.')) for p in parts):
            raise ValueError('Caminho inválido no pacote.')
        reserved = {'CON','PRN','AUX','NUL',*[f'COM{n}' for n in range(1,10)],*[f'LPT{n}' for n in range(1,10)]}
        if any(p.split('.')[0].upper() in reserved or any(c in '<>"|?*' or ord(c) < 32 for c in p) for p in parts):
            raise ValueError('Nome de arquivo inválido no pacote.')
        if name not in ('Vexx-PC/remoto.py', 'Vexx-PC/Instalar.cmd'):
            if not name.startswith('Vexx-PC/pc_companion/') or Path(name).suffix.lower() not in ('.py','.ps1','.cmd','.txt','.md','.html','.css','.js'):
                raise ValueError('Arquivo inesperado no pacote.')
        if name.casefold() in seen:
            raise ValueError('Arquivos duplicados no pacote.')
        seen.add(name.casefold())
    required = ('__init__.py', '__main__.py', 'app.py', 'requirements.txt', 'apply_update.py')
    if any('vexx-pc/pc_companion/' + f not in seen for f in required):
        raise ValueError('Pacote incompleto.')
    return data


def extract_verified(payload, manifest, target):
    validate_manifest(manifest)
    if len(payload) != manifest['size'] or hashlib.sha256(payload).hexdigest() != manifest['sha256']:
        raise ValueError('O download falhou na verificação de integridade. Tente novamente.')
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        infos = archive.infolist()
        if sorted(i.filename for i in infos) != sorted(manifest['files']):
            raise ValueError('Os arquivos não correspondem à versão publicada.')
        if sum(i.file_size for i in infos) > MAX_PACKAGE * 3:
            raise ValueError('Pacote descompactado excede o limite.')
        for info in infos:
            if stat.S_ISLNK(info.external_attr >> 16) or info.flag_bits & 1:
                raise ValueError('Links ou arquivos criptografados não são aceitos.')
        text = archive.read('Vexx-PC/pc_companion/__init__.py').decode('utf-8')
        match = re.search(r'__version__\s*=\s*[\'"]([0-9.]+)[\'"]', text)
        if not match or match.group(1) != manifest['version']:
            raise ValueError('A versão do aplicativo não corresponde ao pacote.')
        # Every member was checked, before writing any bytes to disk.
        archive.extractall(target)


def installed_root():
    try:
        record = json.loads((ROOT / 'installation.json').read_text('utf-8'))
        root = Path(record['install_root']).resolve()
        from .launcher import selected_release
        if selected_release(root) != ROOT or not ROOT.is_relative_to(root / 'releases'):
            return None
        if Path(sys.prefix).resolve() != (ROOT / '.venv').resolve():
            return None
        return root
    except (OSError, ValueError, KeyError, TypeError):
        return None


class Updater:
    def __init__(self, directory, config, connection, log, shutdown):
        self.directory, self.config = Path(directory), config
        self.connection, self.log, self.shutdown = connection, log, shutdown
        self.state = {'current': __version__, 'latest': __version__, 'available': False,
                      'checking': False, 'applying': False, 'error': '', 'checked_at': 0,
                      'installed': installed_root() is not None}
        self.release = None
        self.task = None
        self._check_lock = asyncio.Lock()

    def status(self):
        self.state['installed'] = installed_root() is not None
        try:
            result = json.loads((self.directory / 'update-result.json').read_text('utf-8'))
            self.state['last_result'] = {k:result[k] for k in ('state','version','message','rolled_back') if k in result}
        except (OSError, ValueError):
            pass
        return self.state.copy()

    async def check(self):
        async with self._check_lock:
            return await self._check()

    async def _check(self):
        if self.state['checking'] or self.state['applying']:
            return self.status()
        self.state.update(checking=True, error='')
        try:
            origin = relay_url(self.config.get('relay', ''))
            async with httpx.AsyncClient(timeout=12, follow_redirects=False) as client:
                async with client.stream('GET', origin + '/api/companion/release', headers={'Cache-Control': 'no-cache'}) as response:
                    response.raise_for_status()
                    payload = bytearray()
                    async for chunk in response.aiter_bytes():
                        payload.extend(chunk)
                        if len(payload) > 32000:
                            raise ValueError('Informações de atualização excedem o limite.')
                    data = validate_manifest(json.loads(payload))
            self.release = data
            available = version(data['version']) > version(__version__)
            self.state.update(latest=data['version'], available=available, checked_at=time.time())
        except (ValueError, httpx.HTTPError):
            self.state['error'] = ('Vincule este PC ao seu site Vexx AI para verificar versões.' if not self.config.get('relay')
                                   else 'Não foi possível verificar atualizações. Tente novamente.')
        finally:
            self.state['checking'] = False
        return self.status()

    async def poll(self):
        while True:
            if self.config.get('relay'):
                await self.check()
            await asyncio.sleep(1800)

    async def apply(self):
        if self.state['applying']:
            return self.status()
        if installed_root() is None:
            raise ValueError('A atualização automática funciona na versão instalada. Execute Instalar.cmd primeiro.')
        await self.check()  # Never install an obsolete check or roll back to an older version.
        if self.state['applying']:
            return self.status()
        if self.state['error'] or not self.state['available'] or not self.release:
            raise ValueError(self.state['error'] or 'O Vexx PC já está na versão mais recente.')
        self.state.update(applying=True, error='')
        self.task = asyncio.create_task(self._prepare(self.release.copy()))
        return self.status()

    async def _prepare(self, release):
        stage = self.directory / 'updates' / uuid.uuid4().hex
        try:
            stage.mkdir(parents=True)
            origin = relay_url(self.config.get('relay', ''))
            async with httpx.AsyncClient(timeout=45, follow_redirects=False) as client:
                async with client.stream('GET', origin + release['url'], headers={'Cache-Control':'no-cache'}) as response:
                    response.raise_for_status()
                    payload = bytearray()
                    async for chunk in response.aiter_bytes():
                        payload.extend(chunk)
                        if len(payload) > MAX_PACKAGE:
                            raise ValueError('Download excede o limite permitido.')
            await asyncio.to_thread(extract_verified, bytes(payload), release, stage)
            await self.connection.permission(False)
            root = installed_root()
            if root is None:
                raise ValueError('A instalação mudou. Abra o Vexx PC pelo atalho e tente novamente.')
            job = {'install_root':str(root), 'old_release':str(ROOT), 'stage':str(stage),
                   'directory':str(self.directory.resolve()), 'version':release['version'],
                   'pid':os.getpid(), 'created':psutil.Process().create_time(),
                   'roots':[str(p) for p in getattr(self, 'roots', [])],
                   'no_browser':getattr(self, 'no_browser', False)}
            (stage / 'job.json').write_text(json.dumps(job), 'utf-8')
            shutil.copy2(ROOT / 'pc_companion' / 'apply_update.py', stage / 'apply_update.py')
            output = (stage / 'update.log').open('ab')
            helper = subprocess.Popen([sys.executable, str(stage / 'apply_update.py'), str(stage / 'job.json')],
                                      stdin=subprocess.DEVNULL, stdout=output, stderr=output,
                                      creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            output.close()
            for _ in range(100):
                if (stage / 'ready').exists():
                    self.log('Atualização verificada. Reiniciando o aplicativo; o acesso remoto ficará pausado.')
                    self.shutdown()
                    return
                if helper.poll() is not None:
                    break
                await asyncio.sleep(.1)
            raise ValueError('O instalador não confirmou o início. O aplicativo atual permanece aberto.')
        except Exception:
            self.state.update(applying=False, error='Não foi possível iniciar a atualização. A versão atual foi preservada. Tente novamente.')
            self.log(self.state['error'])
