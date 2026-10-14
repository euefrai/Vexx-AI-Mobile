# JDUI — Exemplos válidos (também usados como fixtures dos testes)

Envelope de todos: `{"version": "FAJULTO-ui-message/v1", "blocks": [...]}`.
No chat, cada envelope vai dentro de um fence:

    ```jdui
    { ... }
    ```

## Quiz

```json
{"version": "FAJULTO-ui-message/v1", "blocks": [
  {"type": "text", "content": "Teste seus conhecimentos:"},
  {"type": "ui", "component": "quiz", "props": {"title": "Python básico", "questions": [
    {"q": "Quanto é 2 + 2?", "options": ["3", "4", "5"], "answer": 1, "explain": "Soma simples."},
    {"q": "Qual o tipo de []?", "options": ["list", "dict"], "answer": 0}
  ]}}
]}
```

## Checklist

```json
{"version": "FAJULTO-ui-message/v1", "blocks": [
  {"type": "ui", "component": "checklist", "props": {"title": "Rotina de estudos", "items": [
    "Ler capítulo 1", {"label": "Fazer exercícios", "checked": true}
  ]}}
]}
```

## Calculadora (basic | imc | porcentagem | juros)

```json
{"version": "FAJULTO-ui-message/v1", "blocks": [
  {"type": "text", "content": "Calcule aqui mesmo:"},
  {"type": "ui", "component": "calculator", "props": {"kind": "imc", "title": "Calculadora de IMC"}}
]}
```

## Cards (comparação)

```json
{"version": "FAJULTO-ui-message/v1", "blocks": [
  {"type": "ui", "component": "cards", "props": {"title": "Python × JavaScript", "items": [
    {"title": "Python", "desc": "Simples e legível", "value": "9.5", "badge": "recomendada",
     "url": "https://python.org", "action": {"chat": "Detalhe as vantagens de Python"}},
    {"title": "JavaScript", "desc": "Ubíqua na web", "value": "9.0"}
  ]}}
]}
```

## Diagrama

```json
{"version": "FAJULTO-ui-message/v1", "blocks": [
  {"type": "ui", "component": "diagram", "props": {"title": "Conexão com o Hermes",
    "direction": "v",
    "nodes": [
      {"id": "cel", "label": "Celular", "desc": "PWA + IndexedDB"},
      {"id": "render", "label": "Render", "desc": "Relay sem banco"},
      {"id": "pc", "label": "PC Agent", "desc": "SQLite + streaming", "status": "ok"},
      {"id": "hermes", "label": "Hermes", "desc": "Modelo Laguna S 2.1"}
    ],
    "edges": [
      {"from": "cel", "to": "render", "label": "HTTPS"},
      {"from": "render", "to": "pc", "label": "WSS"},
      {"from": "pc", "to": "hermes", "label": "loopback"}
    ]}}
]}
```

## Tabela

```json
{"version": "FAJULTO-ui-message/v1", "blocks": [
  {"type": "ui", "component": "table", "props": {"title": "Comparativo",
    "columns": ["Linguagem", "Nota"],
    "rows": [["Python", "9.5"], ["JavaScript", "9.0"], ["Java", "8.5"]] }}
]}
```

## Formulário com cálculo

```json
{"version": "FAJULTO-ui-message/v1", "blocks": [
  {"type": "ui", "component": "form", "props": {"title": "Calcule seu IMC", "calc": "imc",
    "submit": "Calcular",
    "fields": [
      {"name": "peso", "label": "Peso (kg)", "type": "number", "required": true},
      {"name": "altura", "label": "Altura (cm)", "type": "number", "required": true}
    ]}}
]}
```

## Progresso, abas, sanfona

```json
{"version": "FAJULTO-ui-message/v1", "blocks": [
  {"type": "ui", "component": "progress", "props": {"label": "Curso", "value": 30, "max": 100}},
  {"type": "ui", "component": "tabs", "props": {"tabs": [
    {"title": "Resumo", "markdown": "Texto **curto**."}, {"title": "Detalhes", "markdown": "Mais texto."}
  ]}},
  {"type": "ui", "component": "accordion", "props": {"items": [
    {"title": "O que é variável?", "markdown": "Espaço nomeado na memória."}
  ]}}
]}
```
