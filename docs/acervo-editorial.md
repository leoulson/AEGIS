# Acervo editorial inicial

**Experimental: sete fichas pendentes de revisão profissional; zero revisadas.**
O lema permanece: “A conexão cai. O conhecimento permanece.” Público: profissionais
de saúde, com leitura inicial destinada à avaliação editorial. Esta implementação
não comprova segurança clínica nem desempenho no Raspberry Pi 2 físico.

## O que está disponível

| Área | Fichas locais pendentes |
| --- | --- |
| Urgência e emergência | Avaliação inicial/gravidade; dispneia; dor torácica; hipoglicemia (4) |
| Atenção primária | Febre (1) |
| Saúde da criança | Desidratação (1) |
| Saúde da mulher | Planejada; nenhuma ficha |
| Medicamentos e cálculos | Guia da calculadora experimental (1) |
| Procedimentos e segurança | Planejada; nenhuma ficha |

As contagens da interface são calculadas a partir dos dados, não desta tabela.
As áreas vazias aparecem como estrutura planejada. Não há livros completos,
respostas de IA ou novas regras terapêuticas da calculadora. As sínteses locais
incluem o texto necessário à leitura sem rede; links são complementares.

A consulta padrão da interface mostra somente revisados e explica o estado vazio.
**Explorar fichas pendentes na oficina editorial** ou o checkbox correspondente é
uma escolha explícita; o aviso e estado acompanham resultados, filtros e leitura.
Voltar à consulta assistencial oculta novamente os materiais pendentes, inclusive
os salvos. Salvos gráficos continuam temporários, conforme o comportamento anterior.

No terminal, `--include-pending` é exigido tanto para buscar quanto para ler fichas
pendentes. Sem ele, não há fichas editoriais liberadas neste conjunto. Documentos
legados pessoais não são promovidos a revisados: recebem rótulo separado na busca,
e seu antigo campo `reviewed` não é considerado comprovação de revisão profissional.

## Fonte única e geração reproduzível

- **Editar somente:** `content/editorial.json` (fichas, áreas, fontes e política).
- **Gerados:** `content/catalog.json` (terminal) e `aegis-linux/app/catalog-data.js`
  (navegador), com o mesmo conteúdo e índice textual. Não manter cópias manuais.
- **Código comum:** `aegis/catalog.py` valida o modelo, compila o índice e formata
  leitura no terminal. O gerador também confere os hashes do código da calculadora
  usado como fonte do guia; uma alteração exige reconferência documental.

```bash
python3 tools/build-catalog.py
python3 tools/build-catalog.py --check
# Usar um banco descartável durante revisão:
python3 -m aegis --db /tmp/aegis-editorial/library.sqlite3 init
python3 -m aegis --db /tmp/aegis-editorial/library.sqlite3 search osmolaridade --include-pending
python3 -m aegis --db /tmp/aegis-editorial/library.sqlite3 search '' --area urgencia --state pending_professional_review --include-pending
python3 -m aegis --db /tmp/aegis-editorial/library.sqlite3 read editorial:desidratacao --include-pending
python3 -m aegis --db /tmp/aegis-editorial/library.sqlite3 policy
```

`init` aceita `--source` apontando ao JSON editorial/gerado e mantém compatibilidade
com listas legadas. A importação é validada antes de gravar e transacionada em
SQLite, sob o lock de dados existente. Substitui apenas `editorial_cards` e seus
metadados; a tabela `documents` dos usuários é preservada. A importação repetida não
duplica fichas. IDs pessoais existentes têm prioridade na leitura; os resultados
editoriais do CLI fornecem `editorial:<id>` para evitar colisões com IDs legados.
Não é uma migração automática de dados pessoais ou um instalador de pacotes externos.

Abra `aegis-linux/app/index.html` diretamente no navegador para consultar as mesmas
fichas. O JavaScript gerado é carregado por `<script src>`, sem `fetch`, servidor,
CDN ou fonte remota. A política editorial também é local. Os serviços do lançador
continuam opcionais para este acervo e necessários às ferramentas do dispositivo.
Uma instalação antiga ou um slot já selecionado não é atualizado ao editar o
checkout; esta tarefa não altera a instalação do dispositivo.

O índice cobre título, área, palavras-chave, objetivo, população, contexto,
afirmações e referências usadas na ficha. A busca normaliza caixa/acentos e usa
substring literal. O HTML é construído com `textContent`/DOM, e referências externas
aceitam somente HTTPS sem credenciais. O gerador escapa caracteres que poderiam
fechar uma tag script. O corpus gerado tem aproximadamente 54 KB, sem framework
ou dependência de produção adicional; desempenho real no Pi continua pendente.

## Modelo de ficha e fluxo editorial

Cada ficha tem ID estável, título, resumo, categoria, palavras-chave, público,
população, contexto e objetivo. `sections` contém listas em:

```text
initial_assessment        avaliação inicial
red_flags                 sinais de alerta
source_based_actions      condutas fundamentadas
limits_and_referral       limites, exceções e encaminhamento
follow_up                 acompanhamento, se aplicável
evidence_context          evidência complementar/aplicabilidade
```

Cada item identifica `kind` (`synthesis`, `editorial`, `quotation`), texto e
`citations: [{source_id, locator}]`. A interface distingue **Síntese AEGIS**,
**Observação editorial** e **Texto original citado**. Não há transcrições literais
nas fichas iniciais. Se não houver conteúdo específico sustentado para uma seção,
use lista vazia: a seção não aparece. Não usar frases genéricas para simular um
protocolo completo. Não inferir condutas pelo artigo sem análise profissional.

`editorial` contém estado, proveniência, pendências e data de consulta das fontes.
Estados: `draft`, `pending_professional_review`, `reviewed`. Nos dois primeiros,
`reviewer` e `reviewed_on` são `null`. **Consulta documental não é revisão clínica.**

Para adicionar/atualizar:

1. Selecionar pergunta, população e contexto. Consultar fonte oficial brasileira e
   literatura pertinente; verificar versão, método, limitações e direitos. Registrar
   o que não pôde ser verificado. Não usar apenas DOI/indexação como selo de qualidade.
2. Acrescentar fonte completa e ficha com ID estável. Vínculo por afirmação exige
   localização verificável (página/seção), e não apenas uma bibliografia genérica.
3. Manter pendente de revisão profissional. O texto inicial foi produzido com
   assistência de IA e não teve responsável clínico designado nem aprovação inventada.
4. Para promover a `reviewed`, registrar a revisão real em
   `content/reviews/<registro>.md`, com responsável, data, escopo, análise de
   atualização/aplicabilidade e alterações. Preencher `reviewer`, `reviewed_on` e
   `review_document` com esse caminho. O validador exige registro presente; a mera
   existência de arquivo não autentica a identidade do revisor, que cabe ao processo
   humano de governança. Não gerar registros ou nomes fictícios para passar na validação.
5. Regenerar, executar testes, revisar o diff clínico e documental. A distribuição
   deve manter estados e avisos, sem renomear pendente como revisado. Não foi publicada
   uma Release estável nesta implementação.

Correções devem citar ID da ficha, afirmação e fonte, sem dados de pacientes, por
issue do repositório ou registro editorial local. Corrigir a fonte única e reavaliar
fichas relacionadas. Quando houver dúvida relevante, retirar do estado revisado e
registrar a pendência até revisão. Não há atualização silenciosa por rede.

## Fontes efetivamente consultadas em 11/11/2026

O cadastro em `content/editorial.json` contém referências completas, URLs, edições,
consulta, hashes dos documentos lidos, avaliação crítica e pendências. Hash registra
os bytes observados; não comprova autenticidade por si só. Os textos de terceiros
foram lidos para pesquisa e **não foram incluídos no repositório**.

| Fonte | Verificação e uso | Reprodução do original |
| --- | --- | --- |
| Ministério da Saúde. **Acolhimento à demanda espontânea: queixas mais comuns na Atenção Básica**, CAB 28, v. II, 1ª ed., 1ª reimpressão, 2013. ISBN 978-85-334-1973-5 | PDF oficial BVS/MS acessado; folha de rosto/expediente, avaliação de risco e capítulos de diabetes, diarreia, dispneia e dor torácica consultados. É apoio institucional antigo, não revisão sistemática contemporânea. | Expediente permite reprodução com fonte, sem venda/fim comercial; não declara domínio público. Não distribuído. |
| Ministério da Saúde, OPAS, UNICEF. **Manual de quadros de procedimentos: AIDPI Criança: 2 meses a 5 anos**, 2017. ISBN 978-85-334-2502-6 | PDF oficial acessado; escopo é 2 meses a menos de 5 anos. Quadros de perigo, respiração, diarreia, febre e tratamento/retorno consultados. A paginação do sumário diverge do corpo para alguns quadros; os localizadores foram conferidos no corpo/PDF. | CC BY-NC-SA 4.0 indicada no expediente. Não distribuído. |
| Gerry et al. **Early warning scores for detecting deterioration in adult hospital patients: systematic review and critical appraisal of methodology**. BMJ. 2020;369:m1501. DOI `10.1136/bmj.m1501` | Texto integral XML e metadados Europe PMC conferidos. Revisão de desenvolvimento/validação em adultos internados, com problemas metodológicos; não valida escores para APS brasileira/pediatria. | Licença explícita/metadados CC BY 4.0; XML também contém linha genérica discordante, a reconferir antes de redistribuir. Não distribuído. |
| Holgersson et al. **Fever therapy in febrile adults: systematic review with meta-analyses and trial sequential analyses**. BMJ. 2022;378:e069620. DOI `10.1136/bmj-2021-069620` | Texto integral XML e metadados conferidos. Ensaios em adultos; distingue desfechos críticos e conforto. Não extrapolar a crianças ou transformar resultado agregado em proibição de antitérmico. | CC BY-NC 4.0 indicada. Não distribuído. |
| Hahn, Kim, Garner. **Reduced osmolarity oral rehydration solution for treating dehydration due to diarrhoea in children: systematic review**. BMJ. 2001;323(7304):81–85. DOI `10.1136/bmj.323.7304.81` | Página integral PMC e metadados conferidos, incluindo métodos/discussão. Ensaios randomizados pediátricos hospitalares; revisão histórica, não referência atual de fórmula ou volume. Não fornece evidência direta de prevenção domiciliar. | Permissão de redistribuição não estabelecida; acesso ao texto não equivale a licença. Não distribuído. |
| **Calculadora local do AEGIS** | `medication-core.js` e `medication-ui.js` lidos e hashes registrados. Descreve unidades, aritmética, validações, cadastro MSF/NHS e limites funcionais já existentes. Não é fonte clínica ministerial. | Código MIT; direitos das referências MSF/NHS são independentes. Doses, limites e regras ficaram byte a byte inalterados. |

Checagem de correções/retratações: respostas `resultType=core` do Europe PMC para
PMIDs 32434791, 35820685 e 11451782 foram consultadas. Não havia indicação de
retratação/correção nessas respostas. Havia comentários vinculados à revisão da
febre (PMID 36315945) e à revisão da SRO (11451764, 11713745, 11713746); comentário
não foi rotulado como retratação. A consulta não é auditoria exaustiva de todos os
registros nem prova de inexistência de atualizações futuras.

**Atualização ministerial pendente:** edições/substituições posteriores dos dois
manuais usados não foram confirmadas nesta tarefa. Tentativas de localizar o
manual de dengue e PCDT por URLs presumidas falharam ou retornaram conteúdo que não
era o documento esperado; eles **não** foram cadastrados como fontes verificadas.
Uma busca oficial BVS por dengue também não estabeleceu uma edição clínica atual.
Isso limita principalmente a adoção operacional, o manejo por etiologia e o uso
de limiares/esquemas farmacológicos antigos. Não se afirmou que a edição consultada
é a mais recente. O CAB 28 tem definições antigas de hipoglicemia e recomendações
terapêuticas que não foram importadas como prescrição; revisão com protocolo atual
permanece expressamente pendente.

Diferenças não devem ser apagadas: AIDPI é pediátrico; revisão da febre é de adultos;
escores são de ambiente hospitalar; revisão de SRO é antiga e hospitalar. Não se
fundiram essas populações em um algoritmo. Sínteses próprias e fatos referenciados
são disponibilizados sob MIT; as licenças dos originais permanecem separadas e não
são ampliadas pela licença do código. Reavaliar permissão antes de qualquer cópia
integral, adaptação extensa, imagem ou transcrição de terceiro.

## Verificações

```bash
python3 tools/build-catalog.py --check
python3 -m unittest discover -s tests -v
python3 -m unittest discover -s aegis-linux/tests -v
node --test --test-isolation=none aegis-linux/tests/medication.test.cjs
AEGIS_CHROME=/usr/bin/chromium node aegis-linux/tests/run-browser-qa.cjs
# Onde o navegador permite file://:
AEGIS_CHROME=/usr/bin/chromium node aegis-linux/tests/verify-interface.cjs
```

No cloud Linux x86_64 desta tarefa, Chromium gerenciado negou `file://` com
`ERR_BLOCKED_BY_ADMINISTRATOR`. Sua política não foi alterada. A abertura direta foi
validada com o **Firefox de testes do Playwright, offline**, zero erros JavaScript
e zero requisições HTTP/HTTPS, inclusive busca/filtros/leitura/política/salvos e
regressão da calculadora. Com o Firefox de teste instalado em pasta local:

```bash
PLAYWRIGHT_BROWSERS_PATH=/workspace/.aegis-test-browsers AEGIS_BROWSER=firefox \
  node aegis-linux/tests/verify-interface.cjs
```

Chromium passou na integração pelo lançador/loopback, incluindo as ferramentas já
existentes. As mudanças dos testes substituem os três títulos fictícios por sete
fichas reais pendentes e verificam o estado padrão vazio; as asserções funcionais
da calculadora foram mantidas. Testes Python verificam IDs/campos/referências,
barreiras editoriais, ausência de revisão fictícia, consistência dos dois artefatos,
busca/filtros, preservação de documentos legados com IDs coincidentes e reimportação.
O código da calculadora é conferido por hash. Também há teste de texto malicioso
como dado e escape no JavaScript gerado.

As capturas do catálogo serão geradas com `AEGIS_QA=/tmp/pasta` no teste de navegador:
visões 1440×810 e 390×810. Validar no Pi 2 físico: abertura de arquivo no Chromium do
Raspberry Pi OS 32-bit, legibilidade, teclado/toque, busca, troca de área/estado,
fontes locais, uso de RAM/CPU e tempo de carregamento. Não houve validação clínica,
ensaio em hardware físico nem atualização da instalação do dispositivo.
