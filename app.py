"""
CWD Leads: servidor web (FastAPI). É o mesmo na Vercel e no seu computador.

- Na Vercel, os arquivos de public/ são servidos pela CDN dela e este app
  responde às rotas /api/...
- No computador, use `python cwd_leads.py`: ele liga este app, serve a pasta
  public/ e abre o navegador.

A chave do Google e a senha ficam só no servidor (variáveis de ambiente ou .env).
Os resultados não são guardados em lugar nenhum: a política da Places API não
permite guardar os dados (a exceção é o place ID).
"""

import re
import threading
from pathlib import Path
from urllib.parse import parse_qs, quote_plus, urlparse

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

import acesso
import armazenamento
import buscar_clientes as bc

PASTA_PUBLICA = Path(__file__).resolve().parent / "public"

app = FastAPI(title="CWD Leads", docs_url=None, redoc_url=None, openapi_url=None)
trava_busca = threading.Lock()  # uma busca por vez: clique duplo não gasta em dobro

CABECALHOS_DE_SEGURANCA = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}


@app.middleware("http")
async def cabecalhos_de_seguranca(request: Request, chamar_proximo):
    resposta = await chamar_proximo(request)
    for nome, valor in CABECALHOS_DE_SEGURANCA.items():
        resposta.headers.setdefault(nome, valor)
    if request.url.path.startswith("/api/"):
        resposta.headers["Cache-Control"] = "no-store"  # nada da API fica guardado em cache
    return resposta


def erro(status, mensagem, **extra):
    return HTTPException(status, detail={"mensagem": mensagem, **extra})


# ---------- Login ----------

class PedidoDeLogin(BaseModel):
    senha: str = Field(min_length=1, max_length=200)


def configuracao_de_acesso():
    try:
        return acesso.configuracao()
    except acesso.ErroAcesso as falha:
        raise erro(503, str(falha))


def exigir_login(request: Request):
    """Sem login válido, nenhuma rota protegida funciona."""
    senha, segredo = configuracao_de_acesso()
    if senha is None:
        return  # login desligado: só no computador, sem SENHA_ACESSO no .env
    if not acesso.sessao_valida(request.cookies.get(acesso.NOME_COOKIE), senha, segredo):
        raise erro(401, "Faça login para continuar.", login=True)


@app.get("/api/sessao")
def ver_sessao(request: Request):
    senha, segredo = configuracao_de_acesso()
    try:
        armazenamento.obter()  # só confere as variáveis do Redis (não conecta): avisa já na tela de login
    except armazenamento.ErroArmazenamento as falha:
        raise erro(503, str(falha))
    if senha is None:
        return {"login_necessario": False, "logado": True}
    logado = acesso.sessao_valida(request.cookies.get(acesso.NOME_COOKIE), senha, segredo)
    return {"login_necessario": True, "logado": logado}


@app.post("/api/login")
def entrar(pedido: PedidoDeLogin, request: Request, response: Response):
    senha, segredo = configuracao_de_acesso()
    if senha is None:
        return {"ok": True}
    ip = acesso.ip_do_visitante(request)
    try:
        bloqueio = acesso.segundos_de_bloqueio(ip)
        if bloqueio:
            minutos = -(-bloqueio // 60)  # arredonda para cima
            raise erro(429, f"Muitas senhas erradas. Tente de novo em {minutos} min.")
        if not acesso.senha_correta(pedido.senha, senha):
            acesso.registrar_falha(ip)
            raise erro(401, "Senha incorreta.")
        acesso.limpar_falhas(ip)
    except armazenamento.ErroArmazenamento as falha:
        raise erro(503, str(falha))

    response.set_cookie(
        acesso.NOME_COOKIE,
        acesso.criar_sessao(senha, segredo),
        max_age=acesso.DURACAO_SESSAO,
        httponly=True,  # o JavaScript da página não consegue ler o cookie
        secure=armazenamento.na_vercel() or request.url.scheme == "https",
        samesite="lax",
        path="/",
    )
    return {"ok": True}


@app.post("/api/sair")
def sair(response: Response):
    response.delete_cookie(acesso.NOME_COOKIE, path="/")
    return {"ok": True}


# ---------- Busca ----------

class PedidoDeBusca(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    nicho: str = Field(min_length=2, max_length=80)
    cidade: str = Field(min_length=2, max_length=80)
    paginas: int = Field(default=1, ge=1, le=3)


def configuracao_da_busca():
    try:
        return bc.carregar_configuracao()
    except bc.ErroConfiguracao as falha:
        raise erro(500, str(falha))


def novo_contador(limite_diario, limite_mensal):
    try:
        return bc.ContadorDeUso(limite_diario, limite_mensal)
    except armazenamento.ErroArmazenamento as falha:
        raise erro(503, str(falha))


def resumo_de_uso(contador):
    return {
        "hoje": contador.no_dia, "limite_dia": contador.limite_diario,
        "mes": contador.no_mes, "limite_mes": contador.limite_mensal,
    }


def link_seguro(url):
    """Só deixa passar links http(s), para nada estranho virar botão."""
    try:
        return url if urlparse(url).scheme in ("http", "https") else ""
    except ValueError:
        return ""


def numero_do_link_whatsapp(link):
    """Tira o número de um link wa.me/55... ou api.whatsapp.com/send?phone=55..."""
    partes = urlparse(link)
    if bc.link_de(link, ("wa.me",)):
        candidato = partes.path.strip("/").split("/")[0]
    else:
        candidato = parse_qs(partes.query).get("phone", [""])[0]
    digitos = re.sub(r"\D", "", candidato)
    return digitos if 10 <= len(digitos) <= 15 else ""


def link_whatsapp(telefone, site):
    """Devolve (link, número com 55, provável?). Celular = DDD + 9 dígitos começando com 9."""
    if bc.link_de(site, ("wa.me", "whatsapp.com")):
        return site, numero_do_link_whatsapp(site), False
    digitos = re.sub(r"\D", "", telefone)
    if len(digitos) == 11 and digitos[2] == "9":
        return f"https://wa.me/55{digitos}", f"55{digitos}", True
    return "", "", False


def link_telefone(telefone):
    digitos = re.sub(r"\D", "", telefone)
    return f"tel:+55{digitos}" if len(digitos) in (10, 11) else ""


def para_card(linha, cidade):
    """Monta o que o navegador precisa para desenhar um card."""
    site = link_seguro(linha["site"])
    whatsapp, whatsapp_numero, whatsapp_provavel = link_whatsapp(linha["telefone"], site)
    if bc.link_de(site, ("instagram.com", "instagr.am")):
        instagram, instagram_perfil = site, True
    else:
        pesquisa = f'{linha["nome"]} {cidade} instagram'
        instagram, instagram_perfil = "https://www.google.com/search?q=" + quote_plus(pesquisa), False
    # O botão Site não repete links que já têm botão próprio (Instagram, WhatsApp).
    mostrar_site = linha["situacao_site"] != "sem_site" and site not in (instagram, whatsapp)
    return {
        "place_id": linha["place_id"],
        "nome": linha["nome"],
        "nota": linha["nota"],
        "avaliacoes": linha["avaliacoes"],
        "endereco": linha["endereco"],
        "telefone": linha["telefone"],
        "telefone_link": link_telefone(linha["telefone"]),
        "situacao_site": linha["situacao_site"],
        "whatsapp": whatsapp,
        "whatsapp_numero": whatsapp_numero,
        "whatsapp_provavel": whatsapp_provavel,
        "instagram": instagram,
        "instagram_perfil": instagram_perfil,
        "site": site if mostrar_site else "",
        "maps": link_seguro(linha["maps"]),
    }


@app.get("/api/uso", dependencies=[Depends(exigir_login)])
def ver_uso():
    _, limite_diario, limite_mensal = configuracao_da_busca()
    return resumo_de_uso(novo_contador(limite_diario, limite_mensal))


@app.post("/api/buscar", dependencies=[Depends(exigir_login)])
def fazer_busca(pedido: PedidoDeBusca):
    chave, limite_diario, limite_mensal = configuracao_da_busca()
    texto = f"{pedido.nicho} em {pedido.cidade}"
    with trava_busca:
        contador = novo_contador(limite_diario, limite_mensal)
        motivo = contador.motivo_para_parar()
        if motivo:
            raise erro(429, motivo, uso=resumo_de_uso(contador))
        try:
            lugares = bc.buscar(texto, chave, pedido.paginas, contador)
        except (bc.ErroFatal, bc.ErroBusca, armazenamento.ErroArmazenamento) as falha:
            raise erro(502, str(falha), uso=resumo_de_uso(contador))

    linhas = {linha["place_id"]: linha for linha in map(bc.para_linha, lugares)}.values()
    return {
        "busca": texto,
        "resultados": [para_card(linha, pedido.cidade) for linha in bc.ordenar(linhas)],
        "uso": resumo_de_uso(contador),
    }


@app.get("/", include_in_schema=False)
def pagina_inicial():
    # Na Vercel a CDN costuma entregar public/index.html antes de chegar aqui;
    # esta rota garante a página caso não entregue.
    return FileResponse(PASTA_PUBLICA / "index.html")
