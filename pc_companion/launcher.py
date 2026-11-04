"""Stable installed shortcut. Only a successfully verified release changes current.json."""
import json
import os
import subprocess
import sys
from pathlib import Path


def selected_release(root):
    root = Path(root).resolve()
    value = json.loads((root / 'current.json').read_text('utf-8'))['release']
    selected = (root / value).resolve()
    if not selected.is_relative_to(root / 'releases') or selected == root / 'releases':
        raise ValueError('Instalação inválida. Execute o instalador novamente.')
    return selected


def main():
    root = Path(__file__).resolve().parent
    selected = selected_release(root)
    executable = selected / '.venv' / ('Scripts/pythonw.exe' if os.name == 'nt' else 'bin/python')
    subprocess.Popen([str(executable), '-m', 'pc_companion', *sys.argv[1:]], cwd=selected,
                     creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)


if __name__ == '__main__':
    main()
