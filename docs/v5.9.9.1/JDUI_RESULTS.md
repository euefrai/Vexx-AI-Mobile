# JDUI e Chrome

Preservados compositor/validadores, galeria, schema, fontes e painel existentes. O resultado profundo agora percorre compositor → mensagem SQLite → API de histórico → IndexedDB → reload. No chat são priorizados textos, fontes e mídia; plano/gráficos/evidências completos continuam no hub. Limite de tamanho pode omitir componentes da mensagem, sem truncar JSON/fatos do texto ou apagar registros do job; essa apresentação merece ampliar cobertura com resultados grandes.

Documento/PDF passou a exigir mídia do tipo document e tema pertinente; o caso Raspberry Pi Pico deixou de mostrar12 imagens genéricas e retornou limitação honesta, sem fingir leitura do manual. Não houve ganho certificado de leitura desse PDF.

A inspeção visual encontrou controle de modal antes da foto carregar e palavras quebradas nos botões desktop. Há agora feedback real de carregamento, estado de erro e botões proporcionais. O harness passou a exigir imagem de modal carregada; só verificar caption/foco era insuficiente.

Chrome real autenticado: 1280/390/320px, root igual ao viewport, cards245/350/288px;5 imagens recuperadas/5carregadas; modal com foto, próxima/setas/Escape/foco, metadados expandir/reload, movimento reduzido e zoom CSS200%. Screenshots foram inspecionados. O zoom mantém ausência de overflow, mas abrevia fortemente o header; não equivale a zoom nativo nem aparelho físico.

Falha de rede da imagem foi **injetada** via rota do navegador, com fallback visível; removida a falha, imagem voltou. Downloads MD e CSV pelo hub concluíram sem erro. Não se apresenta falha injetada como indisponibilidade externa espontânea. Zero pageerrors nas rodadas aceitas; isso é evidência adicional, não aprovação visual isolada.

Artefatos: visual-final.log, research-1280/390/320/modal/zoom-200.png, research-image-error.png, e2e-extra-accepted.log, exports MD/CSV. Service worker foi inspecionado: rede primeiro, sem interceptar API privada. Instalação/upgrade offline de PWA e perfil de CPU/RAM de celular físico não foram executados.
