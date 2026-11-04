"""Offline preparation executed by the installer's bundled Python, never system Python."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import traceback
import uuid


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--wheels', type=Path, required=True)
    parser.add_argument('--root', type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    with (root/'install.log').open('a', encoding='utf-8') as log:
        try:
            sys.path.insert(0, str(args.source))
            from pc_companion import __version__
            from pc_companion.release import BUNDLE_FILES
            release = root/'releases'/(__version__+'-'+uuid.uuid4().hex[:12])
            release.mkdir(parents=True)
            for name in BUNDLE_FILES:
                target = release/'pc_companion'/name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(args.source/'pc_companion'/name, target)
            shutil.copy2(args.source/'remoto.py', release/'remoto.py')
            python = release/'.venv/Scripts/python.exe'
            environment = os.environ.copy()
            # Pip checks PATH entries while creating scripts. Unrelated broken or
            # restricted junctions must not affect this self-contained installation.
            windows = Path(environment.get('SystemRoot', 'C:/Windows'))
            environment['PATH'] = os.pathsep.join(map(str, (python.parent, Path(sys.executable).parent, windows/'System32', windows)))
            commands = [
                [sys.executable, '-m', 'venv', '--without-pip', str(release/'.venv')],
                [str(python), '-m', 'ensurepip', '--upgrade', '--default-pip'],
                [str(python), '-m', 'pip', 'install', '--disable-pip-version-check', '--no-index', '--find-links', str(args.wheels), '-r', str(release/'pc_companion/requirements.txt')],
                [str(python), '-c', 'import pc_companion.app, webview, mss, PIL, psutil; print("Vexx PC ready")'],
            ]
            for command in commands:
                log.write('Running: '+repr(command)+'\n'); log.flush()
                subprocess.run(command, cwd=release, stdin=subprocess.DEVNULL, stdout=log, env=environment,
                    stderr=subprocess.STDOUT, check=True, timeout=300,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
            (release/'installation.json').write_text(json.dumps({'install_root':str(root), 'version':__version__}), 'utf-8')
            shutil.copy2(release/'pc_companion/launcher.py', root/'launch.py')
            pending = root/'current.tmp'
            pending.write_text(json.dumps({'release':release.relative_to(root).as_posix(), 'version':__version__}), 'utf-8')
            pending.replace(root/'current.json')
            log.write('Installation complete: '+__version__+'\n')
        except Exception:
            traceback.print_exc(file=log)
            return 1
    return 0


if __name__=='__main__':
    raise SystemExit(main())
