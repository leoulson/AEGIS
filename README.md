# AEGIS

**A conexão cai. O conhecimento permanece.**

![Identidade visual](docs/assets/aegis-banner.svg)

Protótipo experimental de biblioteca de conhecimento em saúde **offline-first** para **Raspberry Pi 2**. **v0.1.0 — não validado clinicamente.**

## Objetivo
Preservar localmente acesso a materiais educativos e referências em saúde em contextos de conectividade instável. A aplicação executa no Linux do Raspberry Pi, **sem navegador, nuvem ou serviço web**.

Site de divulgação (independente do aplicativo): https://aegis-offline.leoulson.chatgpt.site

## Galeria visual

### Conceito tridimensional do hardware
![Estudo 3D isométrico do gabinete AEGIS](docs/assets/aegis-hardware-concept.svg)

*Ilustração isométrica conceitual, não arquivo CAD/STL. Medidas, conectores, energia e ventilação ainda precisam ser validados.*

### Arquitetura técnica
![Fluxo de dados local](docs/assets/aegis-architecture.svg)

## Funcionalidades da versão 0.1.0
- Importar catálogo JSON local para SQLite.
- Buscar documentos por título, categoria ou texto.
- Ler conteúdo pelo terminal sem conexão à internet.
- Executar testes automatizados com a biblioteca padrão Python.

## Executar no Raspberry Pi 2 ou Linux
Requer Python 3 com módulo SQLite (biblioteca padrão).

```bash
git clone https://github.com/leoulson/AEGIS.git
cd AEGIS
python3 -m aegis init
python3 -m aegis search offline
python3 -m aegis read welcome
python3 -m unittest discover -s tests -v
```

Banco padrão: `~/.local/share/aegis/library.sqlite3`. Opcionalmente, use `python3 -m aegis --db /caminho/banco.sqlite3 init`. Somente o clone inicial precisa da internet.

## Estrutura
```text
aegis/           aplicação de terminal
content/         dados demonstrativos
docs/assets/     identidade visual, arquitetura e hardware conceitual
tests/           testes automatizados
```

## Limites e próximos passos
Não estão implementados: imagem Linux customizada, interface gráfica, rede Wi-Fi local, mapas offline, bateria, sincronização, recursos de IA, biblioteca clínica curada ou arquivo CAD imprimível. Os próximos passos são testar em Raspberry Pi 2 físico, medir desempenho e alimentação, construir um projeto mecânico dimensionado e definir processo de curadoria e licenciamento da literatura.

**Aviso:** conteúdo exclusivamente demonstrativo. O AEGIS não é dispositivo médico, não oferece diagnóstico, triagem ou prescrição. Materiais clínicos futuros exigem avaliação e atualização editorial.

Código sob licença MIT. Elementos visuais são conceituais.
