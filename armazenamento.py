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

# Pares (URL, token) aceitos, na ordem de preferência. A integração do Upstash na
# Vercel cria os nomes KV_*; quem cria o banco direto no site do Upstash recebe UPSTASH_*.
# Nomes com prefixo personalizado (ex.: STORAGE_KV_REST_API_URL) também são aceitos.
PARES_CONHECIDOS = (
    ("UPSTASH_REDIS_REST_URL", "UPSTASH_REDIS_REST_TOKEN"),
    ("KV_REST_API_URL", "KV_REST_API_TOKEN"),
)
FINAIS_DE_URL = ("KV_REST_API_URL", "REDIS_REST_URL")


class ErroArmazenamento(Exception):
    """O Redis não respondeu ou não está configurado."""


def na_vercel():
    """A Vercel define a variável VERCEL em todo deploy."""
    return bool(os.getenv("VERCEL"))


class Redis:
    """Cliente mínimo da API REST do Upstash (sem biblioteca extra).

    As mensagens de erro citam só os NOMES das variáveis, nunca os valores.
    """

    def __init__(self, url, token, nome_url, nome_token):
        self.url = url.rstrip("/")
        self.token = token
        self.nome_url = nome_url
        self.nome_token = nome_token

    def executar(self, *comandos):
        """Roda vários comandos de uma vez (pipeline) e devolve os resultados."""
        try:
            resposta = requests.post(
                f"{self.url}/pipeline",
                headers={"Authorization": f"Bearer {self.token}"},
                json=[[str(parte) for parte in comando] for comando in comandos],
                timeout=10,
            )
        except requests.Timeout:
            raise ErroArmazenamento(
                f"erro ao conectar: o Upstash Redis não respondeu a tempo (endereço em {self.nome_url})."
            )
        except requests.ConnectionError:
            raise ErroArmazenamento(
                f"erro ao conectar: não foi possível alcançar o endereço em {self.nome_url}. "
                "Confira se é a URL REST do banco no Upstash."
            )
        except requests.RequestException as falha:
            raise ErroArmazenamento(
                f"erro ao conectar ao Upstash Redis ({falha.__class__.__name__}). "
                f"Confira {self.nome_url} e {self.nome_token}."
            )
        if resposta.status_code in (401, 403):
            raise ErroArmazenamento(
                f"erro ao conectar: o Upstash Redis recusou o token em {self.nome_token} "
                f"(HTTP {resposta.status_code}). Use o token REST completo, não o somente leitura."
            )
        if resposta.status_code >= 400:
            raise ErroArmazenamento(f"erro ao conectar: o Upstash Redis respondeu HTTP {resposta.status_code}.")
        try:
            resultados = resposta.json()
        except ValueError:
            raise ErroArmazenamento(
                f"erro ao conectar: a resposta não veio do Upstash. Confira o endereço em {self.nome_url}."
            )
        erros = [r["error"] for r in resultados if isinstance(r, dict) and "error" in r]
        if erros:
            raise ErroArmazenamento(f"o Upstash Redis recusou um comando: {str(erros[0])[:150]}")
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


def _valor(nome):
    """Valor da variável sem espaços nem aspas coladas por engano ('' se ausente)."""
    return os.getenv(nome, "").strip().strip("\"'").strip()


def _pares_candidatos():
    """Pares conhecidos primeiro; depois os de prefixo personalizado (ex.: STORAGE_KV_REST_API_URL)."""
    pares = list(PARES_CONHECIDOS)
    for nome in sorted(os.environ):
        if nome.endswith(FINAIS_DE_URL):
            par = (nome, nome[: -len("URL")] + "TOKEN")
            if par not in pares:
                pares.append(par)
    return pares


def _nomes_parecidos():
    """Nomes (nunca valores) de variáveis que parecem do Redis, para o diagnóstico."""
    return sorted(
        nome for nome in os.environ
        if "REDIS" in nome.upper() or "UPSTASH" in nome.upper() or nome.upper().startswith("KV_")
    )


def configuracao_redis():
    """Devolve Redis pronto para usar, ou None se nenhuma variável do Redis existir.

    Levanta ErroArmazenamento explicando o que falta (só nomes, nunca valores).
    """
    pares = _pares_candidatos()
    for nome_url, nome_token in pares:
        url, token = _valor(nome_url), _valor(nome_token)
        if url and token:
            if not url.startswith("https://"):
                raise ErroArmazenamento(
                    f"a variável {nome_url} precisa começar com https:// "
                    "(é a URL REST do Upstash, não a redis://)."
                )
            return Redis(url, token, nome_url, nome_token)
    for nome_url, nome_token in pares:
        if _valor(nome_url) or _valor(nome_token):
            presente, ausente = (nome_url, nome_token) if _valor(nome_url) else (nome_token, nome_url)
            raise ErroArmazenamento(
                f"variável ausente: {ausente} não existe ou está vazia ({presente} existe). "
                "Confira em Settings → Environment Variables e faça um novo deploy."
            )
    return None


def obter():
    """Redis quando configurado; senão, o armazenamento local (que não vale na Vercel)."""
    redis = configuracao_redis()
    if redis:
        return ArmazenamentoRedis(redis)
    if na_vercel():
        parecidas = _nomes_parecidos()
        encontradas = f" Neste deploy só existem: {', '.join(parecidas)}." if parecidas else ""
        raise ErroArmazenamento(
            "variável ausente: o Upstash Redis precisa de KV_REST_API_URL e KV_REST_API_TOKEN "
            f"(ou UPSTASH_REDIS_REST_URL e UPSTASH_REDIS_REST_TOKEN), e elas não chegaram a este deploy.{encontradas} "
            "Confira se estão no ambiente Production em Settings → Environment Variables e faça um novo deploy."
        )
    return _local
