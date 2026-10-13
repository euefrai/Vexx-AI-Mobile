/* JDUI 1.0 — Julia Dynamic UI Engine (frontend).
   Renderiza blocos declarativos `julia-ui-message/v1` com componentes NATIVOS.
   Nenhum JavaScript do modelo é executado: só funções deste registry.
   Espelho da validação em `jdui.py` (backend). */
'use strict';
(function () {
  const VERSION = 'julia-ui-message/v1';
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
    try { const p = new URL(u, location.href); return (p.protocol === 'http:' || p.protocol === 'https:') ? p.href : ''; }
    catch (_) { return ''; }
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
      if (['basic', 'imc', 'porcentagem', 'juros'].indexOf(kind) < 0) throw new JduiErro('calculator.kind');
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
        return { id, label: S(n.label, 120), desc: S(n.desc, 300), status: S(n.status, 20) };
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
    tabs(p) {
      const abas = reqList(p, 'tabs', 2, 6, 'tabs 2..6');
      return { tabs: abas.filter(a => a && a.title).map(a => ({ title: S(a.title, 80), markdown: S(a.markdown, 3000) })) };
    },
    accordion(p) {
      const itens = reqList(p, 'items', 1, 10, 'accordion 1..10');
      return { items: itens.filter(a => a && a.title).map(a => ({ title: S(a.title, 120), markdown: S(a.markdown, 3000) })) };
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
    return { ok: true, msg: { version: VERSION, blocks: norm }, erros };
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
    }
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

  R.checklist = function (root, props, st, save) {
    st.checked = Array.isArray(st.checked) ? st.checked : props.items.map(i => !!i.checked);
    const box = el('div', 'jdui-check');
    if (props.title) box.appendChild(el('div', 'jdui-title', props.title));
    const pg = bar(0); box.appendChild(pg);
    const info = el('div', 'jdui-count'); box.appendChild(info);
    const list = el('div', 'jdui-items'); box.appendChild(list);
    function paint() {
      const n = st.checked.filter(Boolean).length;
      pg.firstChild.style.width = (props.items.length ? n / props.items.length * 100 : 0) + '%';
      info.textContent = n + ' de ' + props.items.length + ' concluídas';
      list.replaceChildren();
      props.items.forEach((it, i) => {
        const lab = el('label', 'jdui-item' + (st.checked[i] ? ' done' : ''));
        const c = document.createElement('input');
        c.type = 'checkbox'; c.checked = !!st.checked[i];
        c.setAttribute('aria-label', it.label);
        c.addEventListener('change', () => { st.checked[i] = c.checked; save(st); paint(); });
        lab.appendChild(c); lab.appendChild(el('span', '', it.label));
        list.appendChild(lab);
      });
    }
    paint();
    root.appendChild(box);
  };

  R.calculator = function (root, props) {
    const box = el('div', 'jdui-calc');
    box.appendChild(el('div', 'jdui-title', props.title || 'Calculadora'));
    if (props.kind === 'basic') {
      const disp = el('div', 'jdui-disp', '0');
      disp.setAttribute('aria-live', 'polite');
      box.appendChild(disp);
      let cur = '';
      const grid = el('div', 'jdui-grid');
      ['C', '⌫', '%', '/', '7', '8', '9', '*', '4', '5', '6', '-', '1', '2', '3', '+', '0', '.', '(', ')'].forEach(k => {
        const b = el('button', 'jdui-key' + ('/*÷-+= '.indexOf(k) >= 0 || k === 'C' ? ' op' : ''), k);
        b.type = 'button';
        b.addEventListener('click', () => {
          if (k === 'C') cur = '';
          else if (k === '⌫') cur = cur.slice(0, -1);
          else cur += k;
          disp.textContent = cur || '0';
        });
        grid.appendChild(b);
      });
      const eq = el('button', 'jdui-key eq', '=');
      eq.type = 'button';
      eq.addEventListener('click', () => {
        try { const v = calcExpr(cur); disp.textContent = fmt(v); cur = String(v); }
        catch (_) { disp.textContent = 'Erro'; cur = ''; }
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
        lab.appendChild(inp); box.appendChild(lab); inputs[f[0]] = inp;
      });
      const out = el('div', 'jdui-result', 'Preencha e toque em Calcular.');
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

  R.diagram = function (root, props) {
    const box = el('div', 'jdui-diagram' + (props.direction === 'h' ? ' horiz' : ''));
    if (props.title) box.appendChild(el('div', 'jdui-title', props.title));
    const flow = el('div', 'jdui-flow'); box.appendChild(flow);
    const byId = {};
    props.nodes.forEach(n => { byId[n.id] = n; });
    props.nodes.forEach((n, i) => {
      const node = el('button', 'jdui-node' + (n.status ? ' st-' + n.status.replace(/[^a-z]/g, '') : ''));
      node.type = 'button';
      node.setAttribute('aria-expanded', 'false');
      node.appendChild(el('span', 'jdui-dot'));
      const tx = el('span', 'jdui-nodetx');
      tx.appendChild(el('strong', '', n.label));
      node.appendChild(tx);
      if (n.desc) {
        const full = n.desc;
        const sm = el('small', '', full.slice(0, 60) + (full.length > 60 ? '…' : ''));
        tx.appendChild(sm);
        node.addEventListener('click', () => {
          const open = node.classList.toggle('open');
          node.setAttribute('aria-expanded', open ? 'true' : 'false');
          sm.textContent = open ? full : (full.slice(0, 60) + (full.length > 60 ? '…' : ''));
        });
      }
      flow.appendChild(node);
      if (i < props.nodes.length - 1) {
        const edge = (props.edges || []).find(e => e.from === n.id && byId[e.to]);
        const c = el('div', 'jdui-conn', (edge && edge.label ? edge.label + ' ' : '') + (props.direction === 'h' ? '→' : '↓'));
        flow.appendChild(c);
      }
    });
    root.appendChild(box);
  };

  R.table = function (root, props) {
    const box = el('div', 'jdui-tablewrap');
    if (props.title) box.appendChild(el('div', 'jdui-title', props.title));
    const wrap = el('div', 'jdui-scrollx');
    const t = document.createElement('table');
    t.className = 'jdui-table';
    const thead = document.createElement('thead');
    const hr = document.createElement('tr');
    let sortCol = -1, sortAsc = true;
    const tbody = document.createElement('tbody');
    function rows() {
      let rs = props.rows.slice();
      if (sortCol >= 0) {
        rs.sort((a, b) => {
          const x = a[sortCol] || '', y = b[sortCol] || '';
          const nx = parseFloat(String(x).replace(',', '.')), ny = parseFloat(String(y).replace(',', '.'));
          const c = (!isNaN(nx) && !isNaN(ny)) ? nx - ny : String(x).localeCompare(String(y), 'pt-BR');
          return sortAsc ? c : -c;
        });
      }
      return rs;
    }
    function paint() {
      tbody.replaceChildren();
      rows().forEach(r => {
        const tr = document.createElement('tr');
        r.forEach(c => tr.appendChild(el('td', '', c)));
        tbody.appendChild(tr);
      });
      Array.prototype.forEach.call(hr.children, (th, i) => {
        th.textContent = props.columns[i] + (i === sortCol ? (sortAsc ? ' ▲' : ' ▼') : '');
      });
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
    thead.appendChild(hr); t.appendChild(thead); t.appendChild(tbody);
    wrap.appendChild(t); box.appendChild(wrap);
    paint();
    root.appendChild(box);
  };

  R.form = function (root, props) {
    const box = el('div', 'jdui-form');
    box.appendChild(el('div', 'jdui-title', props.title || 'Formulário'));
    const vals = {};
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
      lab.appendChild(inp); box.appendChild(lab); vals[f.name] = inp;
    });
    const out = el('div', 'jdui-result', '');
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
