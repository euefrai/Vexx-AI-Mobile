"""Explicit test-only PC Agent: real jobs/checkpoints/SSE, synthetic source content."""
import os
from pathlib import Path
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

if os.environ.get('VEXX_RESEARCH_FIXTURE') != '1':
    raise SystemExit('Fixture mode must be explicitly enabled')
database = Path(os.environ['JULIA_SQLITE_PATH']).resolve()
if not database.is_relative_to(Path(tempfile.gettempdir()).resolve()):
    raise SystemExit('Fixture database must be inside a disposable temporary directory')

import pc_agent
import research_agents as ra


class Provider:
    nome = 'local-fixture'
    def buscar(self, consulta, limite=6):
        return [{'titulo':'Bateria ZX — fonte de teste', 'url':'https://example.com/fixture-zx',
                 'trecho':'A bateria ZX tem capacidade nominal de 500 ciclos.'}]


def read(url):
    time.sleep(10)  # Deliberate test latency permits reload while the real worker runs.
    image = os.environ['VEXX_FIXTURE_IMAGE_URL']
    return {'titulo':'Bateria ZX — dados fictícios para teste', 'final':url,
            'texto':'A bateria ZX tem capacidade nominal de 500 ciclos. Dados fictícios de teste local.',
            'texto_lido':True, 'access_state':'read', 'midia':[{
                'type':'image', 'title':'Imagem de teste — ícone do aplicativo', 'url':image,
                'thumb':image, 'source_url':image, 'source_title':'Arquivo local do aplicativo',
                'alt':'Ícone usado apenas para verificar o componente de imagem',
                'access_state':'metadata_only', 'validation_state':'unverified', 'analysis_state':'not_analyzed'}]}


ra.provedores_reais = lambda *args, **kwargs: [Provider()]
ra.recuperar_real = lambda: read

if __name__ == '__main__':
    pc_agent.run()
