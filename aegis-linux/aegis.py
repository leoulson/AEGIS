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
    for filename in ("aegis.py", "updater.py", "update_bridge.py", "device_services.py", "LEIA-ME.md", "origem.json"):
        shutil.copy2(ROOT / filename, target / filename)
    shutil.copytree(ROOT / "recovery", target / "recovery")
    guide = ROOT / "ATUALIZACOES.md"
    if not guide.is_file():
        guide = ROOT.parent / "docs" / "atualizacoes.md"
    if guide.is_file():
        shutil.copy2(guide, target / "ATUALIZACOES.md")
    tools_guide = ROOT / "FERRAMENTAS.md"
    if not tools_guide.is_file():
        tools_guide = ROOT.parent / "docs" / "ferramentas-dispositivo.md"
    if tools_guide.is_file():
        shutil.copy2(tools_guide, target / "FERRAMENTAS.md")
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
    if url is None and not entry.is_file():
        raise RuntimeError("Interface app/index.html não encontrada.")
    url = url or entry.as_uri()
    args = [browser, "--user-data-dir=" + str(profile), "--no-first-run", "--no-default-browser-check"]
    if kiosk:
        args += ["--kiosk", url]
    else:
        args += ["--app=" + url, "--start-maximized"]
    return args


def launch(kiosk, recovery=False):
    require_linux()
    if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        raise RuntimeError("Abra este lançador dentro da sessão gráfica do Linux; --diagnose também funciona no terminal.")
    browser = browser_path()
    if not browser:
        raise RuntimeError("Chromium/Chrome não encontrado no PATH.")
    target, _, _ = locations()
    profile = target.parent / (APP_ID + "-perfil")
    from updater import Manager, UpdateError
    from update_bridge import Bridge
    from device_services import Services, LaunchHistory
    import fcntl
    import time
    data = target.parent
    config = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    manager = Manager(data / "aegis-application-updates", config / "aegis-updater" / "trusted-keys", ROOT)
    services = Services(manager, data / "aegis")
    history = LaunchHistory(manager.home)
    with (manager.home / "application.lock").open("a") as session:
        try:
            fcntl.flock(session, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise UpdateError("O AEGIS já está aberto. Feche a outra janela antes de iniciar a recuperação.")
        if history.needs_recovery():
            recovery = True
            services.recovery_reason = history.state['reason'] or "Inicialização anterior incompleta. O aplicativo não será reiniciado automaticamente."
        if not recovery:
            try:
                services.resume_restore()
                manager.bootstrap()
            except (OSError, UpdateError):
                recovery = True
                services.recovery_reason = "A preparação/inicialização do aplicativo está incompleta. Use as opções independentes de recuperação."
        profile.mkdir(parents=True, exist_ok=True)
        # Let browser Save As choose destinations; never change unrelated preferences.
        prefs = profile / 'Default' / 'Preferences'
        try:
            settings = json.loads(prefs.read_text()) if prefs.exists() else {}
            settings.setdefault('download', {})['prompt_for_download'] = True
            prefs.parent.mkdir(parents=True, exist_ok=True)
            from updater import atomic_json
            atomic_json(prefs, settings)
        except (OSError, ValueError, TypeError):
            pass  # File System Access picker remains available; no overwrite of a broken profile.
        attempts = 0
        while True:
            if recovery:
                root = ROOT
                services.event('recovery_opened')
            else:
                try:
                    root = manager.boot()
                except (OSError, UpdateError):
                    recovery = True
                    services.recovery_reason = "Os arquivos do aplicativo não passaram na validação de inicialização."
                    continue
                history.begin()
                services.event('startup_started')
            this_recovery = recovery
            bridge = Bridge(manager, root, recovery=recovery, services=services)
            process, normal_close = None, False
            try:
                url = bridge.start()
                process = subprocess.Popen(command(ROOT, browser, kiosk, profile, url))
                deadline = time.monotonic() + 30
                while not bridge.ready.wait(.1):
                    if process.poll() is not None or time.monotonic() > deadline:
                        break
                healthy = bridge.ready.is_set()
                if healthy:
                    if not recovery:
                        history.ready()
                        services.event('startup_ready')
                    while process.poll() is None and not bridge.restart.wait(.2):
                        pass
                    if not bridge.restart.is_set():
                        code = process.wait()
                        normal_close = code == 0
                        if recovery or normal_close:
                            return code
                        services.recovery_reason = 'A interface encerrou com erro. Escolha uma ação ou saia da recuperação.'
                elif process.poll() == 0:
                    normal_close = True
                    if not recovery:
                        manager.defer_trial()
                    return 0
                elif recovery:
                    raise UpdateError('A recuperação não abriu no Chromium. Use --diagnose e confira a sessão gráfica; não haverá novas tentativas automáticas.')
                if bridge.restart.is_set():
                    normal_close = True
                    recovery = bridge.next_mode == 'recovery'
                    history.acknowledge()
                    if not recovery:
                        services.resume_restore()
                        manager.bootstrap()
                    attempts = 0
                    continue
            except (KeyboardInterrupt, SystemExit):
                normal_close = True
                if not recovery:
                    manager.defer_trial()
                return 0
            finally:
                if process is not None and process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
                bridge.close()
                if not this_recovery:
                    history.end(normal_close)
                    services.event('normal_exit' if normal_close else 'startup_failed')
            if not recovery:
                attempts += 1
                if not healthy and manager.state()['trial'] and attempts < 2:
                    continue  # Existing atomic rollback, once, only during failed trial startup.
                recovery = True
                services.recovery_reason = services.recovery_reason or 'A interface falhou na inicialização. A recuperação está aberta; não há reinicialização em ciclo.'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--recovery", action="store_true", help="Abre a recuperação independente da interface principal")
    group.add_argument("--diagnose", action="store_true", help="Relatório básico JSON sem sessão gráfica nem conteúdo pessoal")
    group.add_argument("--check", action="store_true", help="Diagnóstico sem alterar arquivos")
    group.add_argument("--install-updater", action="store_true", help="Instala a primeira versão com atualizador em pasta/atalho separados, preservando a instalação antiga")
    group.add_argument("--install", action="store_true", help="Instala o protótipo para o usuário atual")
    group.add_argument("--enable-autostart", action="store_true", help="Ativa início após login via XDG")
    group.add_argument("--disable-autostart", action="store_true", help="Desativa início via XDG")
    group.add_argument("--kiosk", action="store_true", help="Abre em tela cheia; Alt+F4 para sair")
    args = parser.parse_args()
    if args.diagnose:
        from updater import Manager
        from device_services import Services
        target, _, _ = locations()
        config = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
        manager = Manager(target.parent / "aegis-application-updates", config / "aegis-updater/trusted-keys", ROOT)
        print(json.dumps(Services(manager).diagnostics(), ensure_ascii=False, indent=2))
    elif args.check:
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
        return launch(args.kiosk, recovery=args.recovery)
    return 0


if __name__ == "__main__":
    import signal
    def terminate_normally(*_):
        raise SystemExit(0)
    signal.signal(signal.SIGTERM, terminate_normally)
    try:
        sys.exit(main())
    except (RuntimeError, OSError) as error:
        print("AEGIS:", error, file=sys.stderr)
        sys.exit(1)
