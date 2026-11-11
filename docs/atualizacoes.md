> O acervo editorial inicial agora gera `app/catalog-data.js` a partir de uma única
> fonte, conforme [documentação editorial](acervo-editorial.md). Esse recurso estático
> acompanha a interface e será incluído pelo builder de aplicativo; seu conteúdo
> permanece explicitamente pendente de revisão profissional. Pacotes externos do
> acervo, documentos pessoais e modelos continuam fora do atualizador. Revisar também
> o diff editorial antes de distribuir qualquer novo payload; não publicar fichas
> pendentes como conteúdo assistencial revisado.

> O supervisor desta revisão é 1.1.0 e acrescenta serviços offline e recuperação
> independente. Consulte [as ferramentas do dispositivo](ferramentas-dispositivo.md)
> para backup de dados, manifestos do acervo, acessibilidade e atalhos. O código do
> supervisor continua fora dos payloads e exige instalação explícita por canal confiável.

# Central de atualizações do AEGIS

Esta implementação é uma proposta de código para revisão. Não publica uma Release,
não atualiza um Raspberry Pi e não configura uma chave de produção automaticamente.
A base local identifica-se como `0.2.0`; isso **não** significa que exista uma Release
estável dessa versão no GitHub. As versões `0.3.0` dos testes são descartáveis.

## Arquitetura e escopo

O aplicativo da tela do dispositivo continua usando **Chromium/Chrome como motor de
interface**, aberto por Python em janela `--app` ou `--kiosk`. A biblioteca e a
calculadora existentes foram preservadas. Não é um navegador para consultar um
portal remoto. A mudança de `file://` para uma ponte HTTP em **127.0.0.1, porta
efêmera**, permite comunicação com o lançador e seleção de arquivos pelo próprio
Chromium no dispositivo. Não há escuta em Ethernet/Wi-Fi, anúncio de serviço ou
portal para outros computadores/celulares. A API exige token aleatório por sessão,
Host exato e Origin local nas mutações; não habilita CORS. A janela mantém a sandbox
do navegador. Somente Python consulta a internet, por ação do usuário.

O payload atualizável v1 é `app/`: interface, calculadora e recursos locais do
aplicativo. O supervisor de confiança (`aegis.py`, `updater.py`, `update_bridge.py`)
fica **fora dos slots recebidos**. Não há scripts de instalação, hooks ou migrações
nos pacotes; não são aceitos arquivos Python/shell/binários. Uma mudança do próprio
supervisor exige uma nova instalação explícita do bootstrap por canal confiável.
O campo `min_updater` bloqueia payloads que dependam de uma capacidade mais nova.
A biblioteca Python de terminal continua independente; seu banco não é reimportado
ou modificado pelo atualizador da interface Linux.

Linux/kernel, conteúdo do acervo e modelos de IA **não** são atualizados. Os
cadastros demonstrativos da calculadora são código do aplicativo: mudanças neles
exigem revisão profissional antes de uma Release. Não há validação clínica implícita.

Operações demoradas usam worker único, E/S em blocos de 64 KiB e consulta de progresso
a cada 400 ms somente enquanto há uma tarefa. A memória/tempo real no Pi 2 ainda
precisam ser medidos.

## Primeira instalação com o atualizador

Requisitos: Linux, usuário comum, sessão gráfica, Python **3.9+**, módulo SQLite,
Chromium/Chrome no PATH e **OpenSSL 1.1.1+ com RSA-PSS/SHA-256** (OpenSSL 3 recomendado).
Node.js/Playwright são apenas ferramentas de teste, não dependências do dispositivo.
Não é preciso `sudo` para instalar o AEGIS. Instale pré-requisitos pelo procedimento
normal da sua distribuição, se faltarem.

Depois da revisão/merge, obtenha a versão que contém este código por um canal de
confiança e confira sua procedência. No checkout, para testar sem substituir a
instalação anterior:

```bash
python3 aegis-linux/aegis.py --check
python3 aegis-linux/aegis.py
```

Para criar uma cópia e um atalho **separados** da instalação antiga:

```bash
python3 aegis-linux/aegis.py --install-updater
python3 "${XDG_DATA_HOME:-$HOME/.local/share}/aegis-updater/aegis.py"
```

`--install-updater` usa `aegis-updater/` e `applications/aegis-updater.desktop`
dentro de `$XDG_DATA_HOME` (padrão `~/.local/share`). Recusa sobrescrever ambos. Uma cópia deste guia é incluída como `ATUALIZACOES.md`.
O antigo `aegis-prototipo/`, atalho e autostart ficam preservados. Para mudar um
autostart antigo, revise manualmente a entrada existente para apontar ao novo
lançador; não habilite os dois. `--enable-autostart` histórico continua atuando
sobre a instalação antiga `aegis-prototipo`, não sobre a nova cópia separada.
A opção `--install` ainda funciona em uma instalação nova e também recusa sobrescrita.
O acesso a atualizações só existe ao abrir pelo novo lançador; abrir o HTML
diretamente mostra uma prévia com instalação desabilitada.

A instalação inicial é a raiz de confiança: o código e a chave devem ser obtidos e
conferidos fora de um pacote desconhecido. O antigo
`downloads/AEGIS-Linux-atualizado.zip` **não atende ao formato** e será rejeitado.

## Chave pública confiável

Nenhuma chave de produção foi criada ou embutida. Sem uma chave configurada, a tela
informa o bloqueio e nenhum pacote pode ser instalado. O responsável deve gerar uma
chave RSA **3072 ou 4096 bits** em uma máquina de assinatura, fora do repositório,
com permissões restritas (preferencialmente chave criptografada e backup seguro):

```bash
umask 077
mkdir -p "$HOME/aegis-signing"
openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:3072 \
  -aes-256-cbc -out "$HOME/aegis-signing/release-private.pem"
openssl pkey -in "$HOME/aegis-signing/release-private.pem" -pubout \
  -out "$HOME/aegis-signing/release-public.pem"
```

O comando de assinatura solicita a senha da chave criptografada no terminal de
publicação. Não passe a senha em argumentos nem salve em scripts ou logs. Nunca
copie a chave privada para o dispositivo, payload, checkout ou GitHub. A ferramenta
recusa chave privada localizada dentro deste repositório. Os testes geram chaves
não criptografadas **apenas em diretórios temporários**, apagados ao terminar.

Distribua **somente a chave pública**, confirmando sua impressão digital por canal
independente. No dispositivo, depois dessa conferência:

```bash
trust="${XDG_CONFIG_HOME:-$HOME/.config}/aegis-updater/trusted-keys"
mkdir -p "$trust"
# Este hash identifica os bytes PEM exatos; não reformatar o PEM depois da conferência.
id=$(sha256sum /caminho/confiavel/release-public.pem | cut -d' ' -f1)
cp /caminho/confiavel/release-public.pem "$trust/$id.pem"
```

A assinatura é verificada exclusivamente contra esse diretório externo ao payload.
O `key_id` recebido escolhe uma chave já confiável, nunca importa uma chave. Troca
ou revogação exige provisionamento explícito nesse diretório; não há rotação
silenciosa pelo pacote. Uma chave desconhecida, removida ou assinatura adulterada
bloqueia a instalação. Hashes internos sozinhos não provam autenticidade.

## Criar, assinar e publicar

Execute testes e revisão antes de escolher uma **nova versão estável**. Prepare
notas de mudanças e uma data real de publicação. Exemplo de comando (substitua os
valores; não publicar as versões de teste):

```bash
python3 tools/build-update.py \
  --version "$VERSAO_ESTAVEL" --date "$DATA_ISO" --notes /caminho/notas.txt \
  --private-key "$HOME/aegis-signing/release-private.pem" \
  --public-key "$HOME/aegis-signing/release-public.pem" \
  --architectures armv7l --output /caminho/artefatos
```

O builder seleciona explicitamente os arquivos de `aegis-linux/app`, ordena a lista,
fixa timestamps ZIP, produz JSON canônico e assina os bytes exatos do manifesto.
RSA-PSS usa sal aleatório: assinaturas/ZIPs de duas execuções não são byte a byte
iguais; os hashes dos arquivos e o conteúdo do manifesto são reproduzíveis. Ele
confere correspondência das chaves e não substitui um pacote de saída existente.
Saídas:

- `aegis-VERSAO.aegis-update`: o mesmo pacote para internet e pendrive.
- `aegis-VERSAO.manifest.json`: manifesto externo para auditoria.
- `aegis-VERSAO.manifest.sig`: assinatura externa para auditoria.

Publique esses arquivos numa **Release oficial** de `leoulson/AEGIS`, com tag
`vVERSAO` (ou `VERSAO`), nunca marcada como draft/prerelease após validação. O
cliente usa `/repos/leoulson/AEGIS/releases/latest`, que seleciona Releases estáveis,
não a branch `main`. A tag, o nome do asset e a versão assinada têm de coincidir.
Se não houver Release ou asset no novo formato, a tela informa isso. Não foi criada
uma Release por esta tarefa. Validar o asset final baixado e sua assinatura em uma
instalação de teste antes de anunciar a versão no hardware.

HTTPS mantém a verificação TLS. Downloads aceitam somente GitHub oficial e redirects
HTTPS para `release-assets.githubusercontent.com`; limite de pacote 48 MiB,
timeout de socket 15 s, prazo total de 120 s verificado entre leituras. Uma leitura
em curso pode acrescentar até o timeout de socket. Limite da resposta da API:
512 KiB. Em redes restritas, os destinos são `api.github.com`, `github.com` e
`release-assets.githubusercontent.com`. A instalação offline não consulta esses hosts.

## Formato `aegis-update`, versão 1

ZIP com entradas **regulares**, sem diretórios explícitos:

```text
manifest.json
manifest.sig
app/index.html
app/medication-core.js
app/medication-ui.js
app/updates.js
app/updates.css
app/vendor/icons.js
...demais recursos declarados de app/
```

Exemplo de estrutura (hash/ID ilustrativos devem ser substituídos pelo builder):

```json
{
  "app_id": "org.aegis.offline",
  "format": 1,
  "version": "MAJOR.MINOR.PATCH",
  "min_updater": "1.0.0",
  "systems": ["Linux"],
  "architectures": ["armv7l"],
  "released_at": "YYYY-MM-DD",
  "notes": "Mudanças desta versão",
  "key_id": "SHA256 dos bytes do PEM público previamente confiável",
  "files": {
    "app/index.html": {"sha256": "SHA256 hexadecimal", "size": 123}
  }
}
```

`manifest.sig` é a assinatura binária RSA-PSS SHA-256, salt length = digest (32
bytes), sobre os bytes UTF-8 exatos de `manifest.json`. O cliente não recanonicaliza
antes de verificar. Campos JSON duplicados e campos desconhecidos são rejeitados.
São aceitas versões numéricas estáveis de três componentes, sem prerelease, sem
zeros à esquerda; instalação normal exige versão maior que a instalada. Restauração
usa somente um slot local anterior validado.

Limites adicionais: manifesto 256 KiB, assinatura 1024 bytes, 512 arquivos de
payload, 96 MiB expandidos incluindo metadados. Extensões permitidas:
HTML/JS/CSS/SVG/PNG/WebP/ICO/WOFF2 e a licença Lucide conhecida. Todo arquivo exige
caminho, SHA-256 e tamanho declarado; nenhum arquivo extra é aceito. São rejeitados
caminhos absolutos, componentes vazios/`.`/`..`, barras invertidas, drives Windows,
caracteres de controle, links, entradas duplicadas, compressões diferentes de
STORE/DEFLATE e criptografia ZIP. A extração manual escreve apenas arquivos já
validados em um diretório novo; `extractall` não é usado.

## Uso pela tela do dispositivo

Abra **Configurações → Atualizações** no AEGIS.

- **Internet:** Verificar atualizações consulta a Release estável e baixa o asset
  para conferência. Isso não instala. Veja versão, data, notas assinadas, tamanho,
  arquiteturas/sistema e versão mínima do atualizador. Escolha Instalar esta
  atualização e confirme na própria tela.
- **Arquivo:** copie o `.aegis-update` para armazenamento local ou pendrive montado.
  Importar pacote de atualização abre o seletor do dispositivo. A validação é
  idêntica à online e não requer rede. Confira os detalhes e confirme a instalação.
- **Aplicação:** aguarde a preparação terminar. Feche o AEGIS e abra pelo mesmo
  lançador quando desejar. Não há reinício automático durante uma sessão saudável.
- **Restauração:** Restaurar versão anterior prepara a troca para o slot anterior.
  Confirme e feche/abra o aplicativo. Se houver uma preparação pendente, o botão
  passa a Cancelar atualização pendente, preservando a versão atual.

Falhas aparecem na tela; um pacote rejeitado nunca vira candidato instalável. A
prévia da Release não é inventada quando a consulta falha. Mensagens de notas são
texto, não HTML executável. O sistema só trabalha com um candidato por sessão.

## Persistência, ativação e recuperação

Dentro de `$XDG_DATA_HOME` (padrão `~/.local/share`):

```text
aegis-updater/                     bootstrap instalado explicitamente
aegis-application-updates/
  update.lock                     flock interprocessos de mutação
  application.lock                impede duas instâncias do lançador
  state.json                      current / previous / pending / trial
  versions/<id-aleatorio>/app/     payloads imutáveis durante o uso
  versions/<id>/manifest.json
  session-*/                      candidato temporário, apagado ao encerrar
```

Não há banco de pacientes, acervo ou modelos nessas versões. O SQLite existente em
`~/.local/share/aegis/library.sqlite3`, arquivos pessoais, perfil Chromium em
`aegis-prototipo-perfil/` e instalações anteriores permanecem fora dos slots. O
protótipo gráfico ainda usa favoritos **temporários em memória**; a atualização não
cria persistência nem migra favoritos que não existiam em disco. O mecanismo não
apaga favoritos/anotações/configurações/histórico/modelos que estejam nos seus
locais persistentes. Não coloque dados pessoais dentro de `versions/`: esse local
é reservado a código gerenciado.

A preparação revalida o pacote inteiro sob `flock`, verifica espaço (pacote + bytes
expandidos + reserva de 16 MiB; a importação/download reserva o limite expandido),
escreve um slot novo, confere hashes novamente e faz `fsync` dos arquivos e
subdiretórios. Só então grava `pending` por arquivo temporário + `os.replace` +
`fsync` do diretório. Falha antes do commit mantém a versão atual. Falha depois de
um commit durável preserva um estado completo. Partições precisam suportar esses
primitivos (recomendado sistema de arquivos Linux local como ext4).

Na próxima abertura, o supervisor verifica o slot pendente e troca os ponteiros
num único estado atômico. Marca `trial` antes de iniciar Chromium. A interface
confirma carregamento da biblioteca/calculadora e ausência de erros JS de startup
em até 30 s. Ausência de confirmação ou encerramento inesperado antes dela mantém
`trial`; a próxima tentativa recupera a versão anterior. O lançador faz no máximo
uma tentativa automática de recuperação **somente nessa fase de inicialização**.
Arquivos preparados corrompidos também preservam/recuperam a versão anterior. A
central exibe o motivo da recuperação. Um slot que falhou não é oferecido como
versão anterior saudável. Slots sem referência são removidos na próxima abertura
ou preparação, mantendo current/previous/pending; dados externos não são percorridos.

A confirmação de startup não comprova todas as funções nem detecta bugs tardios.
Para isso existe restauração manual. Sem versão anterior válida, falhas do
bootstrap/navegador exigem reparo explícito por canal confiável. `fsync` e troca
atômica reduzem riscos, mas não protegem contra defeito/corrupção do cartão SD,
firmware que ignore flushes, disco avariado ou alteração por processos do mesmo
usuário. Faça backups externos dos dados.

**Não há migrações de dados nesta versão.** Futuras migrações precisam de backup e
compatibilidade reversa própria: trocar código não desfaz uma migração destrutiva.
Uma assinatura comprova origem/integridade, não a qualidade ou segurança clínica.

## Verificações reproduzíveis

```bash
python3 -m unittest discover -s tests -v
python3 -m unittest discover -s aegis-linux/tests -v
node --test --test-isolation=none aegis-linux/tests/medication.test.cjs
AEGIS_CHROME=/usr/bin/chromium node aegis-linux/tests/run-browser-qa.cjs
```

O último comando requer Playwright instalado no ambiente de desenvolvimento
(`AEGIS_PLAYWRIGHT` pode apontar a uma instalação existente). Usa bridge, chaves e
pacotes de teste em diretórios temporários. A rede GitHub é simulada; requisições
do navegador fora do loopback são bloqueadas. A suíte antiga continua testando
biblioteca, busca, filtros, guia, fontes, favoritos e cálculos; acrescenta central,
falta de chave/rede/Release, falha de download, importação offline, prévia online,
confirmação/cancelamento, preparação adiada, cancelamento da preparação, CSRF,
navegação de volta e layout em 1440/1024/390 px. O teste direto de arquivo ainda
pode ser executado com `node aegis-linux/tests/verify-interface.cjs` em um navegador
que permita `file://`.

Os testes Python cobrem assinatura válida/inválida/chave desconhecida, hashes,
truncamento, formatos/versões/arquiteturas, travessia/links/duplicatas/expansão,
espaço insuficiente, falhas de rede, concorrência entre processos, falhas de
preparação e ativação simuladas, perda de energia antes da confirmação, corrupção
do slot, restauração e preservação de arquivos pessoais. Nada usa a instalação
real para simular destruição.

Validação realizada no ambiente cloud **Linux x86_64**, com Chromium headless;
**não** em Raspberry Pi 2 físico. Ainda faltam: chave de produção provisionada,
Release estável revisada/assinada, teste de instalação em Raspberry Pi OS 32-bit,
seletor de pendrive, sandbox, inicialização gráfica/autostart, medição de RAM/CPU,
tempo de abertura, espaço em cartão real e testes controlados de queda de energia.
