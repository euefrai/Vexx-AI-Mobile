# E2E real isolado

FastAPI + PC Agent QA real, SQLite temporário, conta alice de teste, Chrome. Sem produção. Casos A/B separados; fonte conhecida nunca contada como descoberta.

| Caso | Discovery | Reading/evidence | Synthesis | JDUI/persistência | Overall |
|---|---|---|---|---|---|
| A Nikon conhecido, URL explícita | Fixture declarada | HTML público real, peso/bateria parciais | Extrativa | Fonte/contexto/partials, reload e link original | Parcial de leitura validado |
| B Nikon sem URL | Executada | Sem evidência retida lida | Não houve evidência para LLM | Parcial persistido | Insuficiente |
| C múltiplas facetas Object.entries | Executada | Sem evidência retida lida | Sem síntese validada | Reload preservado | Insuficiente |
| D números/tabela Nikon Z8 | Executada | Sem evidência retida lida | Sem síntese validada | Reload preservado | Insuficiente |
| E biblioteca sem dado diário | Executada | Sem dado confirmado | Abstenção parcial | Reload preservado | Não inventou valor |
| F sqlite3.connect moderada | Plano/busca/replan executados | Sem evidência retida lida | Pipeline não atingiu síntese fundamentada | Parcial persistido | Não aprovar cadeia completa |
| C LLM Math.hypot conhecido | Entrada semeada | Uma fonte real válida | Provedor vazio, blocked | Parcial persistido | BLOCKED |

SSE 200 nos fluxos concluídos, IDs/texto comparados após reload, page_errors=[] registrados. Imagens: cinco cards com origem/licença; metadados não apresentados como prova visual. Cancelamento cancelada. MD/CSV baixados e IndexedDB verificado.

Incidente de harness: configuração foi enviada antes de terminar a navegação inicial; script reportou Execution context destroyed. Uma pesquisa padrão de museu rodou antes da retomada; excluída dos critérios. Captura histórica sobrescrita foi preservada localmente na pasta atual e original restaurado do Git (estava limpo no início). Não contar tentativa inválida como passe.

Reconexão injetada: fetch offline falhou; health voltou 200. Isso não cobre todos os fluxos offline. Encerramento QA e estado final são registrados em qa-shutdown.json após os testes.
