"""
Login do CWD Leads: senha, cookie de sessão e bloqueio de tentativas.

- A senha fica na variável de ambiente SENHA_ACESSO (nunca no código).
- O cookie é assinado com SEGREDO_SESSAO + a senha: trocar qualquer um dos dois
  desconecta todos os aparelhos.
- 5 senhas erradas do mesmo IP bloqueiam esse IP por 15 minutos. 20 erros no
  total (de qualquer IP) bloqueiam novos logins por 15 minutos; quem já está
  logado continua usando.
"""

import hashlib
import hmac
import ipaddress
import os
import secrets
import time

from dotenv import load_dotenv

import armazenamento

NOME_COOKIE = "cwd_sessao"
DURACAO_SESSAO = 30 * 24 * 3600  # 30 dias, em segundos
TENTATIVAS_POR_IP = 5
TENTATIVAS_NO_TOTAL = 20
BLOQUEIO = 15 * 60  # segundos
TAMANHO_MINIMO_SENHA = 12
TAMANHO_MINIMO_SEGREDO = 32

# Só no computador, quando não há SEGREDO_SESSAO: muda a cada vez que o servidor liga.
_segredo_local = secrets.token_urlsafe(32)


class ErroAcesso(Exception):
    """Login mal configurado: nada da API funciona até corrigir."""


def configuracao():
    """Devolve (senha, segredo), ou (None, None) quando o login está desligado.

    O login só pode ficar desligado no computador (sem SENHA_ACESSO no .env), onde
    o servidor aceita apenas acessos do próprio computador. Na Vercel ele é
    obrigatório: se faltar algo, tudo fica bloqueado.
    """
    load_dotenv(armazenamento.PASTA_PROJETO / ".env", override=True)
    senha = os.getenv("SENHA_ACESSO", "")
    segredo = os.getenv("SEGREDO_SESSAO", "")
    if armazenamento.na_vercel():
        if len(senha) < TAMANHO_MINIMO_SENHA or len(segredo) < TAMANHO_MINIMO_SEGREDO:
            raise ErroAcesso(
                f"login não configurado na Vercel. Cadastre SENHA_ACESSO ({TAMANHO_MINIMO_SENHA}+ "
                f"caracteres) e SEGREDO_SESSAO ({TAMANHO_MINIMO_SEGREDO}+ caracteres) e faça um "
                "novo deploy. Veja o LEIA-ME."
            )
        return senha, segredo
    if not senha:
        return None, None
    return senha, segredo or _segredo_local


def senha_correta(tentativa, senha):
    # Compara os resumos (mesmo tamanho) em tempo constante: o tempo de resposta não dá pistas.
    return hmac.compare_digest(
        hashlib.sha256(tentativa.encode()).digest(), hashlib.sha256(senha.encode()).digest()
    )


def _assinar(texto, senha, segredo):
    chave = hashlib.sha256(f"{segredo}\0{senha}".encode()).digest()
    return hmac.new(chave, texto.encode(), hashlib.sha256).hexdigest()


def criar_sessao(senha, segredo):
    """Valor do cookie: 'validade.assinatura'."""
    validade = str(int(time.time()) + DURACAO_SESSAO)
    return f"{validade}.{_assinar(validade, senha, segredo)}"


def sessao_valida(valor, senha, segredo):
    validade, _, assinatura = (valor or "").partition(".")
    if not validade.isdigit() or not assinatura:
        return False
    esperada = _assinar(validade, senha, segredo)
    return hmac.compare_digest(assinatura.encode(), esperada.encode()) and int(validade) > time.time()


def ip_do_visitante(request):
    """IP usado no bloqueio de tentativas.

    Na Vercel: só o cabeçalho x-real-ip, que a própria Vercel preenche (ela
    sobrescreve os cabeçalhos de IP vindos de fora para impedir falsificação).
    Fora da Vercel: nenhum cabeçalho (qualquer um poderia inventar); vale o IP
    da própria conexão.
    IPv6 é agrupado por /64, porque um mesmo aparelho troca de endereço dentro
    desse bloco com facilidade.
    """
    if armazenamento.na_vercel():
        bruto = request.headers.get("x-real-ip", "")
    else:
        bruto = request.client.host if request.client else ""
    try:
        ip = ipaddress.ip_address(bruto.strip())
    except ValueError:
        return "desconhecido"
    if ip.version == 6:
        return f"{ipaddress.ip_network(f'{ip}/64', strict=False).network_address}/64"
    return str(ip)


def segundos_de_bloqueio(ip):
    """Quanto falta para liberar o login deste IP (0 = liberado)."""
    loja = armazenamento.obter()
    for chave, limite in ((f"ip:{ip}", TENTATIVAS_POR_IP), ("total", TENTATIVAS_NO_TOTAL)):
        falhas, restante = loja.ler_falhas(chave)
        if falhas >= limite:
            return max(restante, 1)
    return 0


def registrar_falha(ip):
    loja = armazenamento.obter()
    loja.registrar_falha(f"ip:{ip}", BLOQUEIO)
    loja.registrar_falha("total", BLOQUEIO)


def limpar_falhas(ip):
    armazenamento.obter().limpar_falhas(f"ip:{ip}")
