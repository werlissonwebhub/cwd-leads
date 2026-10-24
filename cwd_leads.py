"""
CWD Leads no seu computador.

Uso:
    .venv\\Scripts\\python cwd_leads.py     (liga o servidor e abre o navegador)

O servidor (rotas, login e busca) está em app.py, o mesmo que roda na Vercel.
Aqui ele também serve a pasta public/; na Vercel, quem faz isso é a CDN dela.
"""

import mimetypes
import socket
import sys
import threading
import webbrowser

import uvicorn
from fastapi.staticfiles import StaticFiles

import buscar_clientes as bc
from app import PASTA_PUBLICA, app

ENDERECO = "127.0.0.1"  # só este computador acessa
PORTA = 8000
CONFIG_SERVIDOR = dict(
    host=ENDERECO,
    port=PORTA,
    log_level="warning",
    # Não confiar em X-Forwarded-For: aqui não há proxy na frente, então esse
    # cabeçalho poderia ser inventado e enganar o bloqueio de tentativas de login.
    proxy_headers=False,
)

# O Windows às vezes registra tipos errados para estes arquivos.
mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("text/css", ".css")
mimetypes.add_type("image/svg+xml", ".svg")
mimetypes.add_type("application/manifest+json", ".webmanifest")

# Por último: tudo que não é /api/... vem da pasta public/.
app.mount("/", StaticFiles(directory=PASTA_PUBLICA, html=True), name="public")


def ja_esta_ligado():
    with socket.socket() as conexao:
        return conexao.connect_ex((ENDERECO, PORTA)) == 0


def main():
    try:
        bc.carregar_configuracao()
    except bc.ErroConfiguracao as erro:
        sys.exit(f"ERRO: {erro}")
    url = f"http://{ENDERECO}:{PORTA}"
    if ja_esta_ligado():
        print(f"A porta {PORTA} já está em uso; o CWD Leads provavelmente já está ligado.")
        print(f"Abrindo {url} no navegador.")
        webbrowser.open(url)
        return
    print(f"CWD Leads ligado em {url}")
    print("Deixe esta janela aberta enquanto usa. Para desligar: Ctrl+C.")
    threading.Timer(1.5, webbrowser.open, args=[url]).start()
    uvicorn.run(app, **CONFIG_SERVIDOR)


if __name__ == "__main__":
    main()
