# Ferramentas offline do dispositivo

Esta alteração depende do atualizador do PR #2 e usa o mesmo supervisor/ponte local,
slots de aplicativo, assinatura de pacotes e rollback. O supervisor agora é
**1.1.0**. Não há nova aplicação web remota: Chromium/Chrome continua sendo o motor
da janela na tela do dispositivo, com IPC autenticado apenas em `127.0.0.1`.
Nenhum recurso novo precisa da internet. Não foi publicada uma Release nem aplicada
uma atualização a um dispositivo por esta tarefa.

## Instalar e testar sem alterar sua instalação

Na branch `feat/device-tools-recovery`, com Python 3.9+, SQLite, OpenSSL e Chromium:

```bash
# Use a sua sessão gráfica Linux. Um diretório de teste evita qualquer instalação real.
aegis_test=$(mktemp -d)
XDG_DATA_HOME="$aegis_test/data" XDG_CONFIG_HOME="$aegis_test/config" \
  python3 aegis-linux/aegis.py
# Para instalar uma cópia de teste e o atalho, sem sobrescrever a instalação atual:
XDG_DATA_HOME="$aegis_test/data" XDG_CONFIG_HOME="$aegis_test/config" \
  python3 aegis-linux/aegis.py --install-updater
```

Use as mesmas variáveis ao reabrir ou testar a persistência/recuperação. O terminal
independente permite escolher o mesmo banco com `python3 -m aegis --db
"$aegis_test/data/aegis/library.sqlite3" ...`; seu caminho padrão histórico continua
`~/.local/share/aegis/library.sqlite3`. Os dados de demonstração existentes não são
importados automaticamente por estes recursos.

`--install-updater` copia também `device_services.py` e a pasta de recuperação ao
lado do supervisor. Continua recusando sobrescrita. Para instalar em produção,
primeiro valide em uma cópia e no hardware; obtenha o novo bootstrap 1.1 por canal
confiável. O payload assinado v1 não pode atualizar o supervisor. O builder passa a
exigir `min_updater: 1.1.0`; um supervisor 1.0 bloqueia esse payload. Não basta copiar
só o novo HTML/JS sobre a instalação anterior. Se já houver slots de uma instalação
antiga, eles continuam selecionados: após instalar o novo supervisor em cópia
separada, importe o novo payload assinado para trocar a interface pelo fluxo normal
de atualização. Não gere uma assinatura ou Release estável sem revisão.

## Acesso pela interface

**Configurações** mantém Atualizações e acrescenta Diagnóstico, Verificar acervo,
Backups, Acessibilidade, Atalhos e Recuperação. A calculadora, busca, referências,
guia e salvos demonstrativos permanecem disponíveis. O antigo HTML aberto como
arquivo é somente prévia; as funções de dispositivo precisam do lançador Python.

### Diagnóstico

Abra Configurações → Diagnóstico ou Atualizar diagnóstico. A consulta roda em worker
com cache de 15 s (não faz polling de sensores continuamente). Usa fontes reais:

- Modelo: device tree em `/proc/device-tree/model` ou `/sys/firmware/devicetree/base/model`.
- Arquitetura: `platform.machine()`, sistema: `PRETTY_NAME` em `/etc/os-release`.
- Armazenamento: `disk_usage` da unidade onde está a pasta de dados; valores em MiB.
- RAM: `MemTotal`/`MemAvailable` de `/proc/meminfo`.
- Temperatura: zonas térmicas CPU/SoC conhecidas em `/sys/class/thermal`.
- Acervo: pacotes da pasta gerenciada e arquivos de conteúdo; a contagem de documentos
  SQLite soma `count(*)` da tabela `documents` sem ler/exportar seu conteúdo.
- Versão: manifesto do slot selecionado pelo atualizador.
- Última verificação: data, conclusão e contadores; não inclui os nomes de arquivos
  afetados no relatório exportado. Componentes essenciais mostram observações
  básicas, não uma garantia completa de funcionamento.

Arquivos/comandos/sensores ausentes mostram **Não disponível neste ambiente**.
Não é inferido um modelo Raspberry Pi numa VM. O horário observado é ISO 8601 UTC
com offset explícito, independente do relógio/fuso configurado no navegador.

Exportar relatório permite escolher um arquivo no próprio dispositivo. Usa o
seletor nativo do Chromium (File System Access API) e grava o stream; na alternativa
de download, o lançador configura somente `download.prompt_for_download=true`,
preservando as demais preferências do perfil, para solicitar o destino. Valide o
comportamento do seletor na versão real do Chromium do Pi. O JSON contém somente
os campos descritos acima, sem variáveis de ambiente, hostname, caminhos pessoais,
credenciais, textos do SQLite ou conteúdo de anotações. O backup de dados é uma
operação diferente e pode, intencionalmente, conter dados pessoais.

### Verificação do acervo

Pacotes ficam em `$XDG_DATA_HOME/aegis/packages/<pasta>/`. Cada pacote deve trazer
`manifest.json` **da origem**, criado pelo responsável antes da distribuição:

```json
{
  "format": 1,
  "package_id": "identificador",
  "version": "1.0.0",
  "files": {
    "referencia.pdf": {"size": 123, "sha256": "64 caracteres hexadecimais"}
  }
}
```

Os valores no exemplo são ilustrativos; use hashes/tamanhos reais do original.
Limites: 4096 arquivos e 2 MiB de manifesto por pacote. Caminhos relativos sem `..`,
componentes vazios, drives, barras invertidas ou links. A verificação lê em blocos
de 64 KiB, compara tamanho e hash, detecta alterações de inode/tamanho/mtime/ctime,
revê os arquivos já lidos antes de concluir e detecta arquivos não previstos. O
manifesto também é conferido novamente ao final. Cancelar interrompe entre blocos;
a conclusão passa a interrompida/incompleta. Não se apaga nem se repara nada.

Estados:

| Estado | Significado |
| --- | --- |
| Pacote íntegro | Todos os arquivos declarados correspondem e nenhum extra foi encontrado. |
| Ausente | Arquivo esperado não existe. |
| Conteúdo divergente | Tamanho ou SHA-256 difere. |
| Ilegível | O sistema não permitiu ler. |
| Alterado/inseguro | Mudança durante a leitura ou caminho/link não permitido; não aprovado. |
| Sem manifesto verificável | Referência ausente/inválida; não equivale a íntegro. |
| Incompleto/interrompido | A leitura, inventário ou manifesto mudou/falhou ou houve cancelamento. |

Abra os detalhes do pacote para ver arquivos e causas. Pacotes com danos são
indicados para reinstalação. **Não existe instalador/reinstalador de pacotes do
acervo no projeto atual**. A orientação é obter o original e seu manifesto por
canal confiável e solicitar a substituição ao responsável, preservando documentos
pessoais. Não há botão de reparo fictício. O SQLite histórico não tem manifesto de
origem e aparece separadamente como não verificável; não se fabrica uma referência
a partir do banco atual. “Verificação concluída” significa execução terminada,
não aprovação dos pacotes sem referência. Acervo vazio é identificado como vazio.

Autenticidade é uma observação separada. Opcionalmente, o manifesto contém `key_id`
e um `manifest.sig` binário ao lado. A assinatura RSA-PSS SHA-256 (salt=digest) usa
as mesmas chaves públicas externas em `$XDG_CONFIG_HOME/aegis-updater/trusted-keys`
que o atualizador. Sem assinatura: autenticidade não verificada. Chave desconhecida
ou assinatura inválida não se transforma em “autêntico”, mesmo se os hashes
corresponderem. O resultado completo fica em `aegis/integrity-result.json`; o
relatório de diagnóstico exporta apenas resumo sanitizado.

Ferramenta do **publicador** (não usar para certificar uma instalação existente):

```bash
python3 tools/build-collection-manifest.py --source /originais-revisados \
  --output /saida-separada --package-id identificador --version 1.0.0
# Opcional: --private-key /fora-do-repositorio/chave.pem --public-key /chave-publica.pem
```

Distribua o manifesto resultante com aqueles mesmos originais. A ferramenta exige
saída separada, não aceita uma origem que já contém manifesto e nunca é chamada
pela interface para “reparar” integridade. Para chaves, use as instruções de
[atualização](atualizacoes.md); nunca distribua nem registre a chave privada.

### Backup de dados

Configurações → Backups → Criar backup cria um snapshot e libera **Salvar backup**
para escolher o destino. Também está disponível na recuperação. A operação exige
espaço de preparação e reserva de 16 MiB; não é executada silenciosamente.

Incluídos, **quando existem** em `$XDG_DATA_HOME/aegis`:

- `library.sqlite3`, copiado pela API `sqlite3.Connection.backup`, com quick_check.
- `preferences.json`, `favorites.json`, `annotations.json`, `settings.json`, `history.json`.
- Arquivos regulares dentro de `personal/`, preservando subpastas.

Excluídos: slots/lançador, Linux, pacotes do acervo, modelos, perfis do navegador,
chaves, logs, resultados de integridade, arquivos temporários e qualquer outro
caminho não listado. Bancos em outro caminho escolhido por `--db` não são descobertos
automaticamente; organize/copie por processo de backup próprio ou utilize o caminho
padrão documentado. Os favoritos da interface demonstrativa original continuam
em memória; este recurso não inventa persistência para dados que não existiam em
disco. Arquivos persistentes existentes nos locais listados são preservados.

O backup **não é criptografado**. Escolha destino e armazenamento adequados para os
seus dados. Formato `.aegis-backup`: ZIP sem diretórios explícitos, até 128 MiB
compactados/256 MiB expandidos/4096 arquivos, com manifesto v1:

```text
app_id = org.aegis.offline
format = 1; data_format = 1; scope = user-data-v1
app_version = versão instalada; created_at = ISO 8601
origin = origem declarada (não é prova de procedência)
files = mapa de caminhos -> {size, sha256}
```

Hashes conferem a integridade relativa ao manifesto. Não há chave privada no
dispositivo e este backup não afirma autenticidade criptográfica. Selecione somente
backups cuja procedência você conhece. Metadados não são executados como código.
A versão principal do aplicativo e o formato de dados precisam ser compatíveis.
A restauração valida caminhos, links, duplicatas, limites, hashes, JSON de
configuração e SQLite antes de gravar nos dados atuais.

### Recuperação independente e restauração

Com o aplicativo fechado, na mesma configuração XDG:

```bash
python3 aegis-linux/aegis.py --recovery
# Diagnóstico básico mesmo sem interface/sessão gráfica:
python3 aegis-linux/aegis.py --diagnose
```

A pasta `recovery/` é parte do supervisor e não dos slots `app/`. Abertura explícita
não chama o bootstrap nem valida o HTML principal para renderizar a recuperação.
O lançador impede duas instâncias simultâneas. Não abra a recuperação enquanto o
aplicativo principal estiver usando seus dados.

Na recuperação:

1. Consulte diagnóstico e os últimos 100 eventos técnicos controlados. Não se
   exportam logs brutos de terceiros nem conteúdos de variáveis/arquivos pessoais.
2. **Restaurar versão anterior** reutiliza o rollback do atualizador. Troca somente
   o aplicativo na próxima abertura; com preparação pendente, permite cancelá-la.
3. **Selecionar backup** usa o armazenamento local/pendrive montado. Confira nome do
   arquivo, origem declarada, data, versão, formato/alcance, quantidade e tamanho.
4. **Restaurar dados deste backup** pede confirmação. O backend proíbe essa operação
   na interface principal. Antes de sobrescrever qualquer arquivo, cria snapshot
   consistente do estado atual em `aegis-application-updates/safety-backups/<id>.aegis-backup`.
   Sem espaço para essa segurança **e** preparação, interrompe sem sobrescrever.
5. Dados presentes no backup são substituídos; arquivos adicionais atuais ficam
   preservados. Não se removem modelos/pacotes. Uma restauração não repara nem
   reinstala o acervo. Se desejar voltar, selecione o backup de segurança criado.
6. **Abrir aplicativo** exige confirmação; **Sair da recuperação** fecha a janela
   (Alt+F4 também funciona). Não há ciclo automático de reinicialização.

A preparação fica em diretório separado; hashes e tipos são validados novamente.
`restore-journal.json` grava a transação atômica e duravelmente depois do backup de
segurança e antes de modificar dados. Cada destino usa arquivo temporário + fsync +
replace. Os arquivos preparados ficam intactos até terminar: uma interrupção permite
repetir a aplicação inteira de forma idempotente. O próximo lançamento retoma antes
de abrir a interface, ou oferece **Retomar restauração interrompida** na recuperação.
Se a preparação estiver corrompida, não inventa sucesso nem abre a interface sobre
um conjunto parcial: mantenha os arquivos, use a recuperação e a cópia de segurança.
Sem resolver o registro pendente, a abertura normal é bloqueada.

A biblioteca CLI e serviços usam `.data.lock` interprocessos: verificação, gravação
de preferências, snapshots e restauração não se sobrepõem. Ferramentas futuras de
instalação do acervo devem adquirir o mesmo lock antes de substituir um pacote.
Programas externos que ignoram esse protocolo não podem ser coordenados; feche-os.
Journals/WAL/SHM SQLite presentes bloqueiam restauração, sem apagar arquivos auxiliares.
A API de snapshot permite capturar um banco consistente, com limites de tempo/tamanho.

O registro `launch-status.json` diferencia janela encerrada normalmente, prontidão
e execução interrompida. Fechamento normal (inclusive antes da prontidão) não soma
falhas; um trial fechado pelo usuário é adiado. Execução anterior incompleta ou duas
falhas registradas levam à recuperação com motivo explícito. O rollback de trial
é tentado no máximo uma vez na inicialização. Não se reinicia uma sessão saudável.
A recuperação só tenta abrir o aplicativo quando o usuário confirma. Falha do
próprio Chromium/sessão gráfica encerra a tentativa e orienta o diagnóstico CLI.

Limites: supervisor/navegador íntegros, espaço e sistema de arquivos Linux funcional
são pré-requisitos. Não há reparo de cartão SD fisicamente danificado, Linux que
não inicializa, bitrot generalizado, migrações de dados incompatíveis ou escritores
externos não cooperativos. Faça backups externos. Trocar código não desfaz uma
migração de banco; esta versão não realiza migrações clínicas.

### Acessibilidade e atalhos

Configurações → Acessibilidade permite visualizar texto 100/125/150/200%, alto
contraste e efeitos reduzidos. Salvar aplica persistência global; Visualizar padrões
não grava sem Salvar. O CSS alcança biblioteca, calculadora, configurações e diálogos;
a recuperação usa a mesma camada confiável. Telas refluem em texto grande, com
rolagem vertical. Controles têm alvo mínimo de 44 px (checkboxes usam o rótulo),
foco visível e estados textuais. Mouse, teclado e toque são alternativas; não se
presume tela sensível ao toque. Diálogos usam Tab/Shift+Tab contidos, Escape/cancelar,
confirmação explícita e retorno do foco ao controle que abriu.

Configurações → Atalhos gerencia os atalhos da tela inicial: adicionar, remover,
Subir/Descer (também via Tab e Enter/Espaço), Salvar ou restaurar padrões. O catálogo
contém somente IDs implementados; não aceita shell/caminhos. Duplicatas e IDs de
ferramentas removidas são filtrados, mantendo a ordem dos demais. Padrões:
calculadora, diagnóstico, verificação do acervo. Preferências ficam fora dos slots.

`preferences.json` tem formato 1 com `text_size`, `high_contrast`, `reduced_motion`
e `shortcuts`. Gravação atômica sob lock; formato 0 local é migrado para 1; ausência
usa padrões. Conteúdo inválido/versão desconhecida é preservado como
`preferences.problem-<id>.json`, com aviso, sem impedir abertura. JSON é tratado
como dados, sem eval/import/configuração executável.

## Testes e roteiro no Raspberry Pi 2

```bash
python3 -m unittest discover -s tests -v
python3 -m unittest discover -s aegis-linux/tests -v
node --test --test-isolation=none aegis-linux/tests/medication.test.cjs
AEGIS_CHROME=/usr/bin/chromium AEGIS_QA=/tmp/aegis-device-review \
  node aegis-linux/tests/run-browser-qa.cjs
```

Playwright é ferramenta de desenvolvimento; não é dependência do Pi. Testes usam
somente diretórios, bancos, pacotes, chaves e falhas temporários. Rede da Release é
simulada; todas as novas funções trabalham sem internet. A integração já existente
exercita biblioteca/calculadora/atualizador, acrescida de diagnóstico, manifesto,
backup, preferências, atalhos, foco e recuperação com HTML principal danificado.

Validação automatizada em **cloud Linux x86_64/Chromium headless**, não no Raspberry
físico. Inspeção visual: diagnóstico em 390×810; acessibilidade/alto contraste a
200% em 390×800; recuperação em 390×800; verificação de reflow também em 800×800 e
1280×800, além das regressões existentes 1440/1024/390. Capturas são artefatos de QA,
não dados de produção nem evidência de hardware. Testes de lifecycle usam processos
simulados; a janela real do desktop, seletores nativos, atalhos do desktop e
encerramento do Chromium real precisam ser validados no Pi.

Roteiro pendente no Raspberry Pi OS **32-bit / Pi 2 físico**:

1. Instalar cópia isolada do bootstrap 1.1; conferir modelo/arquitetura/OS/RAM/disco
   e comparar temperatura com o sistema, sem privilégios elevados.
2. Verificar acervo original com manifesto de procedência; testar arquivo removido,
   ilegível e alteração em cópia de teste, cancelando arquivos grandes. Medir RAM,
   CPU e tempo. Não danificar o acervo real para testar.
3. Criar backup com SQLite ativo em cópia de dados; conferir consistência, escolher
   pendrive como destino, importar, cancelar e confirmar restauração na recuperação.
4. Simular interrupção em dados descartáveis, retomar o journal, conferir o backup
   de segurança e os documentos extras. Testar cartão/disco sem espaço por simulação
   ou volume de teste, preservando a instalação real.
5. Fechar normalmente durante/depois da abertura, simular crash em cópia de teste,
   conferir motivo da recuperação e ausência de loops. Abrir `--recovery` com
   `app/index.html` de teste danificado; experimentar rollback disponível.
6. Usar somente teclado, depois mouse e, se existir, toque. Conferir texto 200%,
   contraste, calculadora, todos os diálogos, foco, seletores de arquivo/destino,
   reordenação de atalhos e persistência após reiniciar.

Uma Release estável só deve ser considerada após revisão e validação específica no
hardware; esta entrega é código em pull request.
