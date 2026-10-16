/* JDUI 1.0 — JULIA Dynamic UI Engine (frontend).
   Renderiza blocos declarativos `JULIA-ui-message/v1` com componentes NATIVOS.
   Nenhum JavaScript do modelo é executado: só funções deste registry.
   Espelho da validação em `jdui.py` (backend). */
'use strict';
(function () {
  const VERSION = 'JULIA-ui-message/v1';
  const MAX_STR = 2000;

  function S(v, lim) {
    if (typeof v === 'number') v = String(v);
    if (typeof v !== 'string') return '';
    return v.slice(0, lim || MAX_STR);
  }
  function N(v, dflt) { const n = parseFloat(v); return Number.isFinite(n) ? n : (dflt || 0); }
  function URL_OK(u) {
    u = S(u, 500);
    if (!/^https?:\/\//.test(u)) return '';
    try {
      const p = new URL(u, location.href);
      return (p.protocol === 'http:' || p.protocol === 'https:') && p.hostname &&
        !p.username && !p.password ? p.href : '';
    }
    catch (_) { return ''; }
  }
  function PROVENANCE(value) {
    if (value === undefined || value === null) return [];
    if (!Array.isArray(value) || value.length > 20) throw new JduiErro('sources até 20 referências');
    const ids = Object.create(null);
    return value.map(source => {
      if (!source || typeof source !== 'object') throw new JduiErro('source inválida');
      const id = S(source.id, 100), title = S(source.title, 160);
      if (!id || !title || ids[id]) throw new JduiErro('source exige id e título únicos');
      ids[id] = true;
      return {
        id, title, url: URL_OK(source.url), locator: S(source.locator, 120),
        period: S(source.period, 100), methodology: S(source.methodology, 200),
        analysis_method: S(source.analysis_method, 80)
      };
    });
  }
  function renderProvenance(root, sources) {
    if (!Array.isArray(sources) || !sources.length) return;
    const box = el('div', 'jdui-provenance');
    box.appendChild(el('span', '', 'Referências:'));
    const list = document.createElement('ul');
    sources.forEach(source => {
      const item = document.createElement('li');
      const details = [source.locator, source.period, source.methodology,
        source.analysis_method ? 'analysis: ' + source.analysis_method : ''].filter(Boolean);
      const label = source.title + (details.length ? ' — ' + details.join(' · ') : '');
      if (source.url) {
        const link = el('a', '', label);
        link.href = source.url;
        link.target = '_blank';
        link.rel = 'noopener noreferrer';
        item.appendChild(link);
      } else {
        item.appendChild(el('span', '', label));
      }
      list.appendChild(item);
    });
    box.appendChild(list);
    root.appendChild(box);
  }
  function el(tag, cls, text) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined && text !== null) e.textContent = text;
    return e;
  }

  /* ----- Validação (espelho de jdui.py) ----- */
  function JduiErro(m) { this.message = m; }
  function reqList(p, k, a, b, msg) {
    const v = p[k];
    if (!Array.isArray(v) || v.length < a || v.length > b) throw new JduiErro(msg);
    return v;
  }
  const V = {
    quiz(p) {
      const qs = reqList(p, 'questions', 1, 12, 'quiz.questions 1..12');
      return {
        title: S(p.title, 160),
        questions: qs.map(q => {
          if (!q || typeof q !== 'object') throw new JduiErro('quiz.question');
          const opts = reqList(q, 'options', 2, 6, 'quiz.options 2..6');
          const ans = q.answer;
          if (!Number.isInteger(ans) || ans < 0 || ans >= opts.length) throw new JduiErro('quiz.answer');
          return { q: S(q.q, 400), options: opts.map(o => S(o, 200)), answer: ans, explain: S(q.explain, 500) };
        })
      };
    },
    checklist(p) {
      const itens = reqList(p, 'items', 1, 30, 'checklist.items 1..30');
      return {
        title: S(p.title, 160),
        items: itens.map(i => (i && typeof i === 'object'
          ? { label: S(i.label, 200), checked: !!i.checked }
          : { label: S(i, 200), checked: false }))
      };
    },
    calculator(p) {
      const kind = (S(p.kind, 40).toLowerCase() || 'basic');
      if (['basic', 'imc', 'porcentagem', 'juros', 'conversor'].indexOf(kind) < 0) throw new JduiErro('calculator.kind');
      return { kind, title: S(p.title, 120) };
    },
    cards(p) {
      const itens = reqList(p, 'items', 1, 8, 'cards.items 1..8');
      return {
        title: S(p.title, 160),
        items: itens.map(c => {
          if (!c || typeof c !== 'object' || !S(c.title)) throw new JduiErro('cards.item');
          const a = (c.action && typeof c.action === 'object') ? c.action : {};
          return {
            title: S(c.title, 160), desc: S(c.desc, 400), value: S(c.value, 80),
            badge: S(c.badge, 40), url: URL_OK(c.url),
            action: a.chat ? { chat: S(a.chat, 300) } : {}
          };
        })
      };
    },
    diagram(p) {
      const nos = reqList(p, 'nodes', 1, 12, 'diagram.nodes 1..12');
      const ids = {};
      const nodes = nos.map(n => {
        if (!n || typeof n !== 'object' || !S(n.id, 40)) throw new JduiErro('diagram.node');
        const id = S(n.id, 40); ids[id] = 1;
        return { id, label: S(n.label, 120), desc: S(n.desc, 300), status: S(n.status, 20),
                 icon: S(n.icon, 12), group: S(n.group, 60) };
      });
      const edges = [];
      (Array.isArray(p.edges) ? p.edges : []).forEach(e => {
        if (!e || typeof e !== 'object') return;
        const f = S(e.from, 40), t = S(e.to, 40);
        if (ids[f] && ids[t] && edges.length < 16) edges.push({ from: f, to: t, label: S(e.label, 80) });
      });
      const dir = S(p.direction, 10).toLowerCase();
      return { title: S(p.title, 160), nodes, edges, direction: dir === 'h' ? 'h' : 'v' };
    },
    table(p) {
      const cols = reqList(p, 'columns', 1, 8, 'table.columns 1..8').map(c => S(c, 80));
      const rows = p.rows;
      if (!Array.isArray(rows) || rows.length > 30) throw new JduiErro('table.rows max 30');
      return {
        title: S(p.title, 160), columns: cols,
        rows: rows.map(r => {
          if (!Array.isArray(r)) throw new JduiErro('table.row lista');
          return r.slice(0, cols.length).map(c => S(c, 200));
        })
      };
    },
    form(p) {
      const fs = reqList(p, 'fields', 1, 10, 'form.fields 1..10');
      const kinds = ['imc', 'juros', 'porcentagem', 'soma'];
      const calc = S(p.calc, 40).toLowerCase();
      if (calc && kinds.indexOf(calc) < 0) throw new JduiErro('form.calc');
      return {
        title: S(p.title, 160),
        fields: fs.map(f => {
          if (!f || typeof f !== 'object' || !S(f.name, 40)) throw new JduiErro('form.field');
          const t = S(f.type, 10).toLowerCase() || 'text';
          if (['text', 'number', 'select'].indexOf(t) < 0) throw new JduiErro('form.field.type');
          return {
            name: S(f.name, 40), label: S(f.label, 80), type: t,
            options: t === 'select' ? (Array.isArray(f.options) ? f.options.slice(0, 8).map(o => S(o, 80)) : []) : [],
            required: !!f.required
          };
        }),
        calc, submit: S(p.submit, 40) || 'Calcular'
      };
    },
    progress(p) {
      const max = N(p.max, 100) || 100;
      return { label: S(p.label, 120), value: Math.min(Math.max(N(p.value), 0), max), max };
    },
    exam(p) {
      const aid = S(p.assessment_id, 64);
      if (!/^[A-Za-z0-9_-]{2,64}$/.test(aid)) throw new JduiErro('exam.assessment_id');
      return { assessment_id: aid, title: S(p.title, 160) };
    },
    tabs(p) {
      const abas = reqList(p, 'tabs', 2, 6, 'tabs 2..6');
      return { tabs: abas.filter(a => a && a.title).map(a => ({ title: S(a.title, 80), markdown: S(a.markdown, 3000) })) };
    },
    accordion(p) {
      const itens = reqList(p, 'items', 1, 10, 'accordion 1..10');
      return { items: itens.filter(a => a && a.title).map(a => ({ title: S(a.title, 120), markdown: S(a.markdown, 3000) })) };
    },
    studyplan(p) {
      const pid = S(p.plan_id, 64);
      if (!/^[A-Za-z0-9_-]{2,64}$/.test(pid)) throw new JduiErro('studyplan.plan_id');
      return { plan_id: pid };
    },
    flashcards(p) {
      return { assunto: S(p.assunto, 120) };
    },
    studyprogress(p) {
      return {};
    },
    lesson(p) {
      const lid = S(p.lesson_id, 64);
      if (!/^[A-Za-z0-9_-]{2,64}$/.test(lid)) throw new JduiErro('lesson.lesson_id');
      return { lesson_id: lid, title: S(p.title, 160) };
    },
    chart(p) {
      const tipos = ['line', 'bar', 'pie', 'area', 'scatter'];
      const tipo = String(p.type || 'bar').toLowerCase();
      if (tipos.indexOf(tipo) < 0) throw new JduiErro('chart.type');
      const ss = p.series;
      if (!Array.isArray(ss) || ss.length < 1 || ss.length > 6) throw new JduiErro('chart.series 1..6');
      if (tipo === 'pie' && ss.length !== 1) throw new JduiErro('chart pie: 1 série');
      const fin = v => {
        const f = parseFloat(v);
        if (!Number.isFinite(f) || Math.abs(f) > 1e12) throw new JduiErro('chart: valor inválido');
        return f;
      };
      const series = ss.map(s => {
        if (!s || typeof s !== 'object') throw new JduiErro('chart.serie');
        const vals = s.values;
        if (!Array.isArray(vals) || !vals.length || vals.length > 24) throw new JduiErro('chart.values 1..24');
        if (tipo === 'scatter') {
          return {
            label: S(s.label, 60),
            values: vals.map(v => {
              if (!Array.isArray(v) || v.length !== 2) throw new JduiErro('chart scatter: pares [x,y]');
              return [fin(v[0]), fin(v[1])];
            })
          };
        }
        return { label: S(s.label, 60), values: vals.map(fin) };
      });
      const labels = Array.isArray(p.labels) ? p.labels.map(l => S(l, 40)).slice(0, 24) : [];
      if (labels.length && tipo !== 'scatter' && labels.length !== series[0].values.length) {
        throw new JduiErro('chart.labels acompanha valores');
      }
      return {
        type: tipo, title: S(p.title, 160), labels, series,
        source: S(p.source, 160), x_label: S(p.x_label, 60), y_label: S(p.y_label, 60),
        sources: PROVENANCE(p.sources)
      };
    },
    dashboard(p) {
      const ms = p.metrics;
      if (!Array.isArray(ms) || !ms.length || ms.length > 8) throw new JduiErro('dashboard.metrics 1..8');
      const metrics = ms.map(m => {
        if (!m || typeof m !== 'object' || !S(m.label, 60)) throw new JduiErro('dashboard.metric');
        return { label: S(m.label, 60), value: S(m.value, 40), hint: S(m.hint, 120) };
      });
      let chart = null;
      if (p.chart !== undefined && p.chart !== null) {
        if (typeof p.chart !== 'object') throw new JduiErro('dashboard.chart');
        chart = V.chart(p.chart);
        if (chart.series.length > 3) throw new JduiErro('dashboard.chart: máx 3 séries');
      }
      return { title: S(p.title, 160), metrics, chart, source: S(p.source, 160),
        sources: PROVENANCE(p.sources) };
    },
    compare(p) {
      const cols = p.columns;
      if (!Array.isArray(cols) || cols.length !== 2 || !S(cols[0], 40) || !S(cols[1], 40)) {
        throw new JduiErro('compare.columns: 2 rótulos');
      }
      const rs = p.rows;
      if (!Array.isArray(rs) || !rs.length || rs.length > 12) throw new JduiErro('compare.rows 1..12');
      return {
        title: S(p.title, 160),
        columns: [S(cols[0], 40), S(cols[1], 40)],
        rows: rs.map(r => {
          if (!r || typeof r !== 'object' || !S(r.label, 80)) throw new JduiErro('compare.row');
          const win = String(r.melhor || '').toLowerCase();
          if (['', 'a', 'b', '='].indexOf(win) < 0) throw new JduiErro('compare.melhor');
          return { label: S(r.label, 80), a: S(r.a, 120), b: S(r.b, 120), melhor: win };
        }),
        sources: PROVENANCE(p.sources)
      };
    },
    evidencegraph(p) {
      const ns = p.nodes;
      if (!Array.isArray(ns) || !ns.length || ns.length > 30) throw new JduiErro('evidencegraph.nodes 1..30');
      const kinds = ['claim', 'source', 'evidence'];
      const ids = {};
      const nodes = ns.map(n => {
        if (!n || typeof n !== 'object' || !S(n.id, 40)) throw new JduiErro('evidencegraph.node');
        const kind = String(n.kind || 'evidence').toLowerCase();
        if (kinds.indexOf(kind) < 0) throw new JduiErro('evidencegraph.kind');
        ids[S(n.id, 40)] = 1;
        return { id: S(n.id, 40), label: S(n.label, 80), kind, estado: S(n.estado, 40), detalhe: S(n.detalhe, 200) };
      });
      const tipos = ['SUPPORTS', 'PARTIALLY_SUPPORTS', 'CONTRADICTS', 'MENTIONS', 'DERIVED_FROM', 'DUPLICATES', 'REQUIRES_VERIFICATION'];
      const edges = [];
      (Array.isArray(p.edges) ? p.edges : []).forEach(e => {
        if (!e || typeof e !== 'object') return;
        const f = S(e.from, 40), t = S(e.to, 40), lb = String(e.label || '').toUpperCase();
        if (ids[f] && ids[t] && edges.length < 60 && tipos.indexOf(lb) >= 0) edges.push({ from: f, to: t, label: lb });
      });
      return { title: S(p.title, 160), nodes, edges };
    },
    _produto(o) {
      if (!o || typeof o !== 'object') throw new JduiErro('produto');
      let pv = o.preco_valor !== undefined && o.preco_valor !== null ? parseFloat(o.preco_valor) : null;
      if (pv !== null && !(pv > 0 && pv < 1e9)) pv = null;
      let av = o.avaliacao !== undefined && o.avaliacao !== null ? parseFloat(o.avaliacao) : null;
      if (av !== null && !(av >= 0 && av <= 5)) av = null;
      let nv = o.n_avaliacoes !== undefined && o.n_avaliacoes !== null ? parseInt(o.n_avaliacoes, 10) : null;
      if (nv !== null && !(nv >= 0 && nv < 1e7)) nv = null;
      const disp = String(o.disponibilidade || 'desconhecida').toLowerCase();
      const specs = {};
      if (o.specs && typeof o.specs === 'object' && !Array.isArray(o.specs)) {
        Object.keys(o.specs).slice(0, 12).forEach(k => {
          const v = o.specs[k];
          if (S(k, 40) && (typeof v === 'string' || typeof v === 'number')) specs[S(k, 40)] = S(v, 120);
        });
      }
      const ofertas = (Array.isArray(o.ofertas) ? o.ofertas : []).slice(0, 6).map(item => {
        if (!item || typeof item !== 'object') return null;
        return { loja: S(item.loja, 80), preco: S(item.preco, 40), url: URL_OK(item.url) };
      }).filter(Boolean);
      return {
        nome: S(o.nome || o.name, 160), marca: S(o.marca || o.brand, 80),
        modelo: S(o.modelo || o.model, 80), variante: S(o.variante, 80),
        imagem: URL_OK(o.imagem || o.image), preco: S(o.preco, 40), preco_valor: pv,
        moeda: (S(o.moeda, 3).toUpperCase() || 'BRL'), loja: S(o.loja || o.store, 80),
        url: URL_OK(o.url), specs, avaliacao: av, n_avaliacoes: nv,
        disponibilidade: ['em_estoque', 'sem_estoque', 'estoque_limitado', 'pre_venda'].indexOf(disp) >= 0 ? disp : 'desconhecida',
        verificado_em: S(o.verificado_em, 48), ofertas
      };
    },
    _produtoObrigatorio(o) {
      const prod = V._produto(o && typeof o.produto === 'object' ? o.produto : o);
      if (!prod.nome) throw new JduiErro('produto.nome obrigatório');
      return prod;
    },
    productcard(p) {
      const o = (p.produto && typeof p.produto === 'object') ? p.produto : p;
      return { produto: V._produtoObrigatorio(o), sources: PROVENANCE(p.sources) };
    },
    productgrid(p) {
      const itens = reqList(p, 'items', 1, 6, 'productgrid.items 1..6');
      return { title: S(p.title, 160), items: itens.map(V._produtoObrigatorio), sources: PROVENANCE(p.sources) };
    },
    productcompare(p) {
      const itens = reqList(p, 'items', 2, 4, 'productcompare.items 2..4');
      return { title: S(p.title, 160), items: itens.map(V._produtoObrigatorio), sources: PROVENANCE(p.sources) };
    },
    productdetails(p) {
      if (!p.produto || typeof p.produto !== 'object') throw new JduiErro('productdetails.produto');
      return { produto: V._produtoObrigatorio(p.produto), sources: PROVENANCE(p.sources) };
    },
    productgallery(p) {
      const imgs = p.imagens || p.images;
      if (!Array.isArray(imgs) || !imgs.length || imgs.length > 8) throw new JduiErro('productgallery.imagens 1..8');
      const out = imgs.map(img => {
        const u = typeof img === 'string' ? img : (img && (img.url || img.src));
        const legenda = img && typeof img === 'object' ? (img.legenda || img.caption) : '';
        const ok = URL_OK(u);
        return ok ? { url: ok, legenda: S(legenda, 120) } : null;
      }).filter(Boolean);
      if (!out.length) throw new JduiErro('productgallery sem imagem válida');
      return { title: S(p.title, 160), imagens: out, sources: PROVENANCE(p.sources) };
    }
  };

  function validateMessage(obj) {
    const erros = [];
    if (!obj || typeof obj !== 'object') return { ok: false, msg: null, erros: ['envelope'] };
    if (obj.version !== VERSION) return { ok: false, msg: null, erros: ['version'] };
    if (!Array.isArray(obj.blocks) || !obj.blocks.length) return { ok: false, msg: null, erros: ['blocks'] };
    let blocos = obj.blocks;
    if (blocos.length > 8) { erros.push('teto'); blocos = blocos.slice(0, 8); }
    const norm = [];
    blocos.forEach(b => {
      if (!b || typeof b !== 'object') { erros.push('bloco'); return; }
      if (b.type === 'text') { if (S(b.content, 4000)) norm.push({ type: 'text', content: S(b.content, 4000) }); return; }
      if (b.type === 'ui') {
        const fn = V[S(b.component, 40)];
        if (!fn) { erros.push('desconhecido:' + S(b.component, 40)); return; }
        if (!b.props || typeof b.props !== 'object') { erros.push('props'); return; }
        try { norm.push({ type: 'ui', component: S(b.component, 40), props: fn(b.props) }); }
        catch (e) { erros.push(S(b.component, 40) + ': ' + (e.message || 'inválido')); }
        return;
      }
      erros.push('type');
    });
    if (!norm.length) return { ok: false, msg: null, erros: erros.length ? erros : ['vazio'] };
    const msg = { version: VERSION, blocks: norm };
    if (obj.update_of !== undefined && obj.update_of !== null && obj.update_of !== '') {
      if (typeof obj.update_of !== 'string' || !/^[A-Za-z0-9_-]{2,100}$/.test(obj.update_of)) {
        erros.push('update_of inválido');
      } else {
        const proibidos = ['exam', 'quiz', 'studyprogress'];
        const comps = norm.filter(b => b.type === 'ui').map(b => b.component);
        const ruim = comps.filter(c => proibidos.indexOf(c) >= 0);
        if (ruim.length) erros.push(ruim[0] + ' não aceita atualização (resultado imutável)');
        else msg.update_of = obj.update_of;
      }
    }
    return { ok: true, msg, erros };
  }

  function extractBlocks(text) {
    const out = [];
    if (!text || out.length >= 6) return out;
    const re = /```jdui\s*\n([\s\S]*?)(```|$)/gi;
    let m;
    while ((m = re.exec(text)) && out.length < 6) {
      const fechado = m[0].trimEnd().endsWith('```');
      if (!fechado) continue; // stream parcial: ignora
      const corpo = (m[1] || '').trim();
      if (!corpo || corpo.length > 24000) continue;
      try {
        const r = validateMessage(JSON.parse(corpo));
        if (r.ok) out.push(r.msg);
      } catch (_) { /* inválido: fallback é o texto */ }
    }
    return out;
  }

  /* ----- Operações registradas (cálculos locais; NADA do modelo executa) ----- */
  const OPS = {
    soma(nums) { return nums.reduce((a, b) => a + b, 0); },
    porcentagem(base, perc) {
      const p = base * perc / 100;
      return { parte: p, soma: base + p, resto: base - p };
    },
    imc(peso, altura) {
      if (!(peso > 0 && altura > 0)) return null;
      const h = altura > 3 ? altura / 100 : altura; // aceita cm ou m
      const v = peso / (h * h);
      const faixa = v < 18.5 ? 'Abaixo do peso' : v < 25 ? 'Normal' : v < 30 ? 'Sobrepeso' : 'Obesidade';
      return { valor: Math.round(v * 10) / 10, faixa };
    },
    juros(capital, taxa, meses) {
      if (!(capital >= 0 && meses >= 0)) return null;
      const m = capital * Math.pow(1 + taxa / 100, meses);
      return { montante: Math.round(m * 100) / 100, juros: Math.round((m - capital) * 100) / 100 };
    },
    conversao(valor, de, para) {
      // Tabela local fixa (comprimento, massa, temperatura). Sem rede, sem eval.
      const T = {
        'km->mi': v => v * 0.621371, 'mi->km': v => v * 1.60934,
        'm->km': v => v / 1000, 'km->m': v => v * 1000,
        'kg->lb': v => v * 2.20462, 'lb->kg': v => v * 0.453592,
        'g->kg': v => v / 1000, 'kg->g': v => v * 1000,
        'C->F': v => v * 9 / 5 + 32, 'F->C': v => (v - 32) * 5 / 9,
        'min->h': v => v / 60, 'h->min': v => v * 60
      };
      if (typeof valor !== 'number' || !Number.isFinite(valor)) return null;
      if (de === para) return { valor };
      const fn = T[de + '->' + para];
      if (!fn) return null; // fora do catálogo: renderer explica a limitação
      return { valor: Math.round(fn(valor) * 10000) / 10000 };
    },
    UNIDADES: ['km', 'mi', 'm', 'kg', 'lb', 'g', 'C', 'F', 'min', 'h']
  };
  function fmt(n) {
    if (typeof n !== 'number' || !Number.isFinite(n)) return '—';
    return (Math.round(n * 100) / 100).toLocaleString('pt-BR');
  }
  // Parser seguro de expressões (basic): sem eval.
  function calcExpr(src) {
    let i = 0;
    const s = String(src).replace(/,/g, '.').replace(/[^0-9+\-*/%().\s]/g, '');
    function peek() { return s[i]; }
    function expr() { let v = termo(); while (peek() === '+' || peek() === '-') { const op = s[i++]; const r = termo(); v = op === '+' ? v + r : v - r; } return v; }
    function termo() { let v = fator(); while (peek() === '*' || peek() === '/' || peek() === '%') { const op = s[i++]; const r = fator(); v = op === '*' ? v * r : op === '/' ? v / r : v % r; } return v; }
    function fator() {
      while (s[i] === ' ') i++;
      if (s[i] === '(') { i++; const v = expr(); if (s[i] === ')') i++; return v; }
      if (s[i] === '-') { i++; return -fator(); }
      let num = '';
      while (i < s.length && /[0-9.]/.test(s[i])) num += s[i++];
      if (!num) throw new Error('expressão inválida');
      return parseFloat(num);
    }
    const v = expr();
    if (i < s.length || !Number.isFinite(v)) throw new Error('expressão inválida');
    return Math.round(v * 1e10) / 1e10;
  }

  /* ----- Síntese client-side: código/texto com cara de quiz vira interface ----- */
  function _qlimpa(s) {
    s = String(s == null ? '' : s).replace(/\\n/g, ' ').replace(/\s+/g, ' ').trim();
    s = s.replace(/^["']|["']$/g, '').trim();
    return s.slice(0, 120);
  }
  function _qIdx(letras, letra) { return letras.indexOf(String(letra || '').toLowerCase()); }
  function _qInline(t) {
    const out = [];
    const re = /\b([a-dA-D])[.)]\s*(.+?)(?=\s*\b[a-dA-D][.)]\s*|\s*$)/g;
    let m;
    while ((m = re.exec(t))) out.push([m[1].toLowerCase(), _qlimpa(m[2])]);
    return out;
  }
  function _quizMsg(qs) {
    if (!qs || !qs.length) return null;
    const r = validateMessage({
      version: VERSION,
      blocks: [{ type: 'ui', component: 'quiz', props: { title: 'Quiz interativo', questions: qs.slice(0, 6) } }]
    });
    return r.ok ? r.msg : null;
  }
  function _prints(regiao) {
    const out = [];
    let m;
    const re1 = /print\(\s*"((?:[^"\\]|\\.)*)"\s*\)/g;
    while ((m = re1.exec(regiao))) out.push(m[1]);
    if (!out.length) {
      const re2 = /print\(\s*'((?:[^'\\]|\\.)*)'\s*\)/g;
      while ((m = re2.exec(regiao))) out.push(m[1]);
    }
    return out.map(p => p.replace(/\\n/g, ' ').replace(/\\"/g, '"'));
  }
  function quizFromCode(texto) {
    const partes = String(texto || '').split(/#\s*[Pp]ergunta\s*\d+/);
    if (partes.length < 2) return null;
    const qs = [];
    for (let k = 1; k < partes.length && qs.length < 6; k++) {
      const seg = partes[k];
      const corte = seg.search(/\bresposta\s*=\s*input|\binput\s*\(|if\s+\w+\s*==/);
      const regiao = corte >= 0 ? seg.slice(0, corte) : seg;
      const lista = _prints(regiao);
      let q = '', pares = [];
      lista.forEach(p => {
        if (!q) {
          const mq = p.match(/^\s*\d+[.)]\s*([\s\S]+)/);
          const cand = _qlimpa(mq ? mq[1] : p);
          if (cand.length >= 8 && cand.indexOf('===') < 0) { q = cand; return; }
        }
        _qInline(p).forEach(pr => pares.push(pr));
      });
      if (pares.length < 2) pares = _qInline(lista.join(' '));
      const letras = pares.map(p => p[0]);
      const textos = pares.map(p => (p[1] || '').slice(0, 120)).slice(0, 6);
      const ma = seg.match(/if\s+\w+\s*==\s*["']([a-dA-D])["']/);
      const ans = ma ? _qIdx(letras, ma[1]) : -1;
      if (q && textos.length >= 2 && ans >= 0 && ans < textos.length)
        qs.push({ q: q.slice(0, 300), options: textos, answer: ans, explain: '' });
    }
    return _quizMsg(qs);
  }
  function quizFromText(texto) {
    const t = String(texto || '');
    if (!/pergunta\s*\d+/i.test(t)) return null;
    const partes = t.split(/^\s*(?:\*\*?)?\s*pergunta\s*\d+\s*[:.\-]?\s*(?:\*\*?)?/gim);
    if (partes.length < 2) return null;
    const qs = [];
    for (let k = 1; k < partes.length && qs.length < 6; k++) {
      const seg = partes[k].trim();
      if (/print\s*\(/.test(seg) && /input\s*\(/.test(seg)) continue; // é código: outro parser
      const corpo = seg.replace(/```[\s\S]*?(```|$)/g, ' ');
      let pares = [];
      corpo.split('\n').forEach(linha => {
        const m = linha.match(/^\s*([a-dA-D])[.)]\s*(.+?)\s*$/);
        if (m && _qlimpa(m[2]).length >= 1) pares.push([m[1].toLowerCase(), _qlimpa(m[2])]);
      });
      if (pares.length < 2) pares = _qInline(' ' + corpo).filter(p => p[1]).map(p => [p[0], p[1]]);
      const mq = seg.match(/\b[a-dA-D][.)]\s/);
      const qpart = (mq ? seg.slice(0, mq.index) : seg).replace(/```[\s\S]*?(```|$)/g, ' ');
      const q = _qlimpa(qpart.replace(/^[\s*#:\-–—]+/, '')).slice(0, 300);
      const letras = pares.map(p => p[0]);
      const textos = pares.map(p => p[1]).slice(0, 6);
      const m = seg.match(/(?:resposta\s*(?:certa|correta)?|certa|gabarito)\s*[:\-]?\s*\(?([a-dA-D])\)?/i);
      const ans = m ? _qIdx(letras, m[1]) : -1;
      if (q && textos.length >= 2 && ans >= 0 && ans < textos.length)
        qs.push({ q, options: textos, answer: ans, explain: '' });
    }
    if (qs.length < 2) return null; // anti-ruído: texto precisa de 2+ questões
    return _quizMsg(qs);
  }

  /* ----- Renderers ----- */
  function bar(pct) {
    const w = el('div', 'jdui-bar'); w.setAttribute('role', 'progressbar');
    const f = el('i'); f.style.width = Math.min(100, Math.max(0, pct)) + '%'; w.appendChild(f);
    return w;
  }

  const R = {};
  R.quiz = function (root, props, st, save, ctx) {
    st.answers = st.answers || {}; st.idx = st.idx || 0; st.done = !!st.done;
    const qs = props.questions;
    const box = el('div', 'jdui-quiz');
    if (props.title) box.appendChild(el('div', 'jdui-title', props.title));
    const head = el('div', 'jdui-head');
    const count = el('span', 'jdui-count'); head.appendChild(count); box.appendChild(head);
    const pg = bar(0); box.appendChild(pg);
    const area = el('div', 'jdui-area'); box.appendChild(area);
    const nav = el('div', 'jdui-nav'); box.appendChild(nav);

    function score() {
      let s = 0;
      qs.forEach((q, i) => { if (st.answers[i] === q.answer) s++; });
      return s;
    }
    function paint() {
      box.querySelectorAll('.jdui-slot-state').forEach(e => e.remove());
      if (st.done) return paintResult();
      const i = Math.min(st.idx, qs.length - 1);
      const q = qs[i];
      count.textContent = 'Pergunta ' + (i + 1) + ' de ' + qs.length + ' · ' + score() + ' acertos';
      pg.firstChild.style.width = (Object.keys(st.answers).length / qs.length * 100) + '%';
      area.replaceChildren();
      area.appendChild(el('div', 'jdui-q', q.q));
      const opts = el('div', 'jdui-opts');
      q.options.forEach((txt, oi) => {
        const lab = el('label', 'jdui-opt' + (st.answers[i] !== undefined
          ? (oi === q.answer ? ' ok' : oi === st.answers[i] ? ' bad' : '') : ''));
        const inp = document.createElement('input');
        inp.type = 'radio'; inp.name = 'jq' + i + '_' + Math.random().toString(36).slice(2, 7);
        inp.disabled = st.answers[i] !== undefined;
        inp.checked = st.answers[i] === oi;
        inp.setAttribute('aria-label', txt);
        inp.addEventListener('change', () => {
          if (st.answers[i] !== undefined) return;
          st.answers[i] = oi; save(st); paint();
        });
        lab.appendChild(inp);
        lab.appendChild(el('span', '', txt));
        opts.appendChild(lab);
      });
      area.appendChild(opts);
      if (st.answers[i] !== undefined && q.explain) {
        const ex = el('div', 'jdui-explain', (st.answers[i] === q.answer ? '✓ Correto. ' : '✗ Resposta certa: ' + q.options[q.answer] + '. ') + q.explain);
        area.appendChild(ex);
      }
      nav.replaceChildren();
      if (i > 0) {
        const b = el('button', 'jdui-btn ghost', '← Anterior');
        b.addEventListener('click', () => { st.idx = i - 1; save(st); paint(); });
        nav.appendChild(b);
      }
      if (st.answers[i] !== undefined) {
        const b = el('button', 'jdui-btn', i === qs.length - 1 ? 'Ver resultado' : 'Próxima →');
        b.addEventListener('click', () => {
          if (i === qs.length - 1) { st.done = true; } else { st.idx = i + 1; }
          save(st); paint();
        });
        nav.appendChild(b);
      }
    }
    function paintResult() {
      const s = score();
      if (!st.historico_enviado && ctx.api && (!ctx.online || ctx.online())) {
        st.historico_enviado = true;
        save(st);
        const send = ctx.queueLearn
          ? ctx.queueLearn('/api/learn/avulso', {
            titulo: props.title || 'Quiz', certas: s, total: qs.length })
          : ctx.api('/api/learn/avulso', { method: 'POST', body: JSON.stringify({
            titulo: props.title || 'Quiz', certas: s, total: qs.length }) });
        send.catch(() => {
          st.historico_enviado = false;
          try { save(st); } catch (_) {}
        });
      }
      count.textContent = 'Resultado: ' + s + '/' + qs.length;
      pg.firstChild.style.width = '100%';
      area.replaceChildren();
      const big = el('div', 'jdui-score', s + '/' + qs.length);
      area.appendChild(big);
      area.appendChild(el('div', 'jdui-q', s === qs.length ? 'Perfeito! 🎉' : s >= qs.length / 2 ? 'Bom trabalho! 💪' : 'Continue praticando! 📚'));
      const erradas = qs.map((q, i) => ({ q, i })).filter(o => st.answers[o.i] !== o.q.answer);
      if (erradas.length) {
        const ul = el('div', 'jdui-errs');
        erradas.slice(0, 6).forEach(o => ul.appendChild(el('div', 'jdui-err', 'Q' + (o.i + 1) + ': ' + o.q.q + ' → ' + o.q.options[o.q.answer])));
        area.appendChild(ul);
      }
      nav.replaceChildren();
      const r = el('button', 'jdui-btn ghost', '↻ Refazer');
      r.addEventListener('click', () => { st.answers = {}; st.idx = 0; st.done = false; save(st); paint(); });
      nav.appendChild(r);
      if (erradas.length && ctx.onChat) {
        const e = el('button', 'jdui-btn', 'Explicar meus erros');
        e.addEventListener('click', () => ctx.onChat('Explique meus erros neste quiz'
          + (props.title ? ' "' + props.title + '"' : '') + ': '
          + erradas.map(o => 'errei "' + o.q.q + '" (certa: ' + o.q.options[o.q.answer] + ')').join('; ')));
        nav.appendChild(e);
      }
    }
    paint();
    root.appendChild(box);
  };

  R.exam = function (root, props, st, save, ctx) {
    const box = el('div', 'jdui-quiz');
    box.appendChild(el('div', 'jdui-title', props.title || 'Prova'));
    const info = el('div', 'jdui-count', 'Carregando prova…');
    box.appendChild(info);
    root.appendChild(box);
    if (!ctx.api || (ctx.online && !ctx.online())) {
      info.textContent = 'Conecte-se para carregar a prova.';
      const b = el('button', 'jdui-btn ghost', 'Tentar de novo');
      b.addEventListener('click', () => { root.replaceChildren(); R.exam(root, props, st, save, ctx); });
      box.appendChild(b);
      return;
    }
    st.att = st.att || null;
    st.idx = st.idx || 0;
    st.feitas = st.feitas || {};
    let qs = [];
    let total = 0;
    async function carregar() {
      try {
        const r = await ctx.api('/api/learn/assessments/' + encodeURIComponent(props.assessment_id));
        qs = r.questions || [];
        total = qs.length;
        if (!st.att) {
          const t = await ctx.api('/api/learn/attempts', { method: 'POST', body: JSON.stringify({ assessment_id: props.assessment_id }) });
          st.att = t.id;
          save(st);
        }
        paint();
      } catch (_) {
        info.textContent = 'Não consegui carregar. Toque para tentar de novo.';
        info.style.cursor = 'pointer';
        info.addEventListener('click', carregar, { once: true });
      }
    }
    function paint() {
      box.querySelectorAll('.jdui-dyn').forEach(e => e.remove());
      const area = el('div', 'jdui-area jdui-dyn');
      const nav = el('div', 'jdui-nav jdui-dyn');
      const i = Math.min(st.idx, total - 1);
      const q = qs[i];
      if (!q) { info.textContent = 'Prova vazia.'; return; }
      info.textContent = 'Questão ' + (i + 1) + ' de ' + total;
      const pg = bar(Object.keys(st.feitas).length / total * 100);
      pg.classList.add('jdui-dyn');
      box.insertBefore(pg, area);
      area.appendChild(el('div', 'jdui-q', q.enunciado));
      if (q.tipo === 'discursiva') {
        const ta = document.createElement('textarea');
        ta.className = 'jdui-ta';
        ta.placeholder = 'Sua resposta…';
        ta.value = st.feitas[q.id] && st.feitas[q.id].texto ? st.feitas[q.id].texto : '';
        area.appendChild(ta);
        const b = el('button', 'jdui-btn', 'Enviar para avaliação');
        b.addEventListener('click', async () => {
          if (!ta.value.trim()) return;
          b.disabled = true;
          try {
            const send = ctx.queueLearn
              ? ctx.queueLearn('/api/learn/answer', { attempt_id: st.att, question_id: q.id, resposta: ta.value })
              : ctx.api('/api/learn/answer', { method: 'POST', body: JSON.stringify({ attempt_id: st.att, question_id: q.id, resposta: ta.value }) });
            await send;
            st.feitas[q.id] = { texto: ta.value, pendente: true };
            save(st); paint();
          } catch (_) { b.disabled = false; }
        });
        nav.appendChild(b);
      } else {
        const opts = el('div', 'jdui-opts');
        (q.opcoes || []).forEach((txt, oi) => {
          const feito = st.feitas[q.id];
          const lab = el('label', 'jdui-opt' + (feito ? (feito.certa ? ' ok' : (feito.certa === false ? ' bad' : '')) : ''));
          const inp = document.createElement('input');
          inp.type = 'radio';
          inp.name = 'ex' + i + '_' + props.assessment_id.slice(-4);
          inp.disabled = !!feito;
          inp.checked = feito && feito.escolha === oi;
          inp.setAttribute('aria-label', txt);
          inp.addEventListener('change', async () => {
            if (st.feitas[q.id]) return;
            lab.classList.add('wait');
            try {
              const send = ctx.queueLearn
                ? ctx.queueLearn('/api/learn/answer', { attempt_id: st.att, question_id: q.id, resposta: oi })
                : ctx.api('/api/learn/answer', { method: 'POST', body: JSON.stringify({ attempt_id: st.att, question_id: q.id, resposta: oi }) });
              const r = await send;
              st.feitas[q.id] = r && r.queued
                ? { escolha: oi, certa: null, pendente: true }
                : { escolha: oi, certa: !!r.correta };
              save(st); paint();
            } catch (_) { lab.classList.remove('wait'); }
          });
          lab.appendChild(inp);
          lab.appendChild(el('span', '', txt));
          opts.appendChild(lab);
        });
        area.appendChild(opts);
      }
      box.appendChild(area);
      if (i > 0) {
        const b = el('button', 'jdui-btn ghost', '← Anterior');
        b.addEventListener('click', () => { st.idx = i - 1; save(st); paint(); });
        nav.appendChild(b);
      }
      if (i < total - 1) {
        const b = el('button', 'jdui-btn', 'Próxima →');
        b.addEventListener('click', () => { st.idx = i + 1; save(st); paint(); });
        nav.appendChild(b);
      } else {
        const b = el('button', 'jdui-btn', 'Finalizar prova');
        b.addEventListener('click', async () => {
          b.disabled = true;
          try {
            const r = await ctx.api('/api/learn/finish', { method: 'POST', body: JSON.stringify({ attempt_id: st.att }) });
            st.fim = r;
            save(st);
            paintFim(r);
          } catch (_) { b.disabled = false; }
        });
        nav.appendChild(b);
      }
      box.appendChild(nav);
    }
    function paintFim(r) {
      box.querySelectorAll('.jdui-dyn').forEach(e => e.remove());
      info.textContent = 'Resultado: ' + r.certas + '/' + r.total;
      const area = el('div', 'jdui-area jdui-dyn');
      area.appendChild(el('div', 'jdui-score', r.certas + '/' + r.total));
      if (r.pendentes_avaliacao) area.appendChild(el('div', 'jdui-q', r.pendentes_avaliacao + ' discursiva(s) aguardando avaliação.'));
      (r.erradas || []).slice(0, 8).forEach(o => {
        area.appendChild(el('div', 'jdui-err', '✗ ' + o.enunciado + ' → certa: ' + (o.gabarito_texto || o.gabarito)));
      });
      const nav = el('div', 'jdui-nav jdui-dyn');
      const rb = el('button', 'jdui-btn ghost', '↻ Nova tentativa');
      rb.addEventListener('click', async () => {
        try {
          const t = await ctx.api('/api/learn/attempts', { method: 'POST', body: JSON.stringify({ assessment_id: props.assessment_id }) });
          st.att = t.id; st.idx = 0; st.feitas = {}; delete st.fim;
          save(st); paint();
        } catch (_) {}
      });
      nav.appendChild(rb);
      box.appendChild(area); box.appendChild(nav);
    }
    if (st.fim) {
      carregar().then(() => paintFim(st.fim));
    } else {
      carregar();
    }
  };

  R.checklist = function (root, props, st, save) {
    if (!Array.isArray(st.items)) {
      st.items = props.items.map((item, i) => ({
        label: item.label,
        checked: Array.isArray(st.checked) ? !!st.checked[i] : !!item.checked
      }));
    }
    st.items = st.items.filter(i => i && typeof i.label === 'string')
      .slice(0, 30).map(i => ({ label: i.label.slice(0, 200), checked: !!i.checked }));
    const box = el('div', 'jdui-check');
    if (props.title) box.appendChild(el('div', 'jdui-title', props.title));
    const pg = bar(0); box.appendChild(pg);
    const info = el('div', 'jdui-count'); box.appendChild(info);
    const list = el('div', 'jdui-items'); box.appendChild(list);
    const controls = el('div', 'jdui-actions');
    const newTask = document.createElement('input');
    newTask.type = 'text'; newTask.maxLength = 200; newTask.placeholder = 'Adicionar tarefa';
    newTask.setAttribute('aria-label', 'Nova tarefa');
    const add = el('button', 'jdui-btn ghost', 'Adicionar');
    add.type = 'button';
    add.addEventListener('click', () => {
      const label = String(newTask.value || '').trim().slice(0, 200);
      if (!label || st.items.length >= 30) return;
      st.items.push({ label, checked: false }); newTask.value = ''; save(st); paint();
    });
    newTask.addEventListener('keydown', e => {
      if (e.key === 'Enter') { e.preventDefault(); add.click(); }
    });
    const reset = el('button', 'jdui-btn ghost', 'Reiniciar');
    reset.type = 'button';
    reset.addEventListener('click', () => {
      st.items = props.items.map(i => ({ label: i.label, checked: !!i.checked }));
      save(st); paint();
    });
    controls.append(newTask, add, reset); box.appendChild(controls);
    function paint() {
      const n = st.items.filter(i => i.checked).length;
      pg.firstChild.style.width = (st.items.length ? n / st.items.length * 100 : 0) + '%';
      info.textContent = n + ' de ' + st.items.length + ' concluídas';
      list.replaceChildren();
      st.items.forEach((it, i) => {
        const lab = el('label', 'jdui-item' + (it.checked ? ' done' : ''));
        const c = document.createElement('input');
        c.type = 'checkbox'; c.checked = it.checked;
        c.setAttribute('aria-label', it.label);
        c.addEventListener('change', () => { st.items[i].checked = c.checked; save(st); paint(); });
        lab.appendChild(c); lab.appendChild(el('span', '', it.label));
        list.appendChild(lab);
      });
    }
    paint();
    root.appendChild(box);
  };

  R.calculator = function (root, props, st, save) {
    const box = el('div', 'jdui-calc');
    box.appendChild(el('div', 'jdui-title', props.title || 'Calculadora'));
    if (props.kind === 'conversor') {
      st.conv = st.conv || {};
      const lab = el('label', 'jdui-field', 'Valor');
      const inp = document.createElement('input');
      inp.type = 'number'; inp.inputMode = 'decimal';
      inp.value = typeof st.conv.valor === 'string' ? st.conv.valor.slice(0, 40) : '';
      inp.setAttribute('aria-label', 'Valor a converter');
      inp.addEventListener('input', () => { st.conv.valor = inp.value.slice(0, 40); save(st); });
      lab.appendChild(inp); box.appendChild(lab);
      const sels = {};
      [['de', 'De'], ['para', 'Para']].forEach(([k, titulo]) => {
        const l = el('label', 'jdui-field', titulo);
        const sel = document.createElement('select');
        OPS.UNIDADES.forEach(u => {
          const o = document.createElement('option');
          o.value = u; o.textContent = u;
          sel.appendChild(o);
        });
        sel.value = st.conv[k] || (k === 'de' ? 'km' : 'mi');
        sel.addEventListener('change', () => { st.conv[k] = sel.value; save(st); });
        l.appendChild(sel); box.appendChild(l); sels[k] = sel;
      });
      const out = el('div', 'jdui-result', st.conv.resultado || 'Escolha as unidades e toque em Converter.');
      const go = el('button', 'jdui-btn', 'Converter');
      go.addEventListener('click', () => {
        const v = parseFloat(String(inp.value).replace(',', '.'));
        const r = OPS.conversao(v, sels.de.value, sels.para.value);
        out.textContent = r
          ? fmt(v) + ' ' + sels.de.value + ' = ' + fmt(r.valor) + ' ' + sels.para.value
          : 'Conversão fora do catálogo (comprimento, massa, temperatura e tempo).';
        st.conv.resultado = out.textContent; save(st);
      });
      box.appendChild(go); box.appendChild(out);
      root.appendChild(box);
      return;
    }
    if (props.kind === 'basic') {
      const disp = el('div', 'jdui-disp', '0');
      disp.setAttribute('aria-live', 'polite');
      box.appendChild(disp);
      let cur = typeof st.expression === 'string' ? st.expression.slice(0, 120) : '';
      disp.textContent = cur || '0';
      const grid = el('div', 'jdui-grid');
      ['C', '⌫', '%', '/', '7', '8', '9', '*', '4', '5', '6', '-', '1', '2', '3', '+', '0', '.', '(', ')'].forEach(k => {
        const b = el('button', 'jdui-key' + ('/*÷-+= '.indexOf(k) >= 0 || k === 'C' ? ' op' : ''), k);
        b.type = 'button';
        b.addEventListener('click', () => {
          if (k === 'C') cur = '';
          else if (k === '⌫') cur = cur.slice(0, -1);
          else if (cur.length < 120) cur += k;
          disp.textContent = cur || '0';
          st.expression = cur; save(st);
        });
        grid.appendChild(b);
      });
      const eq = el('button', 'jdui-key eq', '=');
      eq.type = 'button';
      eq.addEventListener('click', () => {
        try { const v = calcExpr(cur); disp.textContent = fmt(v); cur = String(v); }
        catch (_) { disp.textContent = 'Erro'; cur = ''; }
        st.expression = cur; save(st);
      });
      grid.appendChild(eq);
      box.appendChild(grid);
    } else {
      const fields = {
        imc: [['peso', 'Peso (kg)', 'number'], ['altura', 'Altura (cm)', 'number']],
        porcentagem: [['base', 'Valor base', 'number'], ['perc', 'Porcentagem (%)', 'number']],
        juros: [['capital', 'Capital (R$)', 'number'], ['taxa', 'Taxa (%/mês)', 'number'], ['meses', 'Meses', 'number']]
      }[props.kind] || [];
      const inputs = {};
      fields.forEach(f => {
        const lab = el('label', 'jdui-field', f[1]);
        const inp = document.createElement('input');
        inp.type = 'number'; inp.inputMode = 'decimal'; inp.name = f[0];
        inp.value = st.values && typeof st.values[f[0]] === 'string' ? st.values[f[0]].slice(0, 40) : '';
        inp.addEventListener('input', () => {
          st.values = st.values || {}; st.values[f[0]] = inp.value.slice(0, 40); save(st);
        });
        lab.appendChild(inp); box.appendChild(lab); inputs[f[0]] = inp;
      });
      const out = el('div', 'jdui-result', st.result || 'Preencha e toque em Calcular.');
      const go = el('button', 'jdui-btn', 'Calcular');
      go.addEventListener('click', () => {
        const g = n => parseFloat(String(inputs[n] ? inputs[n].value : '').replace(',', '.'));
        let pre = 'Verifique os valores.', bold = '', pos = '';
        if (props.kind === 'imc') {
          const r = OPS.imc(g('peso'), g('altura'));
          if (r) { pre = 'IMC '; bold = fmt(r.valor); pos = ' — ' + r.faixa; }
        } else if (props.kind === 'porcentagem') {
          const b = g('base'), p = g('perc');
          if (Number.isFinite(b) && Number.isFinite(p)) {
            pre = fmt(p) + '% de ' + fmt(b) + ' = '; bold = fmt(OPS.porcentagem(b, p).parte);
          }
        } else if (props.kind === 'juros') {
          const r = OPS.juros(g('capital'), g('taxa'), g('meses'));
          if (r) { pre = 'Montante '; bold = 'R$ ' + fmt(r.montante); pos = ' (juros R$ ' + fmt(r.juros) + ')'; }
        }
        out.replaceChildren();
        out.appendChild(el('span', '', pre));
        if (bold) out.appendChild(el('strong', '', bold));
        if (pos) out.appendChild(el('span', '', pos));
        st.values = st.values || {};
        Object.keys(inputs).forEach(name => { st.values[name] = inputs[name].value.slice(0, 40); });
        st.result = out.textContent; save(st);
      });
      box.appendChild(go); box.appendChild(out);
    }
    root.appendChild(box);
  };

  R.cards = function (root, props, st, save, ctx) {
    const box = el('div', 'jdui-cards');
    if (props.title) box.appendChild(el('div', 'jdui-title', props.title));
    const grid = el('div', 'jdui-cardgrid'); box.appendChild(grid);
    props.items.forEach(c => {
      const card = el('div', 'jdui-card');
      const top = el('div', 'jdui-cardtop');
      top.appendChild(el('strong', '', c.title));
      if (c.badge) top.appendChild(el('span', 'jdui-badge', c.badge));
      card.appendChild(top);
      if (c.value) card.appendChild(el('div', 'jdui-value', c.value));
      if (c.desc) card.appendChild(el('div', 'jdui-desc', c.desc));
      const acts = el('div', 'jdui-cardacts');
      if (c.url) {
        const a = el('a', 'jdui-btn ghost', 'Abrir ↗');
        a.href = c.url; a.target = '_blank'; a.rel = 'noopener noreferrer';
        acts.appendChild(a);
      }
      if (c.action && c.action.chat && ctx.onChat) {
        const b = el('button', 'jdui-btn', 'Detalhar');
        b.addEventListener('click', () => ctx.onChat(c.action.chat));
        acts.appendChild(b);
      }
      if (acts.children.length) card.appendChild(acts);
      grid.appendChild(card);
    });
    root.appendChild(box);
  };

  R.diagram = function (root, props, st, save) {
    st = st || {};
    const box = el('div', 'jdui-diagram' + (props.direction === 'h' ? ' horiz' : ''));
    if (props.title) box.appendChild(el('div', 'jdui-title', props.title));
    const barra = el('div', 'jdui-actions');
    const menos = el('button', 'jdui-btn ghost', '−');
    const mais = el('button', 'jdui-btn ghost', '+');
    menos.type = 'button'; mais.type = 'button';
    menos.setAttribute('aria-label', 'Reduzir diagrama');
    mais.setAttribute('aria-label', 'Ampliar diagrama');
    st.zoom = Math.min(2, Math.max(0.6, parseFloat(st.zoom) || 1));
    const aplicaZoom = () => { flow.style.fontSize = (st.zoom * 100) + '%'; };
    menos.addEventListener('click', () => { st.zoom = Math.max(0.6, st.zoom - 0.2); save(st); aplicaZoom(); });
    mais.addEventListener('click', () => { st.zoom = Math.min(2, st.zoom + 0.2); save(st); aplicaZoom(); });
    barra.appendChild(menos); barra.appendChild(mais);
    box.appendChild(barra);
    const flow = el('div', 'jdui-flow'); box.appendChild(flow);
    const byId = {};
    props.nodes.forEach(n => { byId[n.id] = n; });
    let grupoAtual = null;
    props.nodes.forEach((n, i) => {
      if (n.group && n.group !== grupoAtual) {
        grupoAtual = n.group;
        flow.appendChild(el('div', 'jdui-count', grupoAtual));
      }
      const node = el('button', 'jdui-node' + (n.status ? ' st-' + n.status.replace(/[^a-z]/g, '') : '')
        + (st.sel === n.id ? ' open' : ''));
      node.type = 'button';
      node.setAttribute('aria-expanded', st.sel === n.id ? 'true' : 'false');
      node.appendChild(el('span', 'jdui-dot'));
      const tx = el('span', 'jdui-nodetx');
      tx.appendChild(el('strong', '', (n.icon ? n.icon + ' ' : '') + n.label));
      node.appendChild(tx);
      const full = n.desc || '';
      const sm = el('small', '', full ? full.slice(0, 60) + (full.length > 60 ? '…' : '') : 'Toque para detalhes');
      tx.appendChild(sm);
      node.addEventListener('click', () => {
        st.sel = st.sel === n.id ? null : n.id;
        save(st);
        const open = st.sel === n.id;
        node.classList.toggle('open', open);
        node.setAttribute('aria-expanded', open ? 'true' : 'false');
        sm.textContent = open && full ? full : (full ? full.slice(0, 60) + (full.length > 60 ? '…' : '') : 'Toque para detalhes');
      });
      flow.appendChild(node);
      if (i < props.nodes.length - 1) {
        const edge = (props.edges || []).find(e => e.from === n.id && byId[e.to]);
        const c = el('div', 'jdui-conn', (edge && edge.label ? edge.label + ' ' : '') + (props.direction === 'h' ? '→' : '↓'));
        flow.appendChild(c);
      }
    });
    aplicaZoom();
    root.appendChild(box);
  };

  R.table = function (root, props, st, save) {
    const box = el('div', 'jdui-tablewrap');
    if (props.title) box.appendChild(el('div', 'jdui-title', props.title));
    if (!Array.isArray(st.rows)) st.rows = props.rows.map(row => row.slice());
    st.rows = st.rows.slice(0, 30).map(row =>
      Array.isArray(row) ? row.slice(0, props.columns.length).map(c => String(c).slice(0, 200)) : []);
    st.editing = !!st.editing;
    const controls = el('div', 'jdui-actions');
    const edit = el('button', 'jdui-btn ghost', st.editing ? 'Concluir edição' : 'Editar tabela');
    edit.type = 'button';
    const addRow = el('button', 'jdui-btn ghost', 'Adicionar linha');
    addRow.type = 'button';
    const reset = el('button', 'jdui-btn ghost', 'Restaurar original');
    reset.type = 'button';
    const exportCsv = el('button', 'jdui-btn ghost', 'Baixar CSV');
    exportCsv.type = 'button';
    exportCsv.addEventListener('click', () => {
      if (!ctx.download) return;
      const quote = value => {
        let text = String(value == null ? '' : value);
        if (/^[=+\-@]/.test(text)) text = "'" + text;
        return '"' + text.replace(/"/g, '""') + '"';
      };
      const csv = [props.columns, ...st.rows].map(row => row.map(quote).join(',')).join('\r\n');
      const filename = (props.title || 'tabela').replace(/[^\w\- ]+/g, '').trim().slice(0, 40) || 'tabela';
      ctx.download(filename + '.csv', 'text/csv', '\uFEFF' + csv);
    });
    controls.append(edit, addRow, reset, exportCsv);
    box.appendChild(controls);
    const wrap = el('div', 'jdui-scrollx');
    const t = document.createElement('table');
    t.className = 'jdui-table';
    const thead = document.createElement('thead');
    const hr = document.createElement('tr');
    let sortCol = -1, sortAsc = true;
    const filtro = document.createElement('input');
    filtro.type = 'search'; filtro.maxLength = 80; filtro.placeholder = 'Filtrar linhas…';
    filtro.setAttribute('aria-label', 'Filtrar linhas da tabela');
    filtro.value = typeof st.filtro === 'string' ? st.filtro : '';
    filtro.addEventListener('input', () => { st.filtro = filtro.value.slice(0, 80); save(st); paint(); });
    box.appendChild(filtro);
    const tbody = document.createElement('tbody');
    function rows() {
      let rs = st.rows.map((row, index) => ({ row, index }));
      const f = (st.filtro || '').toLowerCase();
      if (f) rs = rs.filter(o => o.row.some(c => String(c).toLowerCase().indexOf(f) >= 0));
      if (sortCol >= 0) {
        rs.sort((a, b) => {
          const x = a.row[sortCol] || '', y = b.row[sortCol] || '';
          const nx = parseFloat(String(x).replace(',', '.')), ny = parseFloat(String(y).replace(',', '.'));
          const c = (!isNaN(nx) && !isNaN(ny)) ? nx - ny : String(x).localeCompare(String(y), 'pt-BR');
          return sortAsc ? c : -c;
        });
      }
      return rs;
    }
    function paint() {
      tbody.replaceChildren();
      rows().forEach(item => {
        const tr = document.createElement('tr');
        item.row.forEach((value, column) => {
          const td = document.createElement('td');
          if (st.editing) {
            const input = document.createElement('input');
            input.type = 'text'; input.maxLength = 200; input.value = value;
            input.setAttribute('aria-label', props.columns[column] + ', linha ' + (item.index + 1));
            input.addEventListener('input', () => {
              st.rows[item.index][column] = input.value.slice(0, 200); save(st);
            });
            td.appendChild(input);
          } else td.textContent = value;
          tr.appendChild(td);
        });
        if (st.editing) {
          const remove = el('button', 'jdui-btn ghost', 'Remover');
          remove.type = 'button';
          remove.addEventListener('click', () => { st.rows.splice(item.index, 1); save(st); paint(); });
          const td = document.createElement('td'); td.appendChild(remove); tr.appendChild(td);
        }
        tbody.appendChild(tr);
      });
      Array.prototype.forEach.call(hr.children, (th, i) => {
        if (i < props.columns.length) th.textContent = props.columns[i] + (i === sortCol ? (sortAsc ? ' ▲' : ' ▼') : '');
      });
      edit.textContent = st.editing ? 'Concluir edição' : 'Editar tabela';
      addRow.disabled = !st.editing || st.rows.length >= 30;
      reset.disabled = !st.editing;
      actionHead.textContent = st.editing ? 'Ações' : '';
      actionHead.hidden = !st.editing;
    }
    props.columns.forEach((c, i) => {
      const th = el('th', '', c);
      th.setAttribute('role', 'button');
      th.addEventListener('click', () => {
        if (sortCol === i) sortAsc = !sortAsc; else { sortCol = i; sortAsc = true; }
        paint();
      });
      hr.appendChild(th);
    });
    const actionHead = document.createElement('th');
    actionHead.hidden = true;
    hr.appendChild(actionHead);
    edit.addEventListener('click', () => { st.editing = !st.editing; save(st); paint(); });
    addRow.addEventListener('click', () => {
      if (!st.editing || st.rows.length >= 30) return;
      st.rows.push(props.columns.map(() => '')); save(st); paint();
    });
    reset.addEventListener('click', () => {
      if (!st.editing) return;
      st.rows = props.rows.map(row => row.slice()); save(st); paint();
    });
    thead.appendChild(hr); t.appendChild(thead); t.appendChild(tbody);
    wrap.appendChild(t); box.appendChild(wrap);
    paint();
    root.appendChild(box);
  };

  R.form = function (root, props, st, save) {
    const box = el('div', 'jdui-form');
    box.appendChild(el('div', 'jdui-title', props.title || 'Formulário'));
    const vals = {};
    st.values = st.values && typeof st.values === 'object' ? st.values : {};
    props.fields.forEach(f => {
      const lab = el('label', 'jdui-field', f.label + (f.required ? ' *' : ''));
      let inp;
      if (f.type === 'select') {
        inp = document.createElement('select');
        f.options.forEach(o => { const op = document.createElement('option'); op.value = o; op.textContent = o; inp.appendChild(op); });
      } else {
        inp = document.createElement('input');
        inp.type = f.type === 'number' ? 'number' : 'text';
        if (f.type === 'number') inp.inputMode = 'decimal';
      }
      inp.name = f.name;
      if (typeof st.values[f.name] === 'string' || typeof st.values[f.name] === 'number') {
        inp.value = String(st.values[f.name]).slice(0, 200);
      }
      const saveValue = () => { st.values[f.name] = String(inp.value || '').slice(0, 200); save(st); };
      inp.addEventListener('input', saveValue);
      inp.addEventListener('change', saveValue);
      lab.appendChild(inp); box.appendChild(lab); vals[f.name] = inp;
    });
    const out = el('div', 'jdui-result', st.result || '');
    const go = el('button', 'jdui-btn', props.submit || 'Calcular');
    function g(name) {
      const i = vals[name];
      const v = parseFloat(String(i && i.value !== undefined ? i.value : '').replace(',', '.'));
      return Number.isFinite(v) ? v : NaN;
    }
    function pick() {
      const names = Object.keys(vals).map(n => n.toLowerCase());
      const find = (...keys) => {
        for (const k of keys) { const i = names.findIndex(n => n.indexOf(k) >= 0); if (i >= 0) return Object.keys(vals)[i]; }
        return null;
      };
      return { find };
    }
    go.addEventListener('click', () => {
      for (const f of props.fields) {
        if (f.required && !String(vals[f.name].value || '').trim()) {
          out.textContent = 'Preencha "' + f.label + '".';
          vals[f.name].focus();
          return;
        }
      }
      let txt = 'Recebido! ✓';
      if (props.calc) {
        const { find } = pick();
        if (props.calc === 'soma') {
          const ns = props.fields.filter(f => f.type === 'number').map(f => g(f.name)).filter(Number.isFinite);
          txt = ns.length ? 'Soma: ' + fmt(OPS.soma(ns)) : 'Informe números.';
        } else if (props.calc === 'imc') {
          const r = OPS.imc(g(find('peso', 'massa')) || NaN, g(find('alt', 'cm', 'metro')) || NaN);
          txt = r ? 'IMC ' + fmt(r.valor) + ' — ' + r.faixa : 'Informe peso e altura.';
        } else if (props.calc === 'porcentagem') {
          const b = g(find('base', 'valor', 'total')), p = g(find('perc', 'taxa', '%'));
          txt = (Number.isFinite(b) && Number.isFinite(p))
            ? fmt(p) + '% de ' + fmt(b) + ' = ' + fmt(OPS.porcentagem(b, p).parte) : 'Informe base e %.';
        } else if (props.calc === 'juros') {
          const r = OPS.juros(g(find('cap', 'valor', 'principal')) || 0,
                              g(find('taxa', 'jur', '%')) || 0, g(find('mes', 'periodo', 'tempo')) || 0);
          txt = r ? 'Montante R$ ' + fmt(r.montante) : 'Informe os valores.';
        }
      }
      out.textContent = txt;
      st.values = st.values || {};
      Object.keys(vals).forEach(name => { st.values[name] = String(vals[name].value || '').slice(0, 200); });
      st.result = txt; save(st);
    });
    box.appendChild(go); box.appendChild(out);
    root.appendChild(box);
  };

  R.progress = function (root, props) {
    const box = el('div', 'jdui-prog');
    if (props.label) box.appendChild(el('div', 'jdui-count', props.label));
    box.appendChild(bar(props.value / (props.max || 100) * 100));
    box.appendChild(el('div', 'jdui-count', fmt(props.value) + ' / ' + fmt(props.max || 100)));
    root.appendChild(box);
  };

  R.tabs = function (root, props, st, save, ctx) {
    st.tab = st.tab || 0;
    const box = el('div', 'jdui-tabs');
    const bar = el('div', 'jdui-tabbar');
    const body = el('div', 'jdui-tabbody');
    function paint() {
      bar.replaceChildren(); body.replaceChildren();
      props.tabs.forEach((t, i) => {
        const b = el('button', 'jdui-tab' + (i === st.tab ? ' on' : ''), t.title);
        b.setAttribute('role', 'tab');
        b.setAttribute('aria-selected', i === st.tab ? 'true' : 'false');
        b.addEventListener('click', () => { st.tab = i; save(st); paint(); });
        bar.appendChild(b);
      });
      const host = el('div', 'jdui-mdhost');
      host.innerHTML = ctx.markdown ? ctx.markdown(props.tabs[Math.min(st.tab, props.tabs.length - 1)].markdown) : '';
      body.appendChild(host);
    }
    paint();
    root.appendChild(box);
  };

  R.accordion = function (root, props, st, save, ctx) {
    st.open = st.open || {};
    const box = el('div', 'jdui-acc');
    props.items.forEach((a, i) => {
      const item = el('div', 'jdui-accitem');
      const b = el('button', 'jdui-accbtn', a.title);
      b.setAttribute('aria-expanded', st.open[i] ? 'true' : 'false');
      const body = el('div', 'jdui-accbody');
      if (!st.open[i]) body.hidden = true;
      else if (ctx.markdown) body.innerHTML = ctx.markdown(a.markdown);
      b.addEventListener('click', () => {
        st.open[i] = !st.open[i]; save(st);
        body.hidden = !st.open[i];
        b.setAttribute('aria-expanded', st.open[i] ? 'true' : 'false');
        if (st.open[i] && ctx.markdown && !body.innerHTML) body.innerHTML = ctx.markdown(a.markdown);
      });
      item.appendChild(b); item.appendChild(body); box.appendChild(item);
    });
    root.appendChild(box);
  };

  function precisaConexao(ctx) {
    return !ctx.api || (ctx.online && !ctx.online());
  }
  function botaoTentar(root, info, recarregar) {
    const b = el('button', 'jdui-btn ghost', 'Tentar de novo');
    b.type = 'button';
    b.addEventListener('click', () => { root.replaceChildren(); recarregar(); });
    root.appendChild(b);
  }

  R.studyplan = function (root, props, st, save, ctx) {
    const box = el('div', 'jdui-quiz');
    const info = el('div', 'jdui-count', 'Carregando plano…');
    box.appendChild(info);
    root.appendChild(box);
    function montar() {
      const b2 = el('div', 'jdui-quiz');
      const i2 = el('div', 'jdui-count', 'Carregando plano…');
      b2.appendChild(i2);
      root.replaceChildren(b2);
      carregar(b2, i2);
    }
    if (precisaConexao(ctx)) {
      info.textContent = 'Conecte-se para ver o plano.';
      botaoTentar(root, info, montar);
      return;
    }
    carregar(box, info);
    async function carregar(bx, inf) {
      let plano;
      try {
        plano = await ctx.api('/api/learn/plans/' + encodeURIComponent(props.plan_id));
      } catch (_) {
        inf.textContent = 'Não consegui carregar. Toque para tentar de novo.';
        inf.style.cursor = 'pointer';
        inf.addEventListener('click', montar, { once: true });
        return;
      }
      const itens = plano.itens || [];
      const feitos = itens.filter(i => i.feito).length;
      bx.replaceChildren();
      bx.appendChild(el('div', 'jdui-title', plano.titulo || 'Plano de estudos'));
      bx.appendChild(el('div', 'jdui-count', 'Progresso: ' + feitos + '/' + itens.length));
      bx.appendChild(bar(itens.length ? feitos / itens.length * 100 : 0));
      const list = el('div', 'jdui-items');
      itens.forEach(it => {
        const lab = el('label', 'jdui-opt' + (it.feito ? ' ok' : ''));
        const inp = document.createElement('input');
        inp.type = 'checkbox';
        inp.checked = !!it.feito;
        inp.setAttribute('aria-label', it.titulo);
        inp.addEventListener('change', async () => {
          inp.disabled = true;
          try {
            await ctx.api('/api/learn/plans/item', {
              method: 'POST',
              body: JSON.stringify({ plan_id: props.plan_id, item_id: it.id, feito: inp.checked })
            });
            it.feito = inp.checked;
            lab.classList.toggle('ok', inp.checked);
            const f2 = itens.filter(x => x.feito).length;
            bx.querySelector('.jdui-count').textContent = 'Progresso: ' + f2 + '/' + itens.length;
            const pg = bx.querySelector('.jdui-bar');
            if (pg && pg.firstChild) pg.firstChild.style.width = (itens.length ? f2 / itens.length * 100 : 0) + '%';
          } catch (_) { inp.checked = it.feito; }
          inp.disabled = false;
        });
        lab.appendChild(inp);
        lab.appendChild(el('span', '', it.titulo));
        list.appendChild(lab);
      });
      bx.appendChild(list);
    }
  };

  R.flashcards = function (root, props, st, save, ctx) {
    const box = el('div', 'jdui-quiz');
    const info = el('div', 'jdui-count', 'Carregando cartões…');
    box.appendChild(info);
    root.appendChild(box);
    function montar() {
      const b2 = el('div', 'jdui-quiz');
      const i2 = el('div', 'jdui-count', 'Carregando cartões…');
      b2.appendChild(i2);
      root.replaceChildren(b2);
      carregar(b2, i2);
    }
    if (precisaConexao(ctx)) {
      info.textContent = 'Conecte-se para revisar os cartões.';
      botaoTentar(root, info, montar);
      return;
    }
    carregar(box, info);
    async function carregar(bx, inf) {
      let todos;
      try {
        const r = await ctx.api('/api/learn/cards/due?limite=50');
        todos = (r.cards || []).filter(c => !props.assunto || c.assunto === props.assunto);
      } catch (_) {
        inf.textContent = 'Não consegui carregar. Toque para tentar de novo.';
        inf.style.cursor = 'pointer';
        inf.addEventListener('click', montar, { once: true });
        return;
      }
      let i = 0;
      let virado = false;
      paint();
      function paint() {
        bx.replaceChildren();
        if (i >= todos.length) {
          bx.appendChild(el('div', 'jdui-title', 'Revisão em dia 🎉'));
          bx.appendChild(el('div', 'jdui-q', 'Nenhum cartão vencendo. Volte amanhã.'));
          return;
        }
        const c = todos[i];
        bx.appendChild(el('div', 'jdui-title', 'Cartão ' + (i + 1) + ' de ' + todos.length));
        if (c.assunto) bx.appendChild(el('div', 'jdui-count', c.assunto));
        bx.appendChild(el('div', 'jdui-q', virado ? c.verso : c.frente));
        const nav = el('div', 'jdui-nav');
        if (!virado) {
          const b = el('button', 'jdui-btn', 'Mostrar resposta');
          b.addEventListener('click', () => { virado = true; paint(); });
          nav.appendChild(b);
        } else {
          const ok = el('button', 'jdui-btn', 'Acertei ✓');
          ok.addEventListener('click', () => avaliar(true));
          const no = el('button', 'jdui-btn ghost', 'Errei ✗');
          no.addEventListener('click', () => avaliar(false));
          nav.appendChild(ok); nav.appendChild(no);
        }
        bx.appendChild(nav);
      }
      async function avaliar(acertou) {
        try {
          await ctx.api('/api/learn/cards/review', {
            method: 'POST',
            body: JSON.stringify({ flashcard_id: todos[i].id, acertou })
          });
        } catch (_) { /* segue local mesmo offline de escrita: o cartão volta ao recarregar */ }
        i += 1; virado = false; paint();
      }
    }
  };

  R.studyprogress = function (root, props, st, save, ctx) {
    const box = el('div', 'jdui-quiz');
    const info = el('div', 'jdui-count', 'Carregando progresso…');
    box.appendChild(el('div', 'jdui-title', 'Meu progresso 📊'));
    box.appendChild(info);
    root.appendChild(box);
    function montar() {
      const b2 = el('div', 'jdui-quiz');
      b2.appendChild(el('div', 'jdui-title', 'Meu progresso 📊'));
      const i2 = el('div', 'jdui-count', 'Carregando progresso…');
      b2.appendChild(i2);
      root.replaceChildren(b2);
      carregar(b2, i2);
    }
    if (precisaConexao(ctx)) {
      info.textContent = 'Conecte-se para ver o progresso.';
      botaoTentar(root, info, montar);
      return;
    }
    carregar(box, info);
    async function carregar(bx, inf) {
      let stats, rec;
      try {
        stats = await ctx.api('/api/learn/stats');
        try { rec = await ctx.api('/api/learn/recommend'); } catch (_) { rec = null; }
      } catch (_) {
        inf.textContent = 'Não consegui carregar. Toque para tentar de novo.';
        inf.style.cursor = 'pointer';
        inf.addEventListener('click', montar, { once: true });
        return;
      }
      const r = stats.resumo || {};
      bx.replaceChildren();
      bx.appendChild(el('div', 'jdui-title', 'Meu progresso 📊'));
      if (!r.concluidas && !r.itens_feitos && !(stats.por_assunto || []).length) {
        bx.appendChild(el('div', 'jdui-q', 'Sem dados ainda — faça um quiz para começar. 📚'));
        return;
      }
      const linhas = [
        ['Provas concluídas', r.concluidas || 0, r.avaliacoes || 0],
        ['Acertos', r.acertos || 0, r.respostas || 0],
        ['Itens do plano', r.itens_feitos || 0, r.itens_plano || 0]
      ];
      linhas.forEach(l => {
        bx.appendChild(el('div', 'jdui-count', l[0] + ': ' + (l[2] ? l[1] + '/' + l[2] : 'Sem dados ainda')));
        if (l[2]) bx.appendChild(bar(l[1] / l[2] * 100));
      });
      (stats.por_assunto || []).forEach(p => {
        bx.appendChild(el('div', 'jdui-count', (p.assunto || 'geral') + ': ' + Math.round((p.taxa || 0) * 100) + '%'));
        bx.appendChild(bar((p.taxa || 0) * 100));
      });
      if (r.revisoes_pendentes) {
        bx.appendChild(el('div', 'jdui-q', (r.revisoes_pendentes || 0) + ' cartão(ões) vencendo — revise hoje.'));
      }
      ((rec && rec.recomendacoes) || []).forEach(x => {
        bx.appendChild(el('div', 'jdui-err', '→ ' + (x.detalhe || x.tipo)));
      });
    }
  };

  /* ----- V4.3: gráficos SVG puros (sem libs, sem eval, dados validados) ----- */
  const PALETA = ['#a78bfa', '#7c6cf0', '#5b5bd6', '#c4b5fd', '#8b7cf6', '#6d6df2'];
  function svgEl(tag, attrs) {
    const e = document.createElementNS('http://www.w3.org/2000/svg', tag);
    for (const k in attrs) e.setAttribute(k, attrs[k]);
    return e;
  }
  function svgText(x, y, s, anchor, size) {
    const t = svgEl('text', { x, y, 'text-anchor': anchor || 'middle', 'font-size': size || 9, fill: 'currentColor', opacity: '.75' });
    t.textContent = String(s);
    return t;
  }
  function fmtTick(v) {
    if (typeof v !== 'number' || !Number.isFinite(v)) return '—';
    const a = Math.abs(v);
    if (a >= 1e9) return (v / 1e9).toLocaleString('pt-BR', { maximumFractionDigits: 1 }) + 'B';
    if (a >= 1e6) return (v / 1e6).toLocaleString('pt-BR', { maximumFractionDigits: 1 }) + 'M';
    if (a >= 1e3) return (v / 1e3).toLocaleString('pt-BR', { maximumFractionDigits: 1 }) + 'k';
    return (Math.round(v * 100) / 100).toLocaleString('pt-BR');
  }
  function dica(elm, texto) {
    const t = svgEl('title', {});
    t.textContent = texto;
    elm.appendChild(t);
    return elm;
  }

  R.chart = function (root, props) {
    const box = el('div', 'jdui-quiz');
    if (props.title) box.appendChild(el('div', 'jdui-title', props.title));
    const series = props.series || [];
    if (!series.length || !series[0].values.length) {
      box.appendChild(el('div', 'jdui-q', 'Sem dados para o gráfico.'));
      root.appendChild(box);
      return;
    }
    const W = 360, H = 220, P = { l: 40, r: 8, t: 10, b: 34 };
    const svg = svgEl('svg', { viewBox: '0 0 ' + W + ' ' + H, role: 'img', 'aria-label': props.title || 'Gráfico' });
    const holder = el('div', 'jdui-chart');
    holder.appendChild(svg);
    box.appendChild(holder);
    const leg = el('div', 'jdui-legend');
    series.forEach((s, i) => {
      const sp = el('span', '', s.label || ('Série ' + (i + 1)));
      const dot = el('i', '');
      dot.style.background = PALETA[i % PALETA.length];
      sp.insertBefore(dot, sp.firstChild);
      leg.appendChild(sp);
    });
    box.appendChild(leg);
    if (props.type === 'pie') {
      const vals = series[0].values;
      const total = vals.reduce((a, b) => a + b, 0) || 1;
      const cx = W / 2, cy = H / 2 - 6, R0 = 62, R1 = 88;
      let ang = -Math.PI / 2;
      vals.forEach((v, i) => {
        const frac = Math.max(v, 0) / total;
        const a2 = ang + frac * Math.PI * 2;
        const grande = frac > 0.5 ? 1 : 0;
        const x1 = cx + R1 * Math.cos(ang), y1 = cy + R1 * Math.sin(ang);
        const x2 = cx + R1 * Math.cos(a2), y2 = cy + R1 * Math.sin(a2);
        const x3 = cx + R0 * Math.cos(a2), y3 = cy + R0 * Math.sin(a2);
        const x4 = cx + R0 * Math.cos(ang), y4 = cy + R0 * Math.sin(ang);
        const fatia = dica(svgEl('path', {
          d: 'M' + x1 + ',' + y1 + ' A' + R1 + ',' + R1 + ' 0 ' + grande + ' 1 ' + x2 + ',' + y2 +
            ' L' + x3 + ',' + y3 + ' A' + R0 + ',' + R0 + ' 0 ' + grande + ' 0 ' + x4 + ',' + y4 + ' Z',
          fill: PALETA[i % PALETA.length], opacity: '.9'
        }), (props.labels[i] || ('Item ' + (i + 1))) + ': ' + fmtTick(v) + ' (' + Math.round(frac * 100) + '%)');
        svg.appendChild(fatia);
        if (frac >= 0.08) svg.appendChild(svgText(cx + 76 * Math.cos((ang + a2) / 2), cy + 76 * Math.sin((ang + a2) / 2), Math.round(frac * 100) + '%', 'middle', 9));
        ang = a2;
      });
    } else {
      let xs, ys, cartesiano = props.type !== 'scatter';
      if (cartesiano) {
        const n = series[0].values.length;
        xs = series.map((s, i) => s.values.map((_, j) => j));
        let mn = Infinity, mx = -Infinity;
        series.forEach(s => s.values.forEach(v => { if (v < mn) mn = v; if (v > mx) mx = v; }));
        if (mn === mx) { mn -= 1; mx += 1; }
        if (mn > 0) mn = 0;
        ys = { mn, mx, n };
      } else {
        let x0 = Infinity, x1 = -Infinity, y0 = Infinity, y1 = -Infinity;
        series.forEach(s => s.values.forEach(p => {
          if (p[0] < x0) x0 = p[0]; if (p[0] > x1) x1 = p[0];
          if (p[1] < y0) y0 = p[1]; if (p[1] > y1) y1 = p[1];
        }));
        if (x0 === x1) { x0 -= 1; x1 += 1; }
        if (y0 === y1) { y0 -= 1; y1 += 1; }
        ys = { mn: y0, mx: y1 };
        xs = { mn: x0, mx: x1 };
      }
      const X = v => P.l + (v - (cartesiano ? 0 : xs.mn)) / ((cartesiano ? ys.n - 1 : xs.mx - xs.mn) || 1) * (W - P.l - P.r);
      const Y = v => P.t + (1 - (v - ys.mn) / ((ys.mx - ys.mn) || 1)) * (H - P.t - P.b);
      for (let g = 0; g <= 3; g++) {
        const v = ys.mn + (ys.mx - ys.mn) * g / 3;
        svg.appendChild(svgEl('line', { x1: P.l, y1: Y(v), x2: W - P.r, y2: Y(v), stroke: 'currentColor', opacity: '.15' }));
        svg.appendChild(svgText(P.l - 4, Y(v) + 3, fmtTick(v), 'end', 9));
      }
      const rotulos = props.labels || [];
      const n = cartesiano ? series[0].values.length : 0;
      if (cartesiano) {
        for (let j = 0; j < n; j++) {
          if (rotulos[j]) svg.appendChild(svgText(X(j), H - 8, String(rotulos[j]).slice(0, 10), 'middle', 9));
        }
      }
      if (props.type === 'bar') {
        const grupo = (W - P.l - P.r) / n;
        const larg = Math.min(grupo / (series.length + 1), 26);
        series.forEach((s, i) => {
          s.values.forEach((v, j) => {
            const x = X(j) - grupo / 2 + i * larg + (grupo - series.length * larg) / 2;
            const barra = dica(svgEl('rect', {
              x, y: Math.min(Y(v), Y(0)), width: larg, height: Math.abs(Y(v) - Y(0)),
              rx: 2, fill: PALETA[i % PALETA.length], opacity: '.9'
            }), (s.label ? s.label + ': ' : '') + fmtTick(v) + (rotulos[j] ? ' (' + rotulos[j] + ')' : ''));
            svg.appendChild(barra);
          });
        });
      } else {
        series.forEach((s, i) => {
          const pts = cartesiano ? s.values.map((v, j) => [X(j), Y(v)]) : s.values.map(p => [X(p[0]), Y(p[1])]);
          const cor = PALETA[i % PALETA.length];
          if (props.type === 'area' && cartesiano) {
            svg.appendChild(svgEl('path', {
              d: 'M' + pts.map(p => p[0].toFixed(1) + ',' + p[1].toFixed(1)).join(' L') +
                ' L' + pts[pts.length - 1][0].toFixed(1) + ',' + Y(0).toFixed(1) +
                ' L' + pts[0][0].toFixed(1) + ',' + Y(0).toFixed(1) + ' Z',
              fill: cor, opacity: '.22'
            }));
          }
          if (props.type !== 'scatter') {
            svg.appendChild(svgEl('polyline', {
              points: pts.map(p => p[0].toFixed(1) + ',' + p[1].toFixed(1)).join(' '),
              fill: 'none', stroke: cor, 'stroke-width': 2
            }));
          }
          pts.forEach((p, j) => {
            const c = dica(svgEl('circle', { cx: p[0], cy: p[1], r: props.type === 'scatter' ? 4 : 3, fill: cor }), (s.label ? s.label + ': ' : '') + fmtTick(cartesiano ? s.values[j] : s.values[j][1]));
            svg.appendChild(c);
          });
        });
      }
      if (props.y_label) svg.appendChild(svgText(8, P.t + 4, String(props.y_label).slice(0, 12), 'start', 9));
      if (props.x_label) svg.appendChild(svgText(W - P.r, H - 8, String(props.x_label).slice(0, 12), 'end', 9));
    }
    if (props.source) box.appendChild(el('div', 'jdui-source', 'Fonte: ' + props.source));
    renderProvenance(box, props.sources);
    root.appendChild(box);
  };

  R.dashboard = function (root, props) {
    const box = el('div', 'jdui-quiz');
    if (props.title) box.appendChild(el('div', 'jdui-title', props.title));
    const grid = el('div', 'jdui-dashgrid');
    props.metrics.forEach(m => {
      const card = el('div', 'jdui-metric');
      card.appendChild(el('span', '', m.label));
      card.appendChild(el('strong', '', m.value || '—'));
      if (m.hint) card.appendChild(el('small', '', m.hint));
      grid.appendChild(card);
    });
    box.appendChild(grid);
    if (props.chart) R.chart(box, props.chart);
    if (props.source) box.appendChild(el('div', 'jdui-source', 'Fonte: ' + props.source));
    renderProvenance(box, props.sources);
    root.appendChild(box);
  };

  R.compare = function (root, props) {
    const box = el('div', 'jdui-quiz');
    if (props.title) box.appendChild(el('div', 'jdui-title', props.title));
    const holder = el('div', 'jdui-chart');
    const t = document.createElement('table');
    t.className = 'jdui-cmp';
    const head = document.createElement('tr');
    head.appendChild(el('th', '', ''));
    props.columns.forEach(c => head.appendChild(el('th', '', c)));
    t.appendChild(head);
    props.rows.forEach(r => {
      const tr = document.createElement('tr');
      tr.appendChild(el('th', '', r.label));
      const ca = el('td', r.melhor === 'a' ? 'win' : '', r.a || '—');
      const cb = el('td', r.melhor === 'b' ? 'win' : '', r.b || '—');
      if (r.melhor === 'a') ca.setAttribute('aria-label', r.a + ' (destaque)');
      if (r.melhor === 'b') cb.setAttribute('aria-label', r.b + ' (destaque)');
      tr.appendChild(ca); tr.appendChild(cb);
      t.appendChild(tr);
    });
    holder.appendChild(t);
    box.appendChild(holder);
    renderProvenance(box, props.sources);
    root.appendChild(box);
  };

  R.evidencegraph = function (root, props, st, save) {
    st.zoom = Math.min(2, Math.max(0.6, parseFloat(st.zoom) || 1));
    st.filtro = st.filtro || 'all';
    st.sel = st.sel || null;
    const box = el('div', 'jdui-quiz');
    if (props.title) box.appendChild(el('div', 'jdui-title', props.title));
    const barra = el('div', 'jdui-actions');
    const menos = el('button', 'jdui-btn ghost', '−');
    const mais = el('button', 'jdui-btn ghost', '+');
    menos.type = 'button'; mais.type = 'button';
    menos.setAttribute('aria-label', 'Reduzir grafo');
    mais.setAttribute('aria-label', 'Ampliar grafo');
    menos.addEventListener('click', () => { st.zoom = Math.max(0.6, st.zoom - 0.2); save(st); paint(); });
    mais.addEventListener('click', () => { st.zoom = Math.min(2, st.zoom + 0.2); save(st); paint(); });
    barra.appendChild(menos); barra.appendChild(mais);
    ['all', 'claim', 'source', 'evidence'].forEach(k => {
      const f = el('button', 'jdui-btn ghost', {all:'Tudo',claim:'Afirmações',source:'Fontes',evidence:'Evidências'}[k]);
      f.type = 'button';
      f.dataset.filter = k;
      f.setAttribute('aria-pressed', String(st.filtro === k));
      f.addEventListener('click', () => {
        st.filtro = k; st.sel = null; save(st);
        barra.querySelectorAll('[data-filter]').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.filter === k)));
        detalhe.textContent = 'Toque em um nó para ver detalhes.';
        paint();
      });
      barra.appendChild(f);
    });
    box.appendChild(barra);
    const host = el('div', 'jdui-chart');
    box.appendChild(host);
    const detalhe = el('div', 'jdui-q', 'Toque em um nó para ver detalhes.');
    box.appendChild(detalhe);
    const CORES = { claim: '#a78bfa', source: '#5b5bd6', evidence: '#34d399' };
    const camadas = { claim: 0, evidence: 1, source: 2 };
    function visiveis() {
      return props.nodes.filter(n => st.filtro === 'all' || n.kind === st.filtro);
    }
    function paint() {
      host.replaceChildren();
      const nos = visiveis().slice(0, 30);
      const ids = {};
      nos.forEach(n => { ids[n.id] = 1; });
      const W = 360, H = Math.max(140, 40 + 3 * 56);
      const svg = svgEl('svg', { viewBox: '0 0 ' + W + ' ' + H, role: 'group', 'aria-label': props.title || 'Grafo de evidências' });
      const porCamada = [[], [], []];
      nos.forEach(n => porCamada[camadas[n.kind]].push(n));
      const pos = {};
      porCamada.forEach((grupo, c) => {
        grupo.forEach((n, i) => {
          pos[n.id] = [(i + 1) * (W / (grupo.length + 1)), 34 + c * 56];
        });
      });
      (props.edges || []).forEach(e => {
        if (!pos[e.from] || !pos[e.to]) return;
        const cor = e.label === 'CONTRADICTS' ? '#f87171' : e.label === 'SUPPORTS' ? '#34d399' : 'currentColor';
        const ln = dica(svgEl('line', {
          x1: pos[e.from][0], y1: pos[e.from][1], x2: pos[e.to][0], y2: pos[e.to][1],
          stroke: cor, 'stroke-width': e.label === 'CONTRADICTS' ? 2 : 1, opacity: '.6'
        }), e.label);
        svg.appendChild(ln);
      });
      nos.forEach(n => {
        const g = svgEl('g', { style: 'cursor:pointer', 'aria-label': n.label,
          role: 'button', tabindex: '0', 'aria-pressed': String(st.sel === n.id) });
        const c = dica(svgEl('circle', {
          cx: pos[n.id][0], cy: pos[n.id][1], r: st.sel === n.id ? 13 : 10,
          fill: CORES[n.kind] || '#888', opacity: st.sel === n.id ? '1' : '.85'
        }), n.kind + ': ' + n.label + (n.estado ? ' (' + n.estado + ')' : ''));
        g.appendChild(c);
        const tx = svgText(pos[n.id][0], pos[n.id][1] + 24, (n.label || '').slice(0, 14), 'middle', 9);
        g.appendChild(tx);
        const selectNode = () => {
          st.sel = st.sel === n.id ? null : n.id; save(st); paint();
          detalhe.textContent = st.sel
            ? (n.kind + ' · ' + n.label + (n.estado ? ' · ' + n.estado : '') + (n.detalhe ? ' — ' + n.detalhe : ''))
            : 'Toque em um nó para ver detalhes.';
        };
        g.addEventListener('click', selectNode);
        g.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); selectNode(); } });
        svg.appendChild(g);
      });
      svg.setAttribute('viewBox', [W * (1 - 1 / st.zoom) / 2, H * (1 - 1 / st.zoom) / 2, W / st.zoom, H / st.zoom].join(' '));
      host.appendChild(svg);
    }
    paint();
    root.appendChild(box);
  };

  /* ----- Produtos (V4.9.1 Shopping Intelligence; só dados verificados) ----- */
  const DISP_LABEL = {
    em_estoque: 'Em estoque', sem_estoque: 'Sem estoque',
    estoque_limitado: 'Estoque limitado', pre_venda: 'Pré-venda',
    desconhecida: 'Disponibilidade não informada'
  };
  function productImg(url, alt) {
    if (url) {
      const img = document.createElement('img');
      img.className = 'jdui-pimg';
      img.src = url;
      img.alt = alt || 'Foto do produto';
      img.loading = 'lazy';
      img.referrerPolicy = 'no-referrer';
      img.addEventListener('error', () => {
        const ph = el('div', 'jdui-pimg ph', 'Sem foto');
        if (img.parentNode) img.parentNode.replaceChild(ph, img);
      });
      img.addEventListener('click', () => abrirLightbox(url, alt));
      return img;
    }
    return el('div', 'jdui-pimg ph', 'Sem foto');
  }
  function abrirLightbox(url, alt) {
    try {
      const ov = el('div', 'jdui-lightbox');
      ov.setAttribute('role', 'dialog');
      ov.setAttribute('aria-label', alt || 'Foto ampliada');
      const img = document.createElement('img');
      img.src = url; img.alt = alt || 'Foto ampliada';
      img.referrerPolicy = 'no-referrer';
      const fechar = el('button', 'jdui-btn', 'Fechar');
      fechar.type = 'button';
      ov.appendChild(img); ov.appendChild(fechar);
      const sair = () => { if (ov.parentNode) ov.parentNode.removeChild(ov); };
      fechar.addEventListener('click', ev => { ev.stopPropagation(); sair(); });
      ov.addEventListener('click', sair);
      document.body.appendChild(ov);
    } catch (_) { /* sem lightbox: a imagem continua visível no card */ }
  }
  function productStars(av, n) {
    if (av === null || av === undefined) return 'Avaliação não informada';
    const cheias = Math.round(av);
    return '★'.repeat(Math.min(5, cheias)) + '☆'.repeat(Math.max(0, 5 - Math.min(5, cheias))) +
      ' ' + Number(av).toFixed(1) + (n ? ' (' + n + ')' : '');
  }
  function productSpecsChips(box, specs, teto) {
    const keys = Object.keys(specs || {}).slice(0, teto || 4);
    if (!keys.length) return;
    const wrap = el('div', 'jdui-pchips');
    keys.forEach(k => wrap.appendChild(el('span', 'jdui-pchip', k + ': ' + specs[k])));
    box.appendChild(wrap);
  }
  function productCardEl(prod, ctx, mini) {
    const card = el('div', 'jdui-pcard' + (mini ? ' mini' : ''));
    const moldura = el('div', 'jdui-pmedia');
    moldura.appendChild(productImg(prod.imagem, prod.nome));
    card.appendChild(moldura);
    const corpo = el('div', 'jdui-pbody');
    corpo.appendChild(el('strong', 'jdui-pnome', prod.nome));
    const marca = [prod.marca, prod.modelo].filter(Boolean).join(' · ');
    if (marca) corpo.appendChild(el('div', 'jdui-pmarca', marca));
    corpo.appendChild(el('div', 'jdui-ppreco', prod.preco || 'Preço não confirmado'));
    const loja = prod.loja + (prod.verificado_em ? ' · verificado em ' + prod.verificado_em : '');
    if (prod.loja || prod.verificado_em) corpo.appendChild(el('div', 'jdui-ploja', loja));
    corpo.appendChild(el('div', 'jdui-paval', productStars(prod.avaliacao, prod.n_avaliacoes)));
    corpo.appendChild(el('span', 'jdui-pdisp ' + (prod.disponibilidade || 'desconhecida'),
      DISP_LABEL[prod.disponibilidade] || DISP_LABEL.desconhecida));
    if (!mini) productSpecsChips(corpo, prod.specs, 4);
    const acts = el('div', 'jdui-cardacts');
    if (prod.url) {
      const a = el('a', 'jdui-btn', 'Abrir oferta ↗');
      a.href = prod.url; a.target = '_blank'; a.rel = 'noopener noreferrer';
      acts.appendChild(a);
    }
    if (ctx && ctx.onChat) {
      const cmp = el('button', 'jdui-btn ghost', 'Comparar');
      cmp.type = 'button';
      cmp.addEventListener('click', () => ctx.onChat('Compare ' + prod.nome + ' com as outras opções'));
      acts.appendChild(cmp);
    }
    if (acts.children.length) corpo.appendChild(acts);
    card.appendChild(corpo);
    card._corpo = corpo;
    return card;
  }
  function productSpecsTable(prod) {
    const keys = Object.keys(prod.specs || {});
    if (!keys.length) return null;
    const holder = el('div', 'jdui-scrollx');
    const t = document.createElement('table');
    t.className = 'jdui-table';
    keys.forEach(k => {
      const tr = document.createElement('tr');
      tr.appendChild(el('th', '', k));
      tr.appendChild(el('td', '', prod.specs[k]));
      t.appendChild(tr);
    });
    holder.appendChild(t);
    return holder;
  }
  function productOfertas(box, prod) {
    if (!Array.isArray(prod.ofertas) || !prod.ofertas.length) return;
    const det = el('div', 'jdui-pchips');
    det.appendChild(el('span', '', 'Outras lojas:'));
    prod.ofertas.slice(0, 6).forEach(o => {
      if (o.url) {
        const a = el('a', 'jdui-pchip link', (o.loja || 'Loja') + ' · ' + (o.preco || 'preço não confirmado'));
        a.href = o.url; a.target = '_blank'; a.rel = 'noopener noreferrer';
        det.appendChild(a);
      } else {
        det.appendChild(el('span', 'jdui-pchip', (o.loja || 'Loja') + ' · ' + (o.preco || 'preço não confirmado')));
      }
    });
    box.appendChild(det);
  }

  R.productcard = function (root, props, st, save, ctx) {
    st = st || {};
    const box = el('div', 'jdui-cards');
    const card = productCardEl(props.produto, ctx, false);
    box.appendChild(card);
    const corpo = card._corpo;
    const specsFull = productSpecsTable(props.produto);
    if (specsFull) {
      specsFull.style.display = st.detalhes ? '' : 'none';
      corpo.appendChild(specsFull);
      const tgl = el('button', 'jdui-btn ghost', st.detalhes ? 'Ocultar especificações' : 'Ver especificações');
      tgl.type = 'button';
      tgl.addEventListener('click', () => {
        st.detalhes = !st.detalhes; save(st);
        specsFull.style.display = st.detalhes ? '' : 'none';
        tgl.textContent = st.detalhes ? 'Ocultar especificações' : 'Ver especificações';
      });
      corpo.appendChild(tgl);
    }
    productOfertas(corpo, props.produto);
    renderProvenance(box, props.sources);
    root.appendChild(box);
  };

  R.productgrid = function (root, props, st, save, ctx) {
    const box = el('div', 'jdui-cards');
    if (props.title) box.appendChild(el('div', 'jdui-title', props.title));
    st.ordem = st.ordem || 'preco';
    const barra = el('div', 'jdui-actions');
    const rotulo = el('span', '', 'Ordenar:');
    barra.appendChild(rotulo);
    const sel = document.createElement('select');
    sel.className = 'jdui-btn ghost';
    sel.setAttribute('aria-label', 'Ordenar produtos');
    [['preco', 'Menor preço'], ['avaliacao', 'Melhor avaliação'], ['nome', 'Nome A–Z']].forEach(([v, lb]) => {
      const op = document.createElement('option');
      op.value = v; op.textContent = lb;
      if (st.ordem === v) op.selected = true;
      sel.appendChild(op);
    });
    barra.appendChild(sel);
    box.appendChild(barra);
    const grid = el('div', 'jdui-cardgrid');
    box.appendChild(grid);
    function pinta() {
      grid.replaceChildren();
      const itens = props.items.slice();
      if (st.ordem === 'preco') itens.sort((a, b) => {
        const pa = a.preco_valor, pb = b.preco_valor;
        if (pa === null && pb === null) return 0;
        if (pa === null) return 1;
        if (pb === null) return -1;
        return pa - pb;
      });
      else if (st.ordem === 'avaliacao') itens.sort((a, b) => (b.avaliacao || -1) - (a.avaliacao || -1));
      else itens.sort((a, b) => String(a.nome).localeCompare(String(b.nome)));
      itens.forEach(p => grid.appendChild(productCardEl(p, ctx, true)));
    }
    sel.addEventListener('change', () => { st.ordem = sel.value; save(st); pinta(); });
    pinta();
    renderProvenance(box, props.sources);
    root.appendChild(box);
  };

  R.productcompare = function (root, props, st, save, ctx) {
    const box = el('div', 'jdui-quiz');
    if (props.title) box.appendChild(el('div', 'jdui-title', props.title));
    const itens = props.items;
    const precos = itens.map(p => p.preco_valor).filter(v => v !== null && v !== undefined);
    const menor = precos.length ? Math.min.apply(null, precos) : null;
    const linhas = [
      { label: 'Preço', vals: itens.map(p => p.preco || 'Preço não confirmado'),
        win: itens.map(p => p.preco_valor !== null && p.preco_valor === menor) },
      { label: 'Loja', vals: itens.map(p => p.loja || '—') },
      { label: 'Avaliação', vals: itens.map(p => productStars(p.avaliacao, p.n_avaliacoes)) },
      { label: 'Disponibilidade', vals: itens.map(p => DISP_LABEL[p.disponibilidade] || DISP_LABEL.desconhecida) }
    ];
    const chaves = [];
    itens.forEach(p => Object.keys(p.specs || {}).forEach(k => { if (chaves.indexOf(k) < 0) chaves.push(k); }));
    chaves.slice(0, 8).forEach(k => {
      linhas.push({ label: k, vals: itens.map(p => (p.specs && p.specs[k]) || '—') });
    });
    const holder = el('div', 'jdui-chart');
    const t = document.createElement('table');
    t.className = 'jdui-cmp';
    const head = document.createElement('tr');
    head.appendChild(el('th', '', ''));
    itens.forEach(p => head.appendChild(el('th', '', (p.nome || '').slice(0, 40))));
    t.appendChild(head);
    linhas.forEach(l => {
      const tr = document.createElement('tr');
      tr.appendChild(el('th', '', l.label));
      l.vals.forEach((v, i) => {
        tr.appendChild(el('td', l.win && l.win[i] ? 'win' : '', v || '—'));
      });
      t.appendChild(tr);
    });
    holder.appendChild(t);
    box.appendChild(holder);
    const acts = el('div', 'jdui-cardacts');
    itens.forEach(p => {
      if (!p.url) return;
      const a = el('a', 'jdui-btn ghost', 'Abrir: ' + (p.nome || '').slice(0, 24) + ' ↗');
      a.href = p.url; a.target = '_blank'; a.rel = 'noopener noreferrer';
      acts.appendChild(a);
    });
    if (acts.children.length) box.appendChild(acts);
    renderProvenance(box, props.sources);
    root.appendChild(box);
  };

  R.productdetails = function (root, props, st, save, ctx) {
    st = st || {};
    const box = el('div', 'jdui-cards');
    const prod = props.produto;
    const card = productCardEl(prod, ctx, false);
    box.appendChild(card);
    const corpo = card._corpo;
    const specs = productSpecsTable(prod);
    if (specs) {
      corpo.appendChild(el('div', 'jdui-count', 'Especificações'));
      corpo.appendChild(specs);
    }
    productOfertas(corpo, prod);
    renderProvenance(box, props.sources);
    root.appendChild(box);
  };

  R.productgallery = function (root, props, st, save) {
    st.idx = Math.min(Math.max(parseInt(st.idx, 10) || 0, 0), props.imagens.length - 1);
    const box = el('div', 'jdui-cards');
    if (props.title) box.appendChild(el('div', 'jdui-title', props.title));
    const moldura = el('div', 'jdui-pmedia grande');
    box.appendChild(moldura);
    const faixa = el('div', 'jdui-pthumbs');
    box.appendChild(faixa);
    function pinta() {
      moldura.replaceChildren();
      const atual = props.imagens[st.idx];
      moldura.appendChild(productImg(atual.url, atual.legenda || props.title));
      if (atual.legenda) moldura.appendChild(el('div', 'jdui-ploja', atual.legenda));
      faixa.replaceChildren();
      props.imagens.forEach((img, i) => {
        const mini = el('button', 'jdui-pthumb' + (i === st.idx ? ' sel' : ''));
        mini.type = 'button';
        mini.setAttribute('aria-label', 'Foto ' + (i + 1));
        const t = document.createElement('img');
        t.src = img.url; t.alt = img.legenda || ('Foto ' + (i + 1));
        t.loading = 'lazy'; t.referrerPolicy = 'no-referrer';
        t.addEventListener('error', () => { mini.style.display = 'none'; });
        mini.appendChild(t);
        mini.addEventListener('click', () => { st.idx = i; save(st); pinta(); });
        faixa.appendChild(mini);
      });
    }
    const nav = el('div', 'jdui-actions');
    const ant = el('button', 'jdui-btn ghost', '‹ Anterior');
    const prox = el('button', 'jdui-btn ghost', 'Próxima ›');
    ant.type = 'button'; prox.type = 'button';
    ant.addEventListener('click', () => {
      st.idx = (st.idx - 1 + props.imagens.length) % props.imagens.length; save(st); pinta();
    });
    prox.addEventListener('click', () => {
      st.idx = (st.idx + 1) % props.imagens.length; save(st); pinta();
    });
    nav.appendChild(ant); nav.appendChild(prox);
    box.appendChild(nav);
    pinta();
    renderProvenance(box, props.sources);
    root.appendChild(box);
  };

  R.lesson = function (root, props, st, save, ctx) {
    const box = el('div', 'jdui-quiz');
    const info = el('div', 'jdui-count', 'Carregando aula…');
    box.appendChild(el('div', 'jdui-title', props.title || 'Aula'));
    box.appendChild(info);
    root.appendChild(box);
    st.open = st.open || {};
    function montar() {
      const b2 = el('div', 'jdui-quiz');
      b2.appendChild(el('div', 'jdui-title', props.title || 'Aula'));
      const i2 = el('div', 'jdui-count', 'Carregando aula…');
      b2.appendChild(i2);
      root.replaceChildren(b2);
      carregar(b2, i2);
    }
    if (precisaConexao(ctx)) {
      info.textContent = 'Conecte-se para ver a aula.';
      botaoTentar(root, info, montar);
      return;
    }
    carregar(box, info);
    async function carregar(bx, inf) {
      let aula;
      try {
        aula = await ctx.api('/api/learn/lessons/' + encodeURIComponent(props.lesson_id));
      } catch (_) {
        inf.textContent = 'Não consegui carregar. Toque para tentar de novo.';
        inf.style.cursor = 'pointer';
        inf.addEventListener('click', montar, { once: true });
        return;
      }
      const secs = aula.secoes || [];
      const feitas = secs.filter(s => s.feito).length;
      bx.replaceChildren();
      bx.appendChild(el('div', 'jdui-title', props.title || aula.assunto || 'Aula'));
      if (aula.objetivo) bx.appendChild(el('div', 'jdui-q', aula.objetivo));
      bx.appendChild(el('div', 'jdui-count', 'Progresso: ' + feitas + '/' + secs.length
        + (aula.nivel ? ' · ' + aula.nivel : '')));
      bx.appendChild(bar(secs.length ? feitas / secs.length * 100 : 0));
      const acc = el('div', 'jdui-acc');
      secs.forEach((s, i) => {
        const item = el('div', 'jdui-accitem');
        const b = el('button', 'jdui-accbtn', (s.feito ? '✓ ' : '') + (i + 1) + '. ' + s.titulo);
        b.setAttribute('aria-expanded', st.open[i] ? 'true' : 'false');
        const body = el('div', 'jdui-accbody');
        if (!st.open[i]) body.hidden = true;
        else montasecao(body, s, i);
        b.addEventListener('click', () => {
          st.open[i] = !st.open[i]; save(st);
          body.hidden = !st.open[i];
          b.setAttribute('aria-expanded', st.open[i] ? 'true' : 'false');
          if (st.open[i] && !body.hasChildNodes()) montasecao(body, s, i);
        });
        item.appendChild(b); item.appendChild(body); acc.appendChild(item);
      });
      bx.appendChild(acc);
      if (aula.resumo) {
        const r = el('div', 'jdui-q', 'Resumo: ' + aula.resumo);
        bx.appendChild(r);
      }
      function montasecao(body, s, i) {
        body.replaceChildren();
        const host = el('div', 'jdui-mdhost');
        host.innerHTML = ctx.markdown ? ctx.markdown(s.explicacao || '') : '';
        body.appendChild(host);
        if (s.exemplo) body.appendChild(el('div', 'jdui-q', 'Exemplo: ' + s.exemplo));
        if (s.exercicio) body.appendChild(el('div', 'jdui-q', 'Exercício: ' + s.exercicio));
        const nav = el('div', 'jdui-nav');
        if (!s.feito) {
          const ok = el('button', 'jdui-btn ghost', 'Marcar como concluída');
          ok.addEventListener('click', async () => {
            ok.disabled = true;
            try {
              await ctx.api('/api/learn/lessons/section', {
                method: 'POST',
                body: JSON.stringify({ lesson_id: props.lesson_id, ordem: i })
              });
              s.feito = true; save(st); paint();
            } catch (_) { ok.disabled = false; }
          });
          nav.appendChild(ok);
        }
        if (ctx.onChat) {
          const e = el('button', 'jdui-btn ghost', 'Explicar mais');
          e.addEventListener('click', () => ctx.onChat(
            'Explique mais sobre "' + s.titulo + '" da aula'
            + (aula.assunto ? ' "' + aula.assunto + '"' : '') + '.'));
          nav.appendChild(e);
        }
        body.appendChild(nav);
      }
      function paint() {
        const f2 = secs.filter(x => x.feito).length;
        bx.querySelector('.jdui-count').textContent = 'Progresso: ' + f2 + '/' + secs.length
          + (aula.nivel ? ' · ' + aula.nivel : '');
        const pg = bx.querySelector('.jdui-bar');
        if (pg && pg.firstChild) pg.firstChild.style.width = (secs.length ? f2 / secs.length * 100 : 0) + '%';
        acc.replaceChildren();
        secs.forEach((s, i) => {
          const item = el('div', 'jdui-accitem');
          const b = el('button', 'jdui-accbtn', (s.feito ? '✓ ' : '') + (i + 1) + '. ' + s.titulo);
          b.setAttribute('aria-expanded', st.open[i] ? 'true' : 'false');
          const body = el('div', 'jdui-accbody');
          if (!st.open[i]) body.hidden = true;
          else montasecao(body, s, i);
          b.addEventListener('click', () => {
            st.open[i] = !st.open[i]; save(st);
            body.hidden = !st.open[i];
            b.setAttribute('aria-expanded', st.open[i] ? 'true' : 'false');
            if (st.open[i] && !body.hasChildNodes()) montasecao(body, s, i);
          });
          item.appendChild(b); item.appendChild(body); acc.appendChild(item);
        });
      }
    }
  };

  /* ----- Mount + dispatcher ----- */
  function mount(root, slots, ctx) {
    ctx = ctx || {};
    (slots || []).forEach((msg, si) => {
      if (!msg || !msg.blocks) return;
      msg.blocks.forEach((b, bi) => {
        if (b.type === 'text') {
          const host = el('div', 'jdui-mdhost');
          host.innerHTML = ctx.markdown ? ctx.markdown(b.content) : '';
          root.appendChild(host);
          return;
        }
        const fn = R[b.component];
        if (!fn) return; // desconhecido: validado fora, ignora silencioso
        const key = si + ':' + bi + ':' + b.component;
        let st = {};
        try { st = ctx.loadState ? (ctx.loadState(key) || {}) : {}; } catch (_) { st = {}; }
        if (!st || typeof st !== 'object') st = {};
        const save = s => { try { if (ctx.saveState) ctx.saveState(key, s || {}); } catch (_) {} };
        const slot = el('div', 'jdui-slot');
        try { fn(slot, b.props, st, save, ctx); root.appendChild(slot); }
        catch (e) {
          slot.appendChild(el('div', 'jdui-fallback', 'Interface indisponível — veja o texto acima.'));
          root.appendChild(slot);
        }
      });
    });
  }

  window.JDUI = {
    version: VERSION,
    validateMessage, extractBlocks, mount, OPS, calcExpr,
    quizFromCode, quizFromText, COMPONENTS: Object.keys(V)
  };
})();
