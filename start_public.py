"""
StorageHub — Launcher avec tunnel public
=========================================
Lance le serveur FastAPI ET un tunnel pour le rendre accessible depuis l'extérieur.

Utilisation :
    python start_public.py

Options :
    --port      PORT      Port local (défaut: 8080)
    --host      HOST      Hôte local (défaut: 0.0.0.0)
    --tunnel    PROVIDER  cloudflared | ngrok | none (défaut: cloudflared)
    --no-reload           Désactiver le hot-reload uvicorn
    --env       ENV       development | production (défaut: development)

Prérequis selon le tunnel choisi :
    cloudflared : winget install Cloudflare.cloudflared   (Windows)
                  brew install cloudflared                 (macOS)
                  ou télécharger sur https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/
    ngrok       : pip install pyngrok  OU  télécharger ngrok.com
"""
import argparse
import os
import re
import signal
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

# ── Couleurs terminal ──────────────────────────────────────────────────────────
def _c(text, code): return f"\033[{code}m{text}\033[0m"
OK    = lambda s: _c(s, "92")
WARN  = lambda s: _c(s, "93")
ERR   = lambda s: _c(s, "91")
BOLD  = lambda s: _c(s, "1")
CYAN  = lambda s: _c(s, "96")
DIM   = lambda s: _c(s, "2")

BANNER = r"""
  ____  _                             _   _       _     
 / ___|| |_ ___  _ __ __ _  __ _  ___| | | |_   _| |__  
 \___ \| __/ _ \| '__/ _` |/ _` |/ _ \ |_| | | | | '_ \ 
  ___) | || (_) | | | (_| | (_| |  __/  _  | |_| | |_) |
 |____/ \__\___/|_|  \__,_|\__, |\___|_| |_|\__,_|_.__/ 
                            |___/                         
"""


def print_banner():
    print(CYAN(BANNER))
    print(BOLD("  Secure File Storage Service — v2.0.0"))
    print(DIM("  WIB Company Engineering\n"))


# ── Détection des binaires ─────────────────────────────────────────────────────
def _cmd_exists(name: str) -> bool:
    import shutil
    return shutil.which(name) is not None


# ── Tunnel cloudflared ─────────────────────────────────────────────────────────
def start_cloudflared(port: int) -> tuple[subprocess.Popen, str]:
    """Lance cloudflared tunnel --url http://localhost:{port}"""
    print(f"  {CYAN('»')} Démarrage du tunnel {BOLD('Cloudflare')}…")

    cmd = ["cloudflared", "tunnel", "--url", f"http://localhost:{port}"]
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )

    public_url = None
    url_pattern = re.compile(r"https://[a-zA-Z0-9\-]+\.trycloudflare\.com")

    for line in proc.stdout:
        line = line.strip()
        if not line:
            continue
        match = url_pattern.search(line)
        if match:
            public_url = match.group()
            break
        if "failed" in line.lower() or "error" in line.lower():
            print(f"  {ERR('✗')} cloudflared: {line}")

    return proc, public_url


# ── Tunnel ngrok ──────────────────────────────────────────────────────────────
def start_ngrok(port: int) -> tuple[subprocess.Popen, str]:
    """Lance ngrok http {port}"""
    print(f"  {CYAN('»')} Démarrage du tunnel {BOLD('ngrok')}…")

    # Essai 1 : pyngrok
    try:
        from pyngrok import ngrok as _ngrok
        tunnel = _ngrok.connect(port, "http")
        public_url = tunnel.public_url.replace("http://", "https://")
        return None, public_url
    except ImportError:
        pass

    # Essai 2 : binaire ngrok
    if not _cmd_exists("ngrok"):
        return None, None

    proc = subprocess.Popen(
        ["ngrok", "http", str(port), "--log=stdout"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1,
    )
    url_pattern = re.compile(r"https://[a-zA-Z0-9\-]+\.ngrok[-\w]*.io")
    public_url = None
    deadline = time.time() + 10
    for line in proc.stdout:
        if time.time() > deadline:
            break
        match = url_pattern.search(line)
        if match:
            public_url = match.group()
            break
    return proc, public_url


# ── Mise à jour du .env avec la public URL ─────────────────────────────────────
def update_public_url(url: str):
    env_file = Path(".env")
    lines = env_file.read_text(encoding="utf-8").splitlines() if env_file.exists() else []
    new_lines = []
    found = False
    for line in lines:
        if line.startswith("BASE_URL=") or line.startswith("CDN_BASE_URL="):
            new_lines.append(f"BASE_URL={url}")
            new_lines.append(f"CDN_BASE_URL={url}")
            found = True
        else:
            new_lines.append(line)
    if not found:
        new_lines.extend([f"BASE_URL={url}", f"CDN_BASE_URL={url}"])
    env_file.write_text("\n".join(new_lines), encoding="utf-8")
    print(f"  {OK('✓')} .env mis à jour : BASE_URL={url}")


# ── Serveur uvicorn dans un thread ─────────────────────────────────────────────
def start_server(host: str, port: int, reload: bool, env: str) -> subprocess.Popen:
    env_vars = {**os.environ, "APP_ENV": env}
    cmd = [
        sys.executable, "-m", "uvicorn", "app.main:app",
        "--host", host, "--port", str(port),
    ]
    if reload:
        cmd.append("--reload")

    print(f"  {CYAN('»')} Démarrage d'uvicorn sur {BOLD(f'http://{host}:{port}')}…")
    proc = subprocess.Popen(cmd, env=env_vars)
    time.sleep(2)
    return proc


# ── Affichage final des URLs ───────────────────────────────────────────────────
def print_urls(local_port: int, public_url: str | None):
    print()
    print(BOLD("  ─────────────────────────────────────────────────"))
    print(BOLD("   StorageHub est opérationnel"))
    print(BOLD("  ─────────────────────────────────────────────────"))
    print()

    local = f"http://localhost:{local_port}"
    if public_url:
        print(f"  {OK('●')} URL publique (externe)  →  {BOLD(public_url)}")
    print(f"  {CYAN('●')} URL locale              →  {local}")
    print()
    print(f"  {DIM('Pages :')}")
    base = public_url or local
    pages = [
        ("Accueil (landing Franck)", "/"),
        ("Dashboard intégrateur",   "/ui/integration.html"),
        ("Suite de tests",          "/test"),
        ("Dashboard SaaS",          "/ui/dashboard.html"),
        ("Swagger API",             "/docs"),
        ("Guide d'intégration",     "/v1/integration/guide"),
        ("Status public",           "/v1/integration/status"),
        ("Admin overview",          "/v1/admin/overview"),
    ]
    for label, path in pages:
        print(f"  {DIM('›')} {label:<30} {CYAN(base + path)}")

    print()
    print(f"  {DIM('Auth de développement :')}")
    print(f"  {DIM('›')} X-API-Key    :  dev-api-key-sendbid-2024")
    print(f"  {DIM('›')} X-User-Id    :  user-001")
    print(f"  {DIM('›')} X-User-Role  :  user")
    print()

    if public_url:
        print(f"  {OK('✓')} Partagez cette URL avec vos applications externes :")
        print(f"     {BOLD(public_url)}")
        print()
        print(f"  {DIM('Exemple rapide (curl) :')}")
        print(f"  {DIM('»')} curl -X POST {public_url}/v1/accounts/register \\")
        print(f"       -H 'Content-Type: application/json' \\")
        print(f"       -d '{{\"email\":\"app@example.com\",\"password\":\"MotDePasse\",\"company_name\":\"Mon App\"}}'")
    else:
        print(WARN("  ⚠ Aucun tunnel — accès local uniquement (LAN ou port forwarding manuel)"))
        print(f"  {DIM('›')} Votre IP locale : utilisez ipconfig pour trouver votre IP LAN")
        print(f"  {DIM('›')} Ouvrez le port {local_port} dans votre pare-feu Windows")
        print()
        print(f"  {DIM('Installer cloudflared (recommandé) :')}")
        print(f"  {DIM('»')} winget install Cloudflare.cloudflared")
        print(f"  {DIM('»')} puis relancer : python start_public.py")

    print()
    print(BOLD("  ─────────────────────────────────────────────────"))
    print(f"  Ctrl+C pour arrêter")
    print()


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="StorageHub public launcher")
    parser.add_argument("--port",     type=int,  default=8080)
    parser.add_argument("--host",     type=str,  default="0.0.0.0")
    parser.add_argument("--tunnel",   type=str,  default="auto", choices=["cloudflared", "ngrok", "none", "auto"])
    parser.add_argument("--no-reload",action="store_true")
    parser.add_argument("--env",      type=str,  default="development")
    parser.add_argument("--open",     action="store_true", help="Ouvrir le navigateur automatiquement")
    args = parser.parse_args()

    print_banner()

    processes = []

    # 1. Serveur FastAPI
    server = start_server(args.host, args.port, not args.no_reload, args.env)
    processes.append(server)

    # 2. Tunnel
    public_url = None
    tunnel_proc = None
    tunnel = args.tunnel

    if tunnel == "auto":
        if _cmd_exists("cloudflared"):
            tunnel = "cloudflared"
        elif _cmd_exists("ngrok") or _module_available("pyngrok"):
            tunnel = "ngrok"
        else:
            tunnel = "none"
            print(WARN("  ⚠ Ni cloudflared ni ngrok trouvés — mode local uniquement"))
            print(f"  {DIM('»')} Pour un accès externe : winget install Cloudflare.cloudflared\n")

    if tunnel == "cloudflared":
        tunnel_proc, public_url = start_cloudflared(args.port)
        if tunnel_proc:
            processes.append(tunnel_proc)
    elif tunnel == "ngrok":
        tunnel_proc, public_url = start_ngrok(args.port)
        if tunnel_proc:
            processes.append(tunnel_proc)

    if public_url:
        update_public_url(public_url)

    print_urls(args.port, public_url)

    if args.open:
        url = public_url or f"http://localhost:{args.port}"
        webbrowser.open(url + "/ui/integration.html")

    # 3. Attente + signal d'arrêt
    def shutdown(*_):
        print(f"\n  {WARN('»')} Arrêt du service…")
        for p in processes:
            try:
                p.terminate()
            except Exception:
                pass
        sys.exit(0)

    signal.signal(signal.SIGINT,  shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    try:
        server.wait()
    except KeyboardInterrupt:
        shutdown()


def _module_available(name: str) -> bool:
    import importlib.util
    return importlib.util.find_spec(name) is not None


if __name__ == "__main__":
    main()
