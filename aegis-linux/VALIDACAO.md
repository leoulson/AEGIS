# Validação da versão 0.1

## Recuperação e conferência — 3 de novembro de 2026

Comparação realizada com `main` em `c6536d35e2849cd0d0ae48087c52710bc9bd9265`, que continha somente a biblioteca de terminal. Foram acrescentados 14 arquivos locais de `aegis-linux`, excluindo caches Python, e um manifesto de SHA-256 em `docs/linux-source-manifest.json`. O código do lançador, HTML, CSS, ícones, fórmulas e cadastro clínico foi preservado byte a byte. Nesta preparação foram atualizados os guias e ampliado o teste de interface; não foram criadas funcionalidades ou doses.

Resultados atuais no Windows:

- Oito testes Python do lançador aprovados, com instalação e autostart simulados em diretórios temporários.
- Oito testes Node.js da calculadora aprovados: conversões, entradas inválidas, limites cadastrados, idade e condições especiais.
- Teste da interface em Chrome com contexto offline aprovado: biblioteca, pesquisa, filtros, salvos, fontes, guia, botão Calculadora, cálculo prescrito, referência NHS, bloqueio de condições especiais, concentração incompleta e retorno à biblioteca. Zero erros JavaScript e zero requisições HTTP/HTTPS. Sem rolagem horizontal em 1440, 1024 e 390 pixels; capturas desktop e móvel inspecionadas.
- O teste antigo da biblioteca de terminal (`tests/test_app.py` na raiz) falhou na limpeza do diretório temporário no Windows: `PermissionError [WinError 32]` no SQLite ainda aberto. Não houve falha nas asserções de importar/buscar/ler antes da limpeza. Esse código já estava no `main` e não foi alterado nesta recuperação.
- Fontes cadastradas conferidas em 03/11/2026: [paracetamol MSF](https://medicalguidelines.msf.org/en/viewport/EssDr/english/paracetamol-acetaminophen-oral-16684400.html), [ibuprofeno MSF](https://medicalguidelines.msf.org/en/viewport/EssDr/english/ibuprofen-oral-16683877.html) e [cetirizina NHS](https://www.nhs.uk/medicines/cetirizine/how-and-when-to-take-cetirizine/). As páginas MSF foram recuperadas pela busca indexada, pois a abertura direta retornou HTTP 405. Mantidas as datas declaradas e a ausência de data de atualização do ibuprofeno; a conferência não representa validação clínica.

Procedência e limites: a conversa “Editar Linux проекта” registra o protótipo anterior funcionando no Debian e a calculadora implementada no workspace, com ZIP e instalação da VM ainda antigos. Os arquivos internos da VM não foram lidos nem copiados; `VBoxManage` retornou acesso negado. Não foi aplicada atualização na VM, configurado login automático ou testado Raspberry Pi 2 físico. O lançador continua apenas com as opções já existentes. A publicação remota depende de autenticação GitHub funcional; esta preparação local não comprova envio.

Para reproduzir a calculadora:

```bash
node --test tests/medication.test.cjs
```

## Registro histórico da base Linux

Revisão Raspberry Pi 2 — 2 de novembro de 2026.

- Alvo corrigido para Raspberry Pi 2 e Raspberry Pi OS de 32 bits. A recomendação anterior de Pi 5/64 bits foi substituída no guia do software.
- Catálogo JavaScript completo de ícones substituído pelos oito ícones usados pela interface: de 594.649 para 2.159 bytes. Isso reduz código transferido/lido e interpretado; o efeito sobre memória e velocidade no Pi 2 ainda não foi medido.
- Os testes de navegação offline foram repetidos após a troca dos ícones e passaram, incluindo ícones renderizados, zero requisições HTTP/HTTPS, zero erros JavaScript e ausência de rolagem horizontal em 1440, 1024 e 390 pixels.

Validações da implementação inicial, ainda aplicáveis ao lançador que não foi alterado nesta revisão:

- Oito testes automatizados Python aprovados em Windows, com instalação simulada em diretórios temporários: cópia da interface e atalho; preservação de instalação existente; detecção de navegador ausente; ativação/desativação XDG; preservação de entradas alheias; URI local e sandbox; escape de argumentos; bloqueio de instalação em Windows.
- Interface testada no Chrome em Windows com contexto offline: pesquisa, filtros, salvos na sessão, fontes, guia demonstrativo e ícones.
- Nenhuma requisição HTTP/HTTPS e nenhum erro JavaScript observados durante o teste da interface.
- Ausência de rolagem horizontal nas larguras de 1440, 1024 e 390 pixels. Revisão visual das versões desktop e móvel realizada.
- Layout original incorporado integralmente; SHA-256 registrado em origem.json. Os arquivos de origem e o modelo 3D foram preservados.

Limites: os testes Python usam diretórios temporários e simulam os pré-requisitos Linux. Ainda não foram validados o navegador iniciado pelo lançador no Linux, o processamento do atalho pelo desktop, o início real via XDG/labwc ou o hardware da maleta. Não há sistema operacional instalado ou imagem bootável neste pacote.

Reproduzir os testes Python, a partir da pasta do pacote:

```bash
python3 -m unittest discover -s tests -v
```

O teste JavaScript requer Node.js, Playwright e Chrome/Chromium já disponíveis. `AEGIS_PLAYWRIGHT` pode apontar para a instalação local de Playwright; `AEGIS_CHROME`, para o executável do navegador; e `AEGIS_QA`, para uma pasta opcional de capturas. Execute `node tests/verify-interface.cjs`.
