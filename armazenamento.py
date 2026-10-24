"""
Onde o CWD Leads guarda o que precisa durar entre um acesso e outro:
o contador de consultas e as tentativas de login erradas.

- Na Vercel: Upstash Redis (lá os arquivos não ficam salvos entre acessos).
- No computador: o contador no arquivo uso_api.json e as tentativas na memória.
  Se as variáveis do Upstash estiverem no .env, o computador também usa o Redis
  (aí o contador do PC e o da Vercel somam juntos).

Só números ficam guardados aqui, nenhum dado do Google.
"""

import json
import os
import threading
import time
from pathlib import Path

import requests

PASTA_PROJETO = Path(__file__).resolve().parent
ARQUIVO_USO = PASTA_PROJETO / "uso_api.json"
PREFIXO = "cwd:"


class ErroArmazenamento(Exception):
    """O Redis não respondeu ou não está configurado."""


def na_vercel():
    """A Vercel define a variável VERCEL em todo deploy."""
    return bool(os.getenv("VERCEL"))


class Redis:
    """Cliente mínimo da API REST do Upstash (sem biblioteca extra)."""

    def __init__(self, url, token):
        self.url = url.rstrip("/")
        self.token = token

    def executar(self, *comandos):
        """Roda vários comandos de uma vez (pipeline) e devolve os resultados."""
        try:
            resposta = requests.post(
                f"{self.url}/pipeline",
                headers={"Authorization": f"Bearer {self.token}"},
                json=[[str(parte) for parte in comando] for comando in comandos],
                timeout=10,
            )
            resposta.raise_for_status()
            resultados = resposta.json()
        except (requests.RequestException, ValueError) as erro:
            raise ErroArmazenamento(f"o Upstash Redis não respondeu ({erro.__class__.__name__}).")
        erros = [r["error"] for r in resultados if "error" in r]
        if erros:
            raise ErroArmazenamento(f"erro no Upstash Redis: {erros[0]}")
        return [r.get("result") for r in resultados]


class ArmazenamentoRedis:
    def __init__(self, redis):
        self.redis = redis

    def ler_uso(self, dia, mes):
        no_dia, no_mes = self.redis.executar(
            ["GET", f"{PREFIXO}uso:dia:{dia}"], ["GET", f"{PREFIXO}uso:mes:{mes}"]
        )
        return int(no_dia or 0), int(no_mes or 0)

    def somar_uso(self, dia, mes):
        chave_dia, chave_mes = f"{PREFIXO}uso:dia:{dia}", f"{PREFIXO}uso:mes:{mes}"
        no_dia, _, no_mes, _ = self.redis.executar(
            ["INCR", chave_dia], ["EXPIRE", chave_dia, 3 * 24 * 3600],
            ["INCR", chave_mes], ["EXPIRE", chave_mes, 40 * 24 * 3600],
        )
        return int(no_dia), int(no_mes)

    def registrar_falha(self, chave, janela):
        chave = f"{PREFIXO}login:{chave}"
        total, _ = self.redis.executar(["INCR", chave], ["EXPIRE", chave, janela])
        return int(total)

    def ler_falhas(self, chave):
        chave = f"{PREFIXO}login:{chave}"
        total, restante = self.redis.executar(["GET", chave], ["TTL", chave])
        return int(total or 0), max(int(restante), 0)

    def limpar_falhas(self, chave):
        self.redis.executar(["DEL", f"{PREFIXO}login:{chave}"])


class ArmazenamentoLocal:
    """Contador no arquivo uso_api.json e tentativas de login na memória."""

    def __init__(self):
        self._trava = threading.Lock()
        self._falhas = {}  # chave -> (total, expira_em)

    def ler_uso(self, dia, mes):
        try:
            dados = json.loads(ARQUIVO_USO.read_text(encoding="utf-8"))
        except (FileNotFoundError, ValueError):
            dados = {}
        no_dia = int(dados.get("requisicoes_dia", 0)) if dados.get("dia") == dia else 0
        no_mes = int(dados.get("requisicoes", 0)) if dados.get("mes") == mes else 0
        return no_dia, no_mes

    def somar_uso(self, dia, mes):
        with self._trava:
            no_dia, no_mes = self.ler_uso(dia, mes)
            no_dia, no_mes = no_dia + 1, no_mes + 1
            ARQUIVO_USO.write_text(
                json.dumps({"mes": mes, "requisicoes": no_mes, "dia": dia, "requisicoes_dia": no_dia}),
                encoding="utf-8",
            )
            return no_dia, no_mes

    def _falhas_validas(self, chave):
        total, expira_em = self._falhas.get(chave, (0, 0))
        return (total, expira_em) if expira_em > time.monotonic() else (0, 0)

    def registrar_falha(self, chave, janela):
        with self._trava:
            total = self._falhas_validas(chave)[0] + 1
            self._falhas[chave] = (total, time.monotonic() + janela)
            return total

    def ler_falhas(self, chave):
        total, expira_em = self._falhas_validas(chave)
        return total, max(int(expira_em - time.monotonic()), 0)

    def limpar_falhas(self, chave):
        with self._trava:
            self._falhas.pop(chave, None)


_local = ArmazenamentoLocal()


def obter():
    """Redis quando configurado; senão, o armazenamento local (que não vale na Vercel)."""
    url = os.getenv("UPSTASH_REDIS_REST_URL") or os.getenv("KV_REST_API_URL")
    token = os.getenv("UPSTASH_REDIS_REST_TOKEN") or os.getenv("KV_REST_API_TOKEN")
    if url and token:
        return ArmazenamentoRedis(Redis(url, token))
    if na_vercel():
        raise ErroArmazenamento(
            "o Upstash Redis não está conectado ao projeto na Vercel. Veja o passo a passo no LEIA-ME."
        )
    return _local
