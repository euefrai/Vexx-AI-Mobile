"""Preferência declarada de fontes por assunto — nunca allowlist exclusiva.

A preferência só muda a ordem das consultas e a pontuação dos candidatos. Ela
não cria resultados, não confirma conteúdo e não impede a busca genérica: se a
fonte preferida falhar, voltar vazia ou não tiver o assunto, o fluxo existente
continua nos demais provedores. A verificação (leitura, data, local, preço)
segue sendo a mesma do Research/Shopping Engine.
"""
from __future__ import annotations

import re
import unicodedata
from urllib.parse import urlsplit


def normalize(text) -> str:
    value = unicodedata.normalize("NFKD", str(text or ""))
    value = "".join(c for c in value if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", value).strip().lower()


def _host(url: str) -> str:
    try:
        host = (urlsplit(str(url or "")).hostname or "").lower()
    except ValueError:
        return ""
    return host[4:] if host.startswith("www.") else host


def _host_matches(host: str, domain: str) -> bool:
    host, domain = (host or "").lower(), (domain or "").lower()
    if host.startswith("www."):
        host = host[4:]
    if domain.startswith("www."):
        domain = domain[4:]
    return bool(host and domain and (host == domain or host.endswith("." + domain)))


# Lojas preferenciais. A ordem é a preferência de descoberta/leitura; o preço
# final continua sendo o critério de exibição do shopping.
SHOPPING_STORES = (
    {"id": "kabum", "label": "KaBuM!", "domain": "kabum.com.br",
     "aliases": ("kabum", "ka bu m")},
    {"id": "shopee", "label": "Shopee", "domain": "shopee.com.br",
     "aliases": ("shopee",)},
    {"id": "mercadolivre", "label": "Mercado Livre", "domain": "mercadolivre.com.br",
     "aliases": ("mercado livre", "mercadolibre")},
    {"id": "americanas", "label": "Americanas", "domain": "americanas.com.br",
     "aliases": ("americanas", "lojas americanas")},
    {"id": "magalu", "label": "Magazine Luiza", "domain": "magazineluiza.com.br",
     "aliases": ("magalu", "magazine luiza")},
    {"id": "amazon", "label": "Amazon", "domain": "amazon.com.br",
     "aliases": ("amazon", "amazon brasil")},
    {"id": "casasbahia", "label": "Casas Bahia", "domain": "casasbahia.com.br",
     "aliases": ("casas bahia",)},
    {"id": "pichau", "label": "Pichau", "domain": "pichau.com.br",
     "aliases": ("pichau",)},
    {"id": "terabyte", "label": "Terabyte Shop", "domain": "terabyteshop.com.br",
     "aliases": ("terabyte", "terabyteshop")},
    {"id": "carrefour", "label": "Carrefour", "domain": "carrefour.com.br",
     "aliases": ("carrefour",)},
)

_SHOPPING_BY_DOMAIN = {store["domain"]: store for store in SHOPPING_STORES}
_SHOPPING_BY_ID = {store["id"]: store for store in SHOPPING_STORES}


def _pack(*, id, label, kind, triggers, domains, secondary=(), aliases=None,
          avoid=(), news_only=False, feeds=(), providers=()):
    return {
        "id": id,
        "label": label,
        "kind": kind,
        "triggers": tuple(re.compile(rx, re.I) for rx in triggers),
        "domains": tuple(domains),
        "secondary": tuple(secondary),
        "aliases": {normalize(alias): domain
                    for alias, domain in (aliases or {}).items()},
        "avoid": tuple(re.compile(rx, re.I) for rx in avoid),
        "news_only": bool(news_only),
        "feeds": tuple(feeds),
        "providers": tuple(providers),
    }


_PACKS_RAW = (
    _pack(
        id="ubata_news", label="Ubatã Notícias", kind="news", news_only=True,
        triggers=(r"\bubata\b", r"\bubatanoticias\b"),
        domains=("ubatanoticias.com.br",),
        secondary=("g1.globo.com",),
        aliases={"ubata noticias": "ubatanoticias.com.br",
                 "ubatanoticias": "ubatanoticias.com.br"},
        feeds=("https://ubatanoticias.com.br/feed/",),
        providers=("bing", "ddg", "google-news", "bing-news"),
    ),
    _pack(
        id="bahia_news", label="Notícias da Bahia", kind="news", news_only=True,
        triggers=(r"\bbahia\b", r"\bsalvador\b", r"\bfeira de santana\b",
                  r"\bilheus\b", r"\bitabuna\b", r"\bporto seguro\b",
                  r"\bjuazeiro\b", r"\bcamacari\b", r"\blauro de freitas\b",
                  r"\bvitoria da conquista\b", r"\binterior da bahia\b"),
        domains=("g1.globo.com",),
        secondary=("atarde.com.br", "correio24horas.com.br"),
        aliases={"a tarde": "atarde.com.br", "correio 24 horas": "correio24horas.com.br"},
        providers=("google-news", "bing-news", "bing", "ddg"),
    ),
    _pack(
        id="world_news", label="Notícias gerais e do mundo", kind="news",
        news_only=True,
        triggers=(r"\bmundo\b", r"\binternacional\b", r"\bexterior\b",
                  r"\bnoticias gerais\b", r"\bmanchetes\b",
                  r"\bnoticias de hoje\b", r"\bultimas noticias\b"),
        domains=("g1.globo.com",),
        secondary=("bbc.com", "reuters.com", "apnews.com",
                   "agenciabrasil.ebc.com.br"),
        aliases={"g1": "g1.globo.com", "g1 globo": "g1.globo.com",
                 "globo": "g1.globo.com", "bbc": "bbc.com",
                 "reuters": "reuters.com", "ap news": "apnews.com",
                 "associated press": "apnews.com",
                 "agencia brasil": "agenciabrasil.ebc.com.br"},
        providers=("google-news", "bing-news", "bing", "ddg"),
    ),
    _pack(
        id="brazil_news", label="Notícias do Brasil", kind="news", news_only=True,
        triggers=(r"\bbrasil\b", r"\bbrazil\b", r"\bnacionais?\b",
                  r"\bpolitica brasileira\b", r"\bgoverno federal\b",
                  r"\bcongresso\b"),
        domains=("g1.globo.com",),
        secondary=("agenciabrasil.ebc.com.br", "folha.uol.com.br",
                   "estadao.com.br"),
        aliases={"agencia brasil": "agenciabrasil.ebc.com.br",
                 "estadao": "estadao.com.br"},
        providers=("google-news", "bing-news", "bing", "ddg"),
    ),
    _pack(
        id="games", label="Jogos e games", kind="topic",
        triggers=(r"\bjogos?\b", r"\bgames?\b", r"\bgameplay\b",
                  r"\bvideogame\b", r"\bconsole\b", r"\bplaystation\b",
                  r"\bxbox\b", r"\bnintendo\b", r"\bsteam\b", r"\besports?\b",
                  r"\be-sports?\b", r"\brpg\b", r"\bminecraft\b",
                  r"\bfortnite\b", r"\bgta\b", r"\bvalorant\b",
                  r"\bleague of legends\b", r"\bcounter-strike\b",
                  r"\bcs2\b", r"\bdota\b", r"\bpixel art\b"),
        avoid=(r"\b(placa|benchmark|consumo|gpu|cpu|hardware)\b",
               r"\b(?:futebol|basquete|volei|tenis|campeonato|brasileirao|"
               r"copa|selecao|time|gol)\b"),
        domains=("ign.com.br",),
        secondary=("eurogamer.pt", "adrenaline.com.br", "tecmundo.com.br",
                   "theenemy.com.br"),
        aliases={"ign": "ign.com.br", "ign brasil": "ign.com.br",
                 "eurogamer": "eurogamer.pt"},
    ),
    _pack(
        id="technology", label="Tecnologia", kind="topic",
        triggers=(r"\btecno?logia\b", r"\bprogramacao\b", r"\bsoftware\b",
                  r"\baplicativo\b", r"\bapp\b", r"\bcomputador\b",
                  r"\bnotebook\b", r"\bcelular\b", r"\bsmartphone\b",
                  r"\bhardware\b", r"\bgpu\b", r"\bcpu\b", r"\bprocessador\b",
                  r"\bplaca de video\b", r"\bseguranca digital\b",
                  r"\blinux\b", r"\bwindows\b", r"\bandroid\b", r"\bios\b",
                  r"\bpython\b", r"\bjavascript\b", r"\btypescript\b",
                  r"\bhtml\b", r"\bcss\b", r"\bsql\b", r"\bapi\b"),
        domains=("tecmundo.com.br",),
        secondary=("canaltech.com.br", "olhardigital.com.br",
                   "adrenaline.com.br", "developer.mozilla.org",
                   "docs.python.org", "stackoverflow.com", "github.com"),
        aliases={"tecmundo": "tecmundo.com.br", "canaltech": "canaltech.com.br",
                 "olhar digital": "olhardigital.com.br",
                 "mozilla": "developer.mozilla.org", "mdn": "developer.mozilla.org"},
    ),
    _pack(
        id="ai", label="Inteligência artificial", kind="topic",
        triggers=(r"\binteligencia artificial\b", r"\bmachine learning\b",
                  r"\baprendizado de maquina\b", r"\bdeep learning\b",
                  r"\bllm\b", r"\bchatgpt\b", r"\bopenai\b",
                  r"\bmodelo de linguagem\b", r"\bredes neurais\b",
                  r"\bgenerative ai\b", r"\bia generativa\b",
                  r"\bagente de ia\b"),
        domains=("arxiv.org",),
        secondary=("openai.com", "deepmind.google", "huggingface.co",
                   "paperswithcode.com", "scielo.br"),
        aliases={"arxiv": "arxiv.org", "openai": "openai.com",
                 "hugging face": "huggingface.co",
                 "huggingface": "huggingface.co"},
    ),
    _pack(
        id="science", label="Ciência", kind="topic",
        triggers=(r"\bciencia\b", r"\bcientific[oa]s?\b", r"\bfisica\b",
                  r"\bquimica\b", r"\bbiologia\b", r"\bastronomia\b",
                  r"\bespaco\b", r"\bnasa\b", r"\bgenetica\b", r"\bevolucao\b",
                  r"\bneurociencia\b", r"\bpesquisa cientifica\b",
                  r"\bfotossintese\b", r"\bcelula\b", r"\batomo\b"),
        domains=("scielo.br",),
        secondary=("nature.com", "science.org", "nasa.gov", "arxiv.org",
                   "pubmed.ncbi.nlm.nih.gov"),
        aliases={"scielo": "scielo.br", "nasa": "nasa.gov",
                 "nature": "nature.com"},
    ),
    _pack(
        id="psychology", label="Comportamento humano e psicologia", kind="topic",
        triggers=(r"\bcomportamento humano\b", r"\bpsicologia\b",
                  r"\bpsicologic[oa]\b", r"\bmente\b", r"\bemocoes?\b",
                  r"\brelacionamentos?\b", r"\bmotivacao\b", r"\bhabitos?\b",
                  r"\bterapia\b", r"\bpsicanalise\b", r"\bfreud\b",
                  r"\bjung\b", r"\bbehaviorismo\b", r"\bcognitiv[oa]\b",
                  r"\bansiedade\b", r"\bdepressao\b",
                  r"\binteligencia emocional\b"),
        domains=("scielo.br",),
        secondary=("apa.org", "pubmed.ncbi.nlm.nih.gov",
                   "theconversation.com", "pepsic.bvsalud.org"),
        aliases={"pepsic": "pepsic.bvsalud.org"},
    ),
    _pack(
        id="health", label="Saúde", kind="topic",
        triggers=(r"\bsaude\b", r"\bdoenca\b", r"\bsintoma\b",
                  r"\btratamento\b", r"\bvacina\b", r"\bmedicamento\b",
                  r"\bremedio\b", r"\bnutricao\b", r"\bdieta\b",
                  r"\bfitness\b", r"\bcancer\b", r"\bdiabetes\b",
                  r"\bgravidez\b", r"\bpediatria\b", r"\bimunidade\b",
                  r"\bpressao alta\b"),
        domains=("fiocruz.br",),
        secondary=("who.int", "pubmed.ncbi.nlm.nih.gov", "scielo.br",
                   "butantan.gov.br"),
        aliases={"fiocruz": "fiocruz.br", "oms": "who.int",
                 "butantan": "butantan.gov.br"},
    ),
    _pack(
        id="philosophy", label="Filosofia", kind="topic",
        triggers=(r"\bfilosofia\b", r"\bfilosof[oa]s?\b", r"\betica\b",
                  r"\bmoral\b", r"\bmetafisica\b", r"\bepistemologia\b",
                  r"\blogica filosofica\b", r"\bexistencialismo\b",
                  r"\bestoic[oa]s?\b", r"\bestoicismo\b", r"\bnietzsche\b",
                  r"\bkant\b", r"\bplatao\b", r"\baristoteles\b",
                  r"\bsocrates\b", r"\bfenomenologia\b", r"\butilitarismo\b",
                  r"\bcontratualismo\b"),
        domains=("plato.stanford.edu",),
        secondary=("iep.utm.edu", "scielo.br", "philpapers.org"),
        aliases={"sep": "plato.stanford.edu",
                 "stanford encyclopedia": "plato.stanford.edu",
                 "plato": "plato.stanford.edu", "iep": "iep.utm.edu"},    ),
    _pack(
        id="mathematics", label="Matemática", kind="topic",
        triggers=(r"\bmatematica\b", r"\bmatematic[oa]s?\b", r"\balgebra\b",
                  r"\bgeometria\b", r"\bcalculo\b", r"\bteorema\b",
                  r"\bequacao\b", r"\btrigonometria\b", r"\blogaritmo\b",
                  r"\bderivada\b", r"\bintegral\b", r"\bmatriz\b",
                  r"\bnumero primo\b", r"\bprobabilidade\b",
                  r"\bestatistica\b", r"\bfuncao quadratica\b"),
        avoid=(r"\bcalculo (renal|biliar|urinario)\b",),
        domains=("mathworld.wolfram.com",),
        secondary=("pt.wikipedia.org", "scielo.br", "impa.br",
                   "mathoverflow.net", "khanacademy.org"),
        aliases={"mathworld": "mathworld.wolfram.com",
                 "wolfram": "mathworld.wolfram.com", "impa": "impa.br"},
    ),
    _pack(
        id="history", label="História", kind="topic",
        triggers=(r"\bhistoria\b", r"\bhistoric[oa]\b", r"\bseculo\b",
                  r"\bguerra\b", r"\brevolucao\b", r"\bimperio\b",
                  r"\bcolonizacao\b", r"\bescravidao\b", r"\bditadura\b",
                  r"\bidade media\b", r"\bantiguidade\b", r"\barqueologia\b",
                  r"\bcivilizacao\b"),
        domains=("britannica.com",),
        secondary=("pt.wikipedia.org", "scielo.br",
                   "brasilescola.uol.com.br", "history.com"),
        aliases={"britannica": "britannica.com",
                 "enciclopedia britannica": "britannica.com"},
    ),
    _pack(
        id="finance", label="Finanças e economia", kind="topic",
        triggers=(r"\bfinancas\b", r"\binvestimento\b", r"\binvestir\b",
                  r"\bbolsa de valores\b", r"\brenda fixa\b",
                  r"\btesouro direto\b", r"\bcdb\b", r"\binflacao\b",
                  r"\bselic\b", r"\bpib\b", r"\bdolar\b", r"\bcambio\b",
                  r"\bimposto de renda\b", r"\breceita federal\b",
                  r"\bcriptomoeda\b", r"\bbitcoin\b", r"\borcamento pessoal\b",
                  r"\bcapital de giro\b", r"\beconomia brasileira\b",
                  r"\beconomia mundial\b", r"\bnoticias de economia\b",
                  r"\bmercado financeiro\b"),
        avoid=(r"\beconomia (circular|criativa|solidaria|do cuidado|de energia|"
               r"de agua|domestica)\b",),
        domains=("bcb.gov.br",),
        secondary=("ibge.gov.br", "gov.br", "infomoney.com.br",
                   "valor.globo.com"),
        aliases={"bcb": "bcb.gov.br", "banco central": "bcb.gov.br",
                 "ibge": "ibge.gov.br", "infomoney": "infomoney.com.br"},
    ),
    _pack(
        id="law", label="Direito", kind="topic",
        triggers=(r"\bdireito\b", r"\bjuridic[oa]\b", r"\blei\b", r"\bleis\b",
                  r"\blegislacao\b", r"\bconstituicao\b", r"\bstf\b",
                  r"\bstj\b", r"\btribunal\b", r"\bprocesso judicial\b",
                  r"\badvogado\b", r"\bcontrato\b", r"\bclt\b",
                  r"\bcodigo civil\b", r"\bcodigo penal\b", r"\blgpd\b",
                  r"\bdireito do consumidor\b"),
        domains=("planalto.gov.br",),
        secondary=("stf.jus.br", "stj.jus.br", "cnj.jus.br",
                   "jusbrasil.com.br"),
        aliases={"planalto": "planalto.gov.br", "stf": "stf.jus.br",
                 "stj": "stj.jus.br", "jusbrasil": "jusbrasil.com.br"},
    ),
    _pack(
        id="education", label="Educação", kind="topic",
        triggers=(r"\beducacao\b", r"\bescola\b", r"\buniversidade\b",
                  r"\bvestibular\b", r"\benem\b", r"\bconcurso\b",
                  r"\bbolsa de estudos\b", r"\bprofessor\b", r"\baluno\b",
                  r"\baprendizagem\b", r"\bpedagogia\b", r"\bmec\b",
                  r"\binep\b", r"\bcurso\b"),
        domains=("mec.gov.br",),
        secondary=("inep.gov.br", "gov.br", "scielo.br",
                   "brasilescola.uol.com.br", "khanacademy.org"),
        aliases={"mec": "mec.gov.br", "inep": "inep.gov.br",
                 "khan academy": "khanacademy.org"},
    ),
    _pack(
        id="sports", label="Esportes", kind="topic",
        triggers=(r"\besportes?\b", r"\bfutebol\b", r"\bbasquete\b",
                  r"\bvolei\b", r"\btenis\b", r"\bolimpiadas?\b",
                  r"\bcopa\b", r"\bbrasileirao\b", r"\bcampeonato\b",
                  r"\batleta\b", r"\bflamengo\b", r"\bcorinthians\b",
                  r"\bpalmeiras\b", r"\bselecao\b"),
        domains=("ge.globo.com",),
        secondary=("espn.com.br", "olympics.com", "cbf.com.br",
                   "lance.com.br"),
        aliases={"espn": "espn.com.br",
                 "cbf": "cbf.com.br"},
    ),
    _pack(
        id="entertainment", label="Cinema, séries e música", kind="topic",
        triggers=(r"\bfilmes?\b", r"\bseries?\b", r"\bcinema\b",
                  r"\bmusica\b", r"\balbum\b", r"\bnovela\b", r"\bator\b",
                  r"\batriz\b", r"\boscar\b", r"\bnetflix\b",
                  r"\bstreaming\b", r"\bcelebridade\b", r"\bcultura pop\b",
                  r"\bshow\b"),
        domains=("g1.globo.com",),
        secondary=("omelete.com.br", "rollingstone.uol.com.br", "imdb.com",
                   "adorocinema.com"),
        aliases={"omelete": "omelete.com.br", "imdb": "imdb.com",
                 "adorocinema": "adorocinema.com",
                 "rolling stone": "rollingstone.uol.com.br"},
    ),
    _pack(
        id="books", label="Livros e literatura", kind="topic",
        triggers=(r"\blivros?\b", r"\bliteratura\b", r"\bromance\b",
                  r"\bpoesia\b", r"\bescritor\b", r"\bautor\b", r"\bisbn\b",
                  r"\beditora\b", r"\bresenha de livro\b"),
        domains=("openlibrary.org",),
        secondary=("goodreads.com", "pt.wikipedia.org", "scielo.br"),
        aliases={"open library": "openlibrary.org",
                 "goodreads": "goodreads.com"},
    ),
    _pack(
        id="cooking", label="Culinária", kind="topic",
        triggers=(r"\breceitas?\b", r"\bculinaria\b", r"\bcozinhar\b",
                  r"\bingredientes\b", r"\bbolo\b", r"\bpao\b", r"\bcarne\b",
                  r"\bfrango\b", r"\bsobremesa\b", r"\bcozinha\b"),
        domains=("tudogostoso.com.br",),
        secondary=("panelinha.com.br", "receitas.globo.com"),
        aliases={"tudo gostoso": "tudogostoso.com.br",
                 "panelinha": "panelinha.com.br"},
    ),
    _pack(
        id="travel", label="Viagem e turismo", kind="topic",
        triggers=(r"\bviagem\b", r"\bviajar\b", r"\bturismo\b", r"\bdestino\b",
                  r"\bhotel\b", r"\bpasseio\b", r"\broteiro\b", r"\bpraia\b",
                  r"\bcidade turistica\b"),
        domains=("visitbrasil.com",),
        secondary=("melhoresdestinos.com.br", "viajeaqui.abril.com.br",
                   "tripadvisor.com.br"),
        aliases={"visit brasil": "visitbrasil.com",
                 "melhores destinos": "melhoresdestinos.com.br",
                 "tripadvisor": "tripadvisor.com.br"},
    ),
    _pack(
        id="cars", label="Carros e veículos", kind="topic",
        triggers=(r"\bcarros?\b", r"\bautomoveis?\b", r"\bmotos?\b",
                  r"\bmotocicleta\b", r"\bveiculos?\b", r"\bcombustivel\b",
                  r"\bipva\b", r"\bcnh\b", r"\bdetran\b", r"\brevisao\b",
                  r"\bmodelo de carro\b", r"\bpecas? de (?:carro|moto|veiculo)\b"),
        avoid=(r"\b(?:computador|notebook|celular|gpu|cpu|placa|hardware|"
               r"eletrodomestico)\b",),
        domains=("quatrorodas.abril.com.br",),
        secondary=("autoesporte.globo.com", "webmotors.com.br", "gov.br"),
        aliases={"quatro rodas": "quatrorodas.abril.com.br",
                 "autoesporte": "autoesporte.globo.com",
                 "webmotors": "webmotors.com.br"},
    ),
    _pack(
        id="environment", label="Meio ambiente", kind="topic",
        triggers=(r"\bmeio ambiente\b", r"\bsustentabilidade\b",
                  r"\bdesmatamento\b", r"\baquecimento global\b",
                  r"\bmudanca climatica\b", r"\breciclagem\b",
                  r"\bpoluicao\b", r"\bbiodiversidade\b", r"\bamazonia\b",
                  r"\benergia renovavel\b", r"\besg\b"),
        domains=("gov.br",),
        secondary=("wwf.org.br", "sosma.org.br", "ipcc.ch", "scielo.br",
                   "oeco.org.br"),
        aliases={"wwf": "wwf.org.br", "sos mata atlantica": "sosma.org.br",
                 "ipcc": "ipcc.ch", "oeco": "oeco.org.br"},
    ),
    _pack(
        id="home", label="Casa e reforma", kind="topic",
        triggers=(r"\breforma\b", r"\bdecoracao\b", r"\bmoveis\b",
                  r"\bjardim\b", r"\blimpeza\b", r"\beletrodomestico\b",
                  r"\bhidraulica\b", r"\beletrica residencial\b",
                  r"\bpintura de parede\b"),
        domains=("casa.com.br",),
        secondary=("casavogue.globo.com", "revistacasaejardim.globo.com"),
        aliases={"casa e jardim": "revistacasaejardim.globo.com",
                 "casa vogue": "casavogue.globo.com"},
    ),
    _pack(
        id="pets", label="Pets", kind="topic",
        triggers=(r"\bpets?\b", r"\bcachorros?\b", r"\bgatos?\b",
                  r"\banimal de estimacao\b", r"\bveterinari[oa]\b",
                  r"\bracao\b", r"\badestramento\b"),
        domains=("petmd.com",),
        secondary=("vetstreet.com", "scielo.br"),
        aliases={"petmd": "petmd.com", "vetstreet": "vetstreet.com"},
    ),
    _pack(
        id="agriculture", label="Agricultura e agro", kind="topic",
        triggers=(r"\bagricultura\b", r"\bagro\b", r"\bplantacao\b",
                  r"\bcolheita\b", r"\bsolo\b", r"\bfertilizante\b",
                  r"\bpecuaria\b", r"\bcafe\b", r"\bsoja\b", r"\bmilho\b",
                  r"\birrigacao\b"),
        domains=("embrapa.br",),
        secondary=("agricultura.gov.br", "scielo.br", "canalrural.com.br"),
        aliases={"embrapa": "embrapa.br", "canal rural": "canalrural.com.br"},
    ),
    _pack(
        id="religion", label="Religião", kind="topic",
        triggers=(r"\breligiao\b", r"\breligios[oa]\b", r"\bbiblia\b",
                  r"\bcristianismo\b", r"\bcatolicismo\b", r"\bevangelic[oa]\b",
                  r"\bislamismo\b", r"\bjudaismo\b", r"\bbudismo\b",
                  r"\bespiritismo\b", r"\bumbanda\b", r"\bcandomble\b",
                  r"\bateismo\b"),
        domains=("britannica.com",),
        secondary=("vaticannews.va", "scielo.br", "pewresearch.org"),
        aliases={"vatican news": "vaticannews.va",
                 "pew research": "pewresearch.org"},
    ),
    _pack(
        id="shopping", label="Compras e ofertas", kind="shopping",
        triggers=(r"\bprecos?\b", r"\bcomprar\b", r"\bcompra\b",
                  r"\bofertas?\b", r"\bpromocao\b", r"\bmais barato\b",
                  r"\bcusto beneficio\b", r"\bvale a pena\b",
                  r"\bonde encontrar\b", r"\bquanto custa\b"),
        domains=tuple(store["domain"] for store in SHOPPING_STORES),
        aliases={alias: store["domain"] for store in SHOPPING_STORES
                 for alias in store["aliases"]},
    ),
)

PACKS = tuple(_PACKS_RAW)
PACK_BY_ID = {pack["id"]: pack for pack in PACKS}

_RX_DOMAIN = re.compile(
    r"(?<![\w@.-])((?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+"
    r"(?:com\.br|org\.br|gov\.br|edu\.br|net\.br|com|org|net|edu|gov|io|dev|"
    r"ai|co|info|me|tv|br))(?![\w.-])"
)
_RX_NEWS_CONTEXT = re.compile(
    r"\b(?:noticias?|manchetes|aconteceu|acontecimentos?|eleicoes?|eleicao|"
    r"governo|hoje|ontem|anteontem|semana|recentes?|ultimas?|urgente)\b"
)
_RX_SHOPPING_CONTEXT = re.compile(
    r"\b(?:precos?|comprar|compra|ofertas?|promocao|barato|loja|"
    r"quanto custa|onde encontrar|vale a pena|produto)\b"
)
_RX_SITE_TOKEN = re.compile(r"\bsite:\S+", re.I)


def _news_context(norm: str, request: dict | None) -> bool:
    return (str((request or {}).get("domain") or "") == "news"
            or bool(_RX_NEWS_CONTEXT.search(norm)))


def _shopping_context(norm: str, request: dict | None) -> bool:
    if str((request or {}).get("domain") or "") in (
            "news", "events", "science", "documents", "air_travel",
            "bus_travel", "currency"):
        return False
    return bool(_RX_SHOPPING_CONTEXT.search(norm))


def _plan_from_pack(pack: dict, *, explicit: bool = False,
                    alias: str = "", domain: str = "") -> dict:
    primary = tuple([domain] if domain else pack["domains"])
    domains = tuple(dict.fromkeys(primary + tuple(pack["secondary"])))
    return {
        "id": pack["id"],
        "label": pack["label"],
        "kind": pack["kind"],
        "primary": primary,
        "secondary": tuple(pack["secondary"]),
        "domains": domains,
        "aliases": dict(pack["aliases"]),
        "feeds": tuple(pack.get("feeds") or ()),
        "providers": tuple(pack.get("providers") or ()),
        "explicit": bool(explicit),
        "alias": alias,
        "reason": ("fonte pedida explicitamente" if explicit
                   else "assunto com fonte preferencial declarada"),
    }


def _explicit_plan(domain: str) -> dict:
    return {
        "id": "explicit_source",
        "label": domain,
        "kind": "explicit",
        "primary": (domain,),
        "secondary": (),
        "domains": (domain,),
        "aliases": {},
        "feeds": (),
        "providers": (),
        "explicit": True,
        "alias": "",
        "reason": "domínio citado explicitamente pelo usuário",
    }


def explicit_source(text: str, *, kinds=None, request: dict | None = None):
    """Primeira fonte nomeada pelo usuário (domínio ou apelido conhecido).

    Só é reconhecida quando o nome aparece como palavra/frase; um domínio
    explícito sempre vence. Fontes de compra exigem contexto de compra para
    apelidos ambíguos (ex.: "Americanas"), mas um domínio completo vale sempre.
    """
    norm = normalize(text)
    if not norm:
        return None
    best = None

    def _consider(start, pack, domain, alias=""):
        nonlocal best
        candidate = (start, -PACKS.index(pack), pack, domain, alias)
        if best is None or candidate[:2] < best[:2]:
            best = candidate

    for pack in PACKS:
        if kinds and pack["kind"] not in kinds:
            continue
        for domain in pack["domains"]:
            match = re.search(r"(?<![\w.-])" + re.escape(domain) + r"(?![\w.-])",
                              norm)
            if match:
                _consider(match.start(), pack, domain)

    for pack in PACKS:
        if kinds and pack["kind"] not in kinds:
            continue
        if pack["news_only"] and not _news_context(norm, request):
            continue
        if pack["kind"] == "shopping" and not _shopping_context(norm, request):
            continue
        for alias, domain in pack["aliases"].items():
            if not alias:
                continue
            if alias in ("g1", "globo") and not _news_context(norm, request):
                # "globo ocular"/"g1 da meiose" não são o portal de notícias.
                continue
            match = re.search(r"(?<!\w)" + re.escape(alias) + r"(?!\w)", norm)
            if match:
                _consider(match.start(), pack, domain, alias)

    if best is not None:
        _, _, pack, domain, alias = best
        return _plan_from_pack(pack, explicit=True, alias=alias, domain=domain)

    unknown = _RX_DOMAIN.search(norm)
    if unknown:
        return _explicit_plan(unknown.group(1))
    return None


def _generic_news(norm: str) -> bool:
    """Noticiário sem assunto próprio — só aí o pacote mundial é preferido.

    "notícias energia solar" tem assunto: a fonte preferida do tema (ou a
    busca genérica) responde; trocar isso por "notícias do mundo" esconderia
    o pedido real.
    """
    restante = re.sub(
        r"\b(?:noticias?|manchetes|aconteceu|acontecimentos?|novidades|"
        r"hoje|ontem|anteontem|agora|recentes?|recentemente|ultimas?|"
        r"ultima|semana|mes|ano|de|do|da|dos|das|e|o|a|os|as|no|na|nos|nas|"
        r"em|por|para|sobre|gerais|general|internacional|mundo|exterior)\b",
        " ", norm)
    palavras = [p for p in re.findall(r"[a-z0-9]{3,}", restante)
                if p not in {"que", "qual", "quais", "como", "onde", "quando"}]
    return not palavras


def detect(text: str, request: dict | None = None) -> dict | None:
    """Plano de prioridade para a consulta; None quando não há preferência."""
    norm = normalize(text)
    if not norm:
        return None
    explicit = explicit_source(text, request=request)
    if explicit:
        return explicit

    # Editorial technology/news preferences must not outrank a request for
    # official documentation. Native documentation providers keep their order.
    if re.search(r'\b(?:documentac(?:ao|oes) oficia(?:l|is)|official documentation)\b', norm):
        return None

    news = _news_context(norm, request)
    shopping = _shopping_context(norm, request)
    candidates = []
    for order, pack in enumerate(PACKS):
        if pack["news_only"] and not news:
            continue
        if pack["kind"] == "shopping" and not shopping:
            continue
        if any(rx.search(norm) for rx in pack["avoid"]):
            continue
        score = sum(1 for rx in pack["triggers"] if rx.search(norm))
        if score:
            candidates.append((score, -order, pack))
    if candidates:
        candidates.sort(reverse=True)
        return _plan_from_pack(candidates[0][2])
    if news and _generic_news(norm):
        return _plan_from_pack(PACK_BY_ID["world_news"])
    return None


def site_queries(plan: dict | None, text: str, limit: int = 1) -> list:
    """Uma consulta com escopo de site, preservando o pedido original."""
    if not plan or not plan.get("primary"):
        return []
    base = clean_query(text, plan)
    if not base:
        base = str(text or "").strip()
    out = []
    for domain in plan["primary"][:max(1, int(limit))]:
        suffix=f' site:{domain}'
        query = re.sub(r"\s+", " ", base[:240-len(suffix)]+suffix).strip()
        if query not in out:
            out.append(query)
    return out[:max(1, int(limit))]


def clean_query(text: str, plan: dict | None = None) -> str:
    """Remove a menção à fonte para não repetir o nome dentro da busca."""
    value = _RX_SITE_TOKEN.sub(" ", str(text or ""))
    value = re.sub(r"\b(?:no|do|da|em)\s+site\b", " ", value, flags=re.I)
    if plan:
        for domain in plan.get("domains") or ():
            value = re.sub(re.escape(domain), " ", value, flags=re.I)
        for alias in sorted((plan.get("aliases") or {}), key=len, reverse=True):
            value = re.sub(r"(?<!\w)" + re.escape(alias) + r"(?!\w)", " ",
                           value, flags=re.I)
    value = re.sub(r"^(?:pesquise|pesquisar|busque|buscar|procure|encontre|"
                   r"mostre|liste)\s+", "", value, flags=re.I)
    value = re.sub(r"\s+", " ", value).strip(" .,;:-")
    value = re.sub(r"\b(?:de|do|da|dos|das|no|na|nos|nas|em|sobre|para|por)"
                   r"\s*$", "", value, flags=re.I).strip(" .,;:-")
    return value[:200]


def score(item: dict, plan: dict | None):
    """(bônus, papel) da URL no plano; nunca apaga nem valida o candidato."""
    if not plan:
        return 0.0, ""
    host = _host((item or {}).get("url", ""))
    if not host:
        return 0.0, ""
    if plan.get("explicit"):
        domain = (plan.get("primary") or [""])[0]
        return (6.0, "explicit") if _host_matches(host, domain) else (0.0, "")
    primary = (plan.get("primary") or [""])[0]
    if _host_matches(host, primary):
        return 3.0, "primary"
    for domain in plan.get("secondary") or ():
        if _host_matches(host, domain):
            return 1.5, "secondary"
    return 0.0, ""


def describe(plan: dict | None) -> dict | None:
    if not plan:
        return None
    return {
        "id": plan.get("id"),
        "label": plan.get("label"),
        "kind": plan.get("kind"),
        "primary": list(plan.get("primary") or ()),
        "secondary": list(plan.get("secondary") or ()),
        "explicit": bool(plan.get("explicit")),
        "reason": plan.get("reason", ""),
    }


def explicit_store(text: str, *, require_request: bool = False):
    """Loja nomeada; escopo exclusivo exige referência à loja, não à marca."""
    norm = normalize(text)
    if not norm:
        return None
    best = None
    requested = set()
    def store_requested(match, store):
        if not require_request:
            return True
        before, after = norm[:match.start()], norm[match.end():]
        # Amazon is also a device brand. "Amazon Echo" alone must retain
        # other merchants, even when a search provider recognizes the brand.
        product_brand = store['id'] == 'amazon' and re.match(
            r'\s+(?:echo|fire|kindle|alexa|basics)\b', after)
        named_site = re.search(r'\b(?:loja|site|marketplace)\s+(?:(?:da|do|de)\s+)?$', before)
        if product_brand and not named_site:
            return False
        return bool(named_site or re.search(
            r'\b(?:na|no|nas|nos|pela|pelo|em|so|apenas|somente|exclusivamente)'
            r'\s+(?:(?:na|no|em|a|o)\s+)?$', before)
            or re.match(r'\s*(?:apenas|somente|exclusivamente)\b', after))
    for order, store in enumerate(SHOPPING_STORES):
        for alias in store["aliases"]:
            for match in re.finditer(r"(?<!\w)" + re.escape(alias) + r"(?!\w)", norm):
                if store_requested(match, store):
                    requested.add(store['domain'])
                    candidate = (match.start(), order, store)
                    if best is None or candidate[:2] < best[:2]:
                        best = candidate
        domain = store["domain"]
        match = re.search(r"(?<![\w.-])(?:www\.)?" + re.escape(domain) + r"(?![\w.-])",
                          norm)
        if match:
            requested.add(store['domain'])
            candidate = (match.start(), order, store)
            if best is None or candidate[:2] < best[:2]:
                best = candidate
    if require_request and len(requested) > 1:
        return None  # A comparison between stores is not one exclusive store.
    return best[2] if best else None


def _best_store_for(text: str) -> dict:
    norm = normalize(text)
    if re.search(r"\b(?:notebook|celular|smartphone|placa|gpu|cpu|monitor|"
                 r"teclado|mouse|console|videogame|hardware|pc gamer)\b", norm):
        return _SHOPPING_BY_ID["kabum"]
    if re.search(r"\b(?:livros?|kindle|isbn)\b", norm):
        return _SHOPPING_BY_ID["amazon"]
    if re.search(r"\b(?:roupa|tenis|moda|beleza|maquiagem|brinquedo)\b", norm):
        return _SHOPPING_BY_ID["shopee"]
    if re.search(r"\b(?:geladeira|fogao|maquina de lavar|movel|sofa|colchao|"
                 r"casa)\b", norm):
        return _SHOPPING_BY_ID["magalu"]
    return _SHOPPING_BY_ID["mercadolivre"]


def shopping_queries(text: str, base_query: str | None = None,
                     limit: int = 1) -> list:
    """Consultas web com escopo nas lojas preferidas (nunca no MLB)."""
    base = _RX_SITE_TOKEN.sub(" ", str(base_query or text or ""))
    base = re.sub(r"\b(?:no|do|da|em)\s+site\b", " ", base, flags=re.I)
    base = re.sub(r"\s+", " ", base).strip(" .,;:-")[:180]
    explicit = explicit_store(text)
    if explicit:
        # O nome da loja já vai no `site:`; repeti-lo na busca só gasta termo.
        for alias in sorted(explicit["aliases"], key=len, reverse=True):
            base = re.sub(r"(?<!\w)" + re.escape(alias) + r"(?!\w)", " ",
                          base, flags=re.I)
        base = re.sub(re.escape(explicit["domain"]), " ", base, flags=re.I)
        base = re.sub(r"\b(?:na|no|nas|nos|da|do|das|dos|de|em)\s*$", "",
                      re.sub(r"\s+", " ", base).strip(), flags=re.I)
        base = base.strip(" .,;:-")
    if not base:
        return []
    if explicit:
        queries = [f"{base} site:{explicit['domain']}"]
    else:
        domains = [store["domain"] for store in SHOPPING_STORES[:6]]
        while len(domains)>1 and len(base)+3+len(' OR '.join(f'site:{d}' for d in domains))>240:
            domains.pop()
        sites = " OR ".join(f"site:{domain}" for domain in domains)
        queries = [f"{base} ({sites})"]
        if int(limit) > 1:
            queries.append(f"{base} site:{_best_store_for(text)['domain']}")
    out = []
    for query in queries[:max(1, int(limit))]:
        query = re.sub(r"\s+", " ", query).strip()[:240]
        if query not in out:
            out.append(query)
    return out


def shopping_rank(url: str) -> int:
    """Posição da loja na preferência; 99 quando não é loja preferida."""
    host = _host(url)
    for index, store in enumerate(SHOPPING_STORES):
        if _host_matches(host, store["domain"]):
            return index
    return 99


def is_preferred_store(url: str) -> bool:
    return shopping_rank(url) < len(SHOPPING_STORES)
