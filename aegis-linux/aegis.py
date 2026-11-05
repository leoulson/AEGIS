#!/usr/bin/env python3
"""AEGIS: on-device Chromium launcher and signed update supervisor."""
import argparse
import json
import os
from pathlib import Path
import platform
import shlex
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
APP_ID = "aegis-prototipo"
BROWSERS = ("chromium", "chromium-browser", "google-chrome", "google-chrome-stable")


def locations():
    data = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local/share")
    config = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    if not data.is_absolute() or not config.is_absolute():
        raise RuntimeError("XDG_DATA_HOME e XDG_CONFIG_HOME devem ser caminhos absolutos.")
    return data / APP_ID, data / "applications" / (APP_ID + ".desktop"), config / "autostart" / (APP_ID + ".desktop")


def browser_path():
    return next((path for name in BROWSERS if (path := shutil.which(name))), None)


def require_linux():
    if platform.system() != "Linux":
        raise RuntimeError("Execute esta operação no Linux. No Windows, abra app/index.html para ver a interface.")
    if os.geteuid() == 0:
        raise RuntimeError("Execute com seu usuário normal, sem sudo.")


def desktop_arg(value):
    """Escape an Exec argument at the Desktop Entry string and quoting levels."""
    value = str(value)
    if any(ord(c) < 32 for c in value):
        raise RuntimeError("Caminho com caractere de controle não suportado.")
    value = value.replace("%", "%%")
    escaped = "".join("\\" + c if c in '\\"`$' else c for c in value)
    return '"' + escaped.replace("\\", "\\\\") + '"'


def desktop_entry(root, kiosk=False):
    args = [sys.executable, str(root / "aegis.py")]
    if kiosk:
        args.append("--kiosk")
    return ("[Desktop Entry]\nType=Application\nName=AEGIS — Protótipo\n"
            "Comment=Biblioteca AEGIS: interface de demonstração local\n"
            "Exec=" + " ".join(desktop_arg(arg) for arg in args) + "\n"
            "Icon=accessories-dictionary\nTerminal=false\nCategories=Education;\n"
            "X-AEGIS-Prototype=true\n")


def install(managed=False):
    require_linux()
    if not browser_path():
        raise RuntimeError("Chromium/Chrome não encontrado. Instale o navegador pelo gerenciador da sua distribuição.")
    target, menu, _ = locations()
    if managed:
        target = target.with_name("aegis-updater")
        menu = menu.with_name("aegis-updater.desktop")
    if target.exists() or target.is_symlink() or menu.exists() or menu.is_symlink():
        raise RuntimeError("Já existem arquivos de instalação AEGIS. Nada foi substituído.")
    entry = desktop_entry(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(ROOT / "app", target / "app")
    for filename in ("aegis.py", "updater.py", "update_bridge.py", "LEIA-ME.md", "origem.json"):
        shutil.copy2(ROOT / filename, target / filename)
    guide = ROOT / "ATUALIZACOES.md"
    if not guide.is_file():
        guide = ROOT.parent / "docs" / "atualizacoes.md"
    if guide.is_file():
        shutil.copy2(guide, target / "ATUALIZACOES.md")
    menu.parent.mkdir(parents=True, exist_ok=True)
    with menu.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(entry)
    command = shlex.join([sys.executable, str(target / "aegis.py"), "--kiosk"]) + " &\n"
    (target / "inicio-labwc.txt").write_text(command, encoding="utf-8")
    print("Instalado para o usuário atual:", target)
    print("Abra AEGIS — Protótipo no menu de aplicativos.")
    print("A inicialização automática permanece desativada.")


def autostart(enable):
    require_linux()
    target, _, entry = locations()
    if entry.is_symlink():
        raise RuntimeError("A entrada de inicialização é um link simbólico; nada foi alterado.")
    if enable:
        if not (target / "aegis.py").is_file():
            raise RuntimeError("Execute --install antes de ativar a inicialização automática.")
        if entry.exists():
            raise RuntimeError("Já existe uma entrada de inicialização AEGIS; nada foi substituído.")
        content = desktop_entry(target, kiosk=True)
        entry.parent.mkdir(parents=True, exist_ok=True)
        with entry.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
        print("Entrada XDG criada:", entry)
        print("Será usada após login em desktops compatíveis com XDG Autostart.")
    elif entry.exists():
        if "X-AEGIS-Prototype=true" not in entry.read_text(encoding="utf-8").splitlines():
            raise RuntimeError("A entrada não foi identificada como deste protótipo; nada foi removido.")
        entry.unlink()
        print("Inicialização XDG do protótipo desativada.")
    else:
        print("Não há entrada XDG deste protótipo para desativar.")


def command(root, browser, kiosk, profile, url=None):
    entry = root / "app/index.html"
    if not entry.is_file():
        raise RuntimeError("Interface app/index.html não encontrada.")
    url = url or entry.as_uri()
    args = [browser, "--user-data-dir=" + str(profile), "--no-first-run", "--no-default-browser-check"]
    if kiosk:
        args += ["--kiosk", url]
    else:
        args += ["--app=" + url, "--start-maximized"]
    return args


def launch(kiosk):
    require_linux()
    if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        raise RuntimeError("Abra este lançador dentro da sessão gráfica do Linux.")
    browser = browser_path()
    if not browser:
        raise RuntimeError("Chromium/Chrome não encontrado no PATH.")
    target, _, _ = locations()
    profile = target.parent / (APP_ID + "-perfil")
    from updater import Manager, UpdateError
    from update_bridge import Bridge
    import fcntl
    import time
    data = target.parent
    config = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    manager = Manager(data / "aegis-application-updates", config / "aegis-updater" / "trusted-keys", ROOT)
    with (manager.home / "application.lock").open("a") as session:
        try:
            fcntl.flock(session, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise UpdateError("O AEGIS já está aberto. Feche a outra janela antes de iniciar.")
        manager.bootstrap()
        profile.mkdir(parents=True, exist_ok=True)
        # At most one automatic recovery, only during failed startup (never during use).
        for attempt in range(2):
            root = manager.boot()
            bridge = Bridge(manager, root)
            url = bridge.start()
            process = None
            try:
                process = subprocess.Popen(command(ROOT, browser, kiosk, profile, url))
                deadline = time.monotonic() + 30
                while not bridge.ready.wait(0.1):
                    if process.poll() is not None or time.monotonic() > deadline:
                        break
                if bridge.ready.is_set():
                    return process.wait()
                if not manager.state()["trial"]:
                    raise UpdateError("A interface não confirmou a inicialização. Confira Chromium/sessão gráfica e o registro de recuperação.")
            finally:
                if process is not None and process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
                bridge.close()
            # Unconfirmed trial remains recorded. boot() restores previous on next pass.
        raise UpdateError("Falha na inicialização. Abra novamente para recuperar a versão anterior.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--check", action="store_true", help="Diagnóstico sem alterar arquivos")
    group.add_argument("--install-updater", action="store_true", help="Instala a primeira versão com atualizador em pasta/atalho separados, preservando a instalação antiga")
    group.add_argument("--install", action="store_true", help="Instala o protótipo para o usuário atual")
    group.add_argument("--enable-autostart", action="store_true", help="Ativa início após login via XDG")
    group.add_argument("--disable-autostart", action="store_true", help="Desativa início via XDG")
    group.add_argument("--kiosk", action="store_true", help="Abre em tela cheia; Alt+F4 para sair")
    args = parser.parse_args()
    if args.check:
        report = {"sistema": platform.system(), "arquitetura": platform.machine(),
                  "python": platform.python_version(), "navegador": browser_path(),
                  "sessao_grafica_linux": bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")),
                  "interface_encontrada": (ROOT / "app/index.html").is_file(),
                  "estado": "Protótipo de interface; acervo e IA não conectados"}
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.install or args.install_updater:
        install(managed=args.install_updater)
    elif args.enable_autostart or args.disable_autostart:
        autostart(args.enable_autostart)
    else:
        return launch(args.kiosk)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (RuntimeError, OSError) as error:
        print("AEGIS:", error, file=sys.stderr)
        sys.exit(1)
