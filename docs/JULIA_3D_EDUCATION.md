# Cenas e sequências educativas — V5.4

O catálogo original em `model3d_education.py` gera geometrias procedurais pequenas. Não baixa modelos nem atribui precisão técnica a ilustrações.

| Pedido | Conteúdo | Etapas |
|---|---|---|
| Mostre um cubo didático em 3D | 6 faces, 12 arestas e 8 vértices selecionáveis; lado 2, área total 24 e volume 8, em unidades ilustrativas | Faces, arestas, vértices, dimensões |
| Mostre um computador em 3D | Placa-mãe, CPU, RAM e GPU com descrições e relações | Conexões, processamento, memória, gráficos |
| Mostre o sistema solar em 3D | Sol, Terra e Marte, com órbitas circulares ilustrativas | Estrela, Terra, Marte |

O cubo ideal tem espessuras artificiais para tornar faces/arestas/vértices clicáveis. O computador não representa socket, compatibilidade, desempenho ou escala reais. O sistema solar é um recorte com três corpos; tamanhos, distâncias, velocidades e períodos não representam escala física. Essas limitações aparecem na própria interface.

Cada etapa contém título, texto, parte selecionada, vista e estado explodido. O mecanismo reutiliza os meshes existentes. O usuário pode escolher uma etapa, avançar/voltar, reproduzir/pausar e ajustar a velocidade. A sequência avança a cada quatro segundos na velocidade 1× e para ao fim. Transições de posição duram 300 ms. As órbitas são animações conceituais, sem motor físico.

`prefers-reduced-motion` desliga reprodução automática ao restaurar e elimina interpolação e movimento orbital. O usuário ainda pode avançar etapas e iniciar explicitamente a sequência textual. A animação interrompe frames quando o viewer sai da tela ou a aba fica oculta; não tenta recuperar o tempo transcorrido em segundo plano.

O snapshot salva etapa, velocidade e reprodução, além da seleção/câmera/visibilidade. Não salva o ângulo orbital a cada frame: o reload restaura a etapa, mas reinicia a fase orbital. Pausar durante uma sessão congela a posição atual. A câmera inicial solar enquadra o trajeto orbital completo, não somente o alinhamento inicial dos corpos.

Limites atuais: sem áudio/narração, dinâmica física, compatibilidade de hardware, modelos externos ou edição livre de cenas. As explicações são textos locais do catálogo e anotações validadas. Não dependem de inferência LLM.

## V5.6 — deltas

- Nova educação `device`: aparelhos do catálogo local e cenas aproximadas por
  pesquisa, com rótulo de fidelidade (`aproximado`/`conceitual`) e fonte visível
  ([JULIA_3D_MODEL_GENERATION.md](JULIA_3D_MODEL_GENERATION.md)).
- Cenas de dispositivo usam papel/grupo/ordem por peça, relações registradas e
  ≥ 3 etapas educativas; limites continuam ≤ 32 peças e ≤ 8 etapas.
- As cenas clássicas ganharam sombras suaves, contornos e palco claro
  ([JULIA_3D_VISUAL_POLISH.md](JULIA_3D_VISUAL_POLISH.md)); nenhuma promessa
  técnica nova foi adicionada — as limitações de escala continuam valendo.
