> **Acervo editorial desta revisão:** sete fichas locais, todas pendentes de revisão
> profissional. Abra `app/index.html` diretamente para ler offline ou use o lançador.
> O catálogo vem de `content/editorial.json`; consulta padrão revisada está vazia e a
> oficina editorial exige escolha explícita. Veja [fontes e geração](../docs/acervo-editorial.md).
> A seção abaixo registra a implementação histórica; os três títulos demonstrativos
> foram substituídos por estas fichas, sem alteração da calculadora.

> **Central de atualizações:** o lançador desta revisão abre a interface existente
> no Chromium da tela do dispositivo por uma ponte Python restrita a 127.0.0.1.
> Não há portal para acesso remoto. O HTML direto continua servindo como prévia.
> Consulte [instalação inicial, pacotes assinados e recuperação](../docs/atualizacoes.md).
> O ZIP antigo não contém o novo formato de atualização. As instruções abaixo
> registram a base histórica; para instalar o atualizador sem substituir a cópia
> antiga, use `python3 aegis.py --install-updater`.

# AEGIS Linux — personalização para Raspberry Pi 2

Base Linux 0.1 • Calculadora 0.2 • Recuperação em 3 de novembro de 2026

Este pacote prepara a interface existente do AEGIS para ser aberta como aplicativo no Linux. O hardware de destino definido pelo usuário é o Raspberry Pi 2. A base recomendada passa a ser Raspberry Pi OS de 32 bits. Ainda não é uma distribuição Linux, imagem ISO ou sistema instalado; não foi executado na placa.

## O que já funciona

- A interface local da biblioteca em grafite, âmbar e azul, com tema claro/escuro conforme a preferência do sistema.
- Pesquisa e filtros nas três referências demonstrativas, navegação por especialidade e referências salvas durante a sessão.
- Ícones locais: somente os desenhos utilizados, sem carregar o catálogo JavaScript completo do Lucide. Não há fontes, bibliotecas ou conteúdo baixados durante o uso da interface.
- Lançador Python que abre Chromium/Chrome em janela própria ou tela cheia, com perfil separado.
- Instalação por usuário e opção de início após login via XDG Autostart.

Os textos e a navegação da proposta anterior foram preservados. Os títulos são exemplos; não há livros, respostas de IA, busca em texto integral ou referências reais integrados. As marcações de salvos são temporárias e se perdem ao recarregar. A abertura de referências e o guia demonstram a interação planejada.

## Calculadora já implementada

O botão **Calculadora** abre o módulo offline para adultos e pediatria. Ele aceita dose prescrita em mg/dose, mg/kg/dose ou mg/kg/dia, calcula o total em 24 horas e converte para mL quando os dois campos de concentração são informados. O modo manual confere aritmética, sem verificar limites clínicos.

O modo de referências contém os três medicamentos já presentes nos arquivos recuperados: paracetamol oral (MSF, atualização declarada em outubro de 2024), ibuprofeno oral (MSF, atualização não informada na página) e cetirizina oral (NHS, revisão em 18/02/2025). A data de consulta cadastrada é 03/11/2026. Os links, indicações, precauções e regras de escopo aparecem na própria interface. Nenhuma dose clínica foi criada ou modificada nesta publicação.

O módulo bloqueia dados inválidos, condições especiais no modo de referência e esquemas acima dos limites cadastrados, sem reduzir doses automaticamente. Não grava dados de pacientes. Continua sendo protótipo para revisão profissional antes de uso clínico.

## Atualização da cópia instalada

Este repositório contém a calculadora; o ZIP anterior citado na conversa não a continha. Baixar o repositório não modifica a instalação da VM. Para conferir a versão recuperada antes de substituir qualquer instalação, extraia em uma nova pasta e execute `python3 aegis.py` nela. A opção `--install` não sobrescreve arquivos existentes; o autostart continua apontando para a cópia previamente instalada. Não há comando automático de atualização nesta versão.

## Ver agora, inclusive no Windows

Abra **app/index.html** em um navegador. Não é preciso instalar o pacote nem iniciar um servidor. O modelo 3D e seu layout de origem não foram modificados.

## Testar no Linux

Requisitos: sessão gráfica, Python 3.9 ou superior e Chromium/Chrome no PATH. A interface foi testada no Chrome no Windows; a instalação e o início em um desktop Linux ainda precisam de validação no equipamento real.

Depois de extrair este pacote, abra um terminal na pasta que contém `aegis.py`:

```bash
python3 aegis.py --check
python3 aegis.py
```

Para tela cheia:

```bash
python3 aegis.py --kiosk
```

Use **Alt+F4** para fechar a janela do AEGIS e voltar ao desktop. O modo tela cheia é uma apresentação da interface, não um bloqueio de segurança do computador.

## Instalar o atalho no Linux

```bash
python3 aegis.py --install
```

Execute como usuário comum, sem `sudo`. A instalação copia a interface para `$XDG_DATA_HOME/aegis-prototipo` (normalmente `~/.local/share/aegis-prototipo`) e cria um atalho no menu de aplicativos. Não instala dependências. Se já houver arquivos do pacote no destino, a operação para sem substituí-los.

O lançador cria um perfil exclusivo para o navegador ao abrir o aplicativo, no diretório `aegis-prototipo-perfil` ao lado da instalação. Este protótipo não desativa a sandbox do navegador, não muda discos, kernel, rede ou login automático.

## Abrir automaticamente após login

Para desktops compatíveis com XDG Autostart, após instalar:

```bash
python3 aegis.py --enable-autostart
```

Para desfazer:

```bash
python3 aegis.py --disable-autostart
```

Isso cria/remove apenas a entrada XDG deste protótipo. O disparo ocorre quando o usuário entra no desktop; não configura login automático nem inicia serviços antes do login.

**Raspberry Pi OS com labwc:** o tutorial oficial orienta usar `~/.config/labwc/autostart`. Após instalar, o arquivo `inicio-labwc.txt` dentro da pasta instalada contém uma linha pronta para acrescentar ao final desse arquivo, preservando o conteúdo existente. Escolha um único mecanismo de inicialização para evitar aberturas duplicadas. Remova essa mesma linha para desfazer o início via labwc; `--disable-autostart` atua somente sobre XDG.

## Base para Raspberry Pi 2

Use **Raspberry Pi OS (32-bit)**. A família Pi 2 tem 1 GB de RAM e diferentes revisões de processador: a revisão 1.1 usa Cortex-A7; as revisões 1.2 e 1.3 usam Cortex-A53. A imagem de 32 bits é a base comum escolhida para o projeto, sem depender da revisão da placa. A recomendação anterior de 64 bits para Pi 5 foi substituída.

Para testar este pacote, a edição **com desktop** fornece sessão gráfica e navegador. Para uma versão enxuta do equipamento, a proposta é partir de **Raspberry Pi OS Lite (32-bit)** e acrescentar apenas a sessão gráfica e o navegador necessários. Lite sozinho não abre esta interface; essa preparação ainda não está automatizada neste pacote. A escolha entre os ambientes gráficos deverá ser testada na placa.

Com 1 GB de RAM, mantenha uma única janela AEGIS. A prioridade será consulta ao acervo, metadados, favoritos e busca textual local. O navegador provavelmente será um dos maiores consumidores de memória; ainda precisamos medir consumo de RAM, tempo de abertura e leitura dos documentos no Pi 2. Reduzir o JavaScript dos ícones é uma otimização do pacote, não uma garantia de fluidez no hardware.

IA generativa local de uso geral não integra esta configuração. A proposta é começar com pesquisa convencional e conteúdo previamente indexado; modelos de linguagem exigiriam avaliação separada de recursos e desempenho. O guia atual continua sendo apenas demonstrativo.

O Pi 2 tem Ethernet de 100 Mb/s e quatro portas USB 2.0, sem Wi-Fi integrado. Compartilhar o acervo por Wi-Fi exigirá adaptador compatível ou roteador/ponto de acesso externo. A leitura local pela tela não depende dessa rede.

O modelo mecânico anterior usa um volume de referência do Pi 5. Este pacote corrige o alvo do software; ainda será necessário revisar posição dos conectores, alimentação e fixações do Pi 2 no projeto mecânico.

O encaixe representado da NVIDIA Quadro não confirma compatibilidade de drivers ou aceleração no Raspberry Pi. Este pacote não instala nem depende da GPU dedicada.

## Próximas decisões e entregas

1. Identificar a revisão do Raspberry Pi 2, o cartão/armazenamento e eventual Linux já instalado. Se houver Linux, `cat /proc/device-tree/model` informa o modelo e `cat /etc/os-release` identifica a distribuição.
2. Testar lançador, resolução da tela, teclado, trackpad e início após login no equipamento.
3. Integrar o acervo real, seus metadados, origem e permissões de uso; persistir favoritos.
4. Implementar pesquisa textual local com índices preparados previamente; medir desempenho com o acervo real.
5. Personalizar desktop, inicialização visual, energia e atualizações; gerar imagem reproduzível somente após validar a base.

Rede Wi-Fi compartilhada, IA local, monitoramento da bateria, dados de pacientes, instalação de sistema e imagem de recuperação não fazem parte desta versão.

## Fontes técnicas

- [Raspberry Pi 2: especificações e revisões](https://www.raspberrypi.com/products/raspberry-pi-2-model-b/)
- [Hardware Raspberry Pi: conectividade por modelo](https://www.raspberrypi.com/documentation/computers/raspberry-pi.html)
- [Imagens oficiais e compatibilidade de 32 bits](https://www.raspberrypi.com/software/operating-systems/)
- [Raspberry Pi OS: edições e arquiteturas](https://www.raspberrypi.com/documentation/computers/os.html)
- [Modo kiosk no Raspberry Pi e inicialização labwc](https://www.raspberrypi.com/tutorials/how-to-use-a-raspberry-pi-in-kiosk-mode/)
- [Desktop Application Autostart Specification](https://specifications.freedesktop.org/autostart/latest/)
- [Desktop Entry Specification — Exec](https://specifications.freedesktop.org/desktop-entry/latest-single/)

O arquivo `origem.json` registra o SHA-256 do layout reaproveitado. A licença dos ícones Lucide está em `app/vendor/LICENSE-lucide`.
