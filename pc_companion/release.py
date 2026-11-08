"""Reproducible public bundle; shared by downloads, release checks and updater QA."""
import hashlib
import io
import zipfile
from functools import lru_cache
from pathlib import Path

from . import __version__

ROOT = Path(__file__).resolve().parents[1]
BUNDLE_FILES = ('__init__.py', '__main__.py', 'app.py', 'system.py', 'indexer.py',
                'connection.py', 'release.py', 'updater.py', 'apply_update.py', 'launcher.py', 'desktop.py', 'ai.py', 'files.py', 'projects.py', 'project_host.py', 'process_group.py',
                'requirements.txt', 'Instalar.cmd', 'instalar.ps1', 'README.md',
                'web/index.html', 'web/style.css', 'web/app.js', 'web/workspace.js')


@lru_cache(maxsize=1)
def bundle():
    output = io.BytesIO()
    files = {'Vexx-PC/pc_companion/' + name: (ROOT / 'pc_companion' / name).read_bytes().replace(b'\r\n', b'\n')
             for name in BUNDLE_FILES}
    files['Vexx-PC/remoto.py'] = (ROOT / 'remoto.py').read_bytes().replace(b'\r\n', b'\n')
    files['Vexx-PC/Instalar.cmd'] = b'@echo off\r\ncd /d "%~dp0"\r\ncall pc_companion\\Instalar.cmd\r\n'
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, content in sorted(files.items()):
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, content)
    return output.getvalue()


def manifest():
    payload = bundle()
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        files = archive.namelist()
    return {'version': __version__, 'sha256': hashlib.sha256(payload).hexdigest(),
            'size': len(payload), 'url': '/downloads/vexx-pc-agent-windows.zip',
            'files': files, 'minimum_python': '3.12', 'installer_url':'/downloads/vexx-pc-agent-setup.exe',
            'notes': 'Sugestões locais de RAM e arquivos grandes, resumo local de arquivos e pastas, comandos revisados e confirmação antes de executar.'}


def installer_url():
    return f'https://github.com/euefrai/Vexx-AI-Mobile/releases/download/vexx-pc-v{__version__}/Vexx-PC-Setup-{__version__}.exe'
