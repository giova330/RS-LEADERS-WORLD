#!/usr/bin/env python3
"""
Inicio con un solo comando: instala dependencias, actualiza los datos
y abre la web en tu navegador. No necesitas GitHub.

    python iniciar.py
"""
import glob
import http.server
import os
import socket
import socketserver
import subprocess
import sys
import threading
import webbrowser

AQUI = os.path.dirname(os.path.abspath(__file__))
os.chdir(AQUI)
PUERTO = 8000


def instalar():
    try:
        import pandas, numpy, requests, yfinance  # noqa: F401
    except ImportError:
        print("Instalando dependencias (solo la primera vez)...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])


def actualizar():
    hay_datos = bool(glob.glob(os.path.join("data", "??.json")))
    if hay_datos:
        r = input("Ya hay datos guardados. ¿Actualizarlos? (s/n) [n]: ").strip().lower()
        if r != "s":
            return None
    print("\nCódigos: us ca mx br es de fr it uk nl be pt ch se dk no fi jp hk cn kr tw in au sg")
    paises = input("Países a escanear, separados por coma (Enter = solo es,us): ").strip().lower() or "es,us"
    print("\nEscaneando... puede tardar unos minutos por país.\n")
    subprocess.call([sys.executable, "scanner.py", "--countries", paises])
    return paises.split(",")[0].strip()


def ip_local():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return None


def servir(codigo):
    class Handler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("0.0.0.0", PUERTO), Handler) as httpd:
        url = f"http://localhost:{PUERTO}/#{codigo or 'es'}"
        print(f"\nEn este ordenador: {url}")
        ip = ip_local()
        if ip:
            print(f"En tu móvil (misma wifi): http://{ip}:{PUERTO}/#{codigo or 'es'}")
        print("Pulsa Ctrl+C para cerrar.")
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nCerrado.")


if __name__ == "__main__":
    instalar()
    servir(actualizar())
