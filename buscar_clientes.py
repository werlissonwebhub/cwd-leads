"""
Busca possíveis clientes na Google Places API (New), só com o Text Search
(sem Place Details), e mostra um resumo no terminal.

A política do Google não permite guardar os dados da Places API (a exceção é
o place ID). Por isso este script não gera planilha: para ver os resultados
completos, use a interface web (cwd_leads.py).

Uso:
    python buscar_clientes.py "psicólogo em Brasília" "clínica de estética em Taguatinga"
    python buscar_clientes.py "dentista em Ceilândia" --paginas 1
    python buscar_clientes.py            (sem nada: pergunta as buscas no terminal)
"""

import argparse
import os
import sys
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests
from dotenv import load_dotenv

import armazenamento

URL_API = "https://places.googleapis.com/v1/places:searchText"

# Só os campos que usamos: o Google cobra de acordo com os campos pedidos.
# nextPageToken não é dado do lugar; serve só para pedir a próxima página.
CAMPOS = ",".join([
    "places.id",
    "places.displayName",
    "places.nationalPhoneNumber",
    "places.formattedAddress",
    "places.rating",
    "places.userRatingCount",
    "places.websiteUri",
    "places.googleMapsUri",
    "nextPageToken",
])

# Cada página de 20 resultados = 1 consulta à API.
LIMITE_POR_EXECUCAO = 30

# Links que contam como "Só rede social" (inclui páginas de "link na bio").
REDES_SOCIAIS = (
    "instagram.com", "instagr.am", "facebook.com", "fb.com", "fb.me",
    "linktr.ee", "taplink.cc", "linkme.bio", "bio.site", "beacons.ai",
    "wa.me", "whatsapp.com",
)
# Sites gratuitos do Google (perfil da empresa), já desativados: contam como "Sem site".
SITES_DESATIVADOS = ("business.site",)

# Ordem de prioridade para prospecção.
SITUACOES = ("sem_site", "rede_social", "tem_site")

PASTA_PROJETO = Path(__file__).resolve().parent

# O dia e o mês do contador viram no horário de Brasília (os servidores da Vercel usam UTC).
# O Brasil não tem mais horário de verão, então UTC-3 fixo basta.
FUSO_BRASILIA = timezone(timedelta(hours=-3))


class ErroConfiguracao(Exception):
    """Falta algo (ou há algo errado) no .env."""


class ErroFatal(Exception):
    """Erro que impede as próximas buscas (chave inválida, sem internet, cota...)."""


class ErroBusca(Exception):
    """Erro só desta busca: pula para a próxima."""


def carregar_configuracao():
    """Lê a chave da API e os limites do arquivo .env (relido a cada chamada)."""
    load_dotenv(PASTA_PROJETO / ".env", override=True)
    chave = os.getenv("GOOGLE_PLACES_API_KEY", "").strip()
    if not chave or chave == "cole_sua_chave_aqui":
        raise ErroConfiguracao(
            "chave da API não encontrada.\n"
            "  1) Copie o arquivo .env.example para .env\n"
            "  2) Abra o .env e cole sua chave depois de GOOGLE_PLACES_API_KEY=\n"
            "Veja o passo a passo no LEIA-ME.md."
        )
    try:
        limite_diario = int(os.getenv("LIMITE_DIARIO", "30"))
        limite_mensal = int(os.getenv("LIMITE_MENSAL", "900"))
    except ValueError:
        raise ErroConfiguracao(
            "LIMITE_DIARIO e LIMITE_MENSAL no .env precisam ser números inteiros (ex.: 30 e 900)."
        )
    return chave, limite_diario, limite_mensal


class ContadorDeUso:
    """Conta as consultas à API nesta execução, no dia e no mês.

    Na Vercel a contagem fica no Upstash Redis; no computador, no arquivo
    uso_api.json (veja armazenamento.py). Pode levantar ErroArmazenamento.
    """

    def __init__(self, limite_diario, limite_mensal, limite_execucao=None):
        self.limite_diario = limite_diario
        self.limite_mensal = limite_mensal
        self.limite_execucao = limite_execucao
        agora = datetime.now(FUSO_BRASILIA)
        self.dia = agora.strftime("%Y-%m-%d")
        self.mes = agora.strftime("%Y-%m")
        self.armazenamento = armazenamento.obter()
        self.nesta_execucao = 0
        self.no_dia, self.no_mes = self.armazenamento.ler_uso(self.dia, self.mes)

    def motivo_para_parar(self):
        """Devolve o motivo se não puder fazer mais consultas; senão, None."""
        if self.limite_execucao is not None and self.nesta_execucao >= self.limite_execucao:
            return f"limite de {self.limite_execucao} consultas por execução atingido."
        if self.no_dia >= self.limite_diario:
            return (
                f"limite de {self.limite_diario} consultas por dia atingido.\n"
                "Volte amanhã ou aumente LIMITE_DIARIO no .env."
            )
        if self.no_mes >= self.limite_mensal:
            return (
                f"limite de segurança de {self.limite_mensal} consultas neste mês atingido.\n"
                "Para continuar, aumente LIMITE_MENSAL no .env (pode gerar cobrança no Google)."
            )
        return None

    def registrar(self):
        """Conta a consulta antes de chamar o Google: se não der para contar, não consulta."""
        self.no_dia, self.no_mes = self.armazenamento.somar_uso(self.dia, self.mes)
        self.nesta_execucao += 1


def tratar_erro_http(resposta):
    """Transforma o erro do Google numa mensagem em português (sempre levanta exceção)."""
    try:
        detalhe = resposta.json()["error"]["message"]
    except (ValueError, KeyError, TypeError):
        detalhe = resposta.text[:300]
    codigo = resposta.status_code
    if codigo == 400 and "API key" in detalhe:
        raise ErroFatal("chave da API inválida. Confira se copiou a chave inteira para o .env.")
    if codigo == 403:
        raise ErroFatal(
            "o Google recusou a chave (erro 403). Confira se:\n"
            "  - a 'Places API (New)' está ATIVADA no projeto;\n"
            "  - o faturamento está ativado;\n"
            "  - a restrição da chave inclui a 'Places API (New)'.\n"
            f"Detalhe do Google: {detalhe}"
        )
    if codigo == 429:
        raise ErroFatal("limite de uso do Google atingido (erro 429). Tente mais tarde.")
    raise ErroBusca(f"erro {codigo} do Google: {detalhe}")


def buscar(texto, chave, max_paginas, contador):
    """Faz a busca no Google (Text Search) e devolve a lista de lugares (20 por página)."""
    cabecalhos = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": chave,
        "X-Goog-FieldMask": CAMPOS,
    }
    corpo = {"textQuery": texto, "languageCode": "pt-BR", "regionCode": "BR", "pageSize": 20}
    lugares = []
    for _ in range(max_paginas):
        if contador.motivo_para_parar():
            print("  Limite de consultas atingido: ficando só com as páginas já baixadas.")
            break
        contador.registrar()
        try:
            resposta = requests.post(URL_API, headers=cabecalhos, json=corpo, timeout=30)
        except requests.exceptions.ConnectionError:
            raise ErroFatal("sem conexão com a internet (ou o Google está fora do ar).")
        except requests.exceptions.Timeout:
            raise ErroBusca("o Google demorou demais para responder.")
        if resposta.status_code != 200:
            tratar_erro_http(resposta)
        dados = resposta.json()
        lugares.extend(dados.get("places", []))
        token = dados.get("nextPageToken")
        if not token:
            break
        corpo["pageToken"] = token
        time.sleep(2)  # pausa curta para a próxima página ficar disponível
    return lugares


def dominio(url):
    """'https://www.instagram.com/perfil' -> 'instagram.com'"""
    if "://" not in url:
        url = "https://" + url
    try:
        host = urlparse(url).hostname or ""
    except ValueError:
        return ""
    return host.lower().removeprefix("www.")


def link_de(url, dominios):
    """True se o link é de um destes domínios (ou de um subdomínio deles)."""
    host = dominio(url) if url else ""
    return any(host == d or host.endswith("." + d) for d in dominios)


def classificar_site(url):
    """'sem_site', 'rede_social' ou 'tem_site'."""
    if not url or link_de(url, SITES_DESATIVADOS):
        return "sem_site"
    if link_de(url, REDES_SOCIAIS):
        return "rede_social"
    return "tem_site"


def para_linha(lugar):
    """Pega um lugar da resposta do Google e monta um dicionário mais simples."""
    site = lugar.get("websiteUri", "")
    return {
        "place_id": lugar.get("id", ""),
        "nome": lugar.get("displayName", {}).get("text", ""),
        "telefone": lugar.get("nationalPhoneNumber", ""),
        "endereco": lugar.get("formattedAddress", ""),
        "nota": lugar.get("rating"),
        "avaliacoes": lugar.get("userRatingCount", 0),
        "site": site,
        "situacao_site": classificar_site(site),
        "maps": lugar.get("googleMapsUri", ""),
    }


def ordenar(linhas):
    """Sem site, depois só rede social, depois tem site; em cada grupo, mais avaliações
    primeiro; no empate, maior nota."""
    return sorted(
        linhas,
        key=lambda l: (SITUACOES.index(l["situacao_site"]), -l["avaliacoes"], -(l["nota"] or 0)),
    )


def ler_argumentos():
    parser = argparse.ArgumentParser(
        description="Busca possíveis clientes no Google Maps e mostra um resumo."
    )
    parser.add_argument("buscas", nargs="*", help='ex.: "psicólogo em Brasília"')
    parser.add_argument(
        "--paginas", type=int, choices=[1, 2, 3], default=3,
        help="páginas de 20 resultados por busca; cada página = 1 consulta (padrão: 3)",
    )
    return parser.parse_args()


def pedir_buscas():
    print("Digite uma busca por linha (ex.: psicólogo em Brasília).")
    print("Para começar, deixe a linha em branco e aperte Enter.")
    buscas = []
    while True:
        texto = input("> ").strip()
        if not texto:
            return buscas
        buscas.append(texto)


def main():
    args = ler_argumentos()
    try:
        chave, limite_diario, limite_mensal = carregar_configuracao()
        contador = ContadorDeUso(limite_diario, limite_mensal, LIMITE_POR_EXECUCAO)
    except (ErroConfiguracao, armazenamento.ErroArmazenamento) as erro:
        sys.exit(f"ERRO: {erro}")
    buscas = args.buscas or pedir_buscas()
    if not buscas:
        sys.exit("Nenhuma busca informada.")
    if len(buscas) * args.paginas > LIMITE_POR_EXECUCAO:
        print(
            f"Atenção: {len(buscas)} buscas x {args.paginas} páginas podem passar de "
            f"{LIMITE_POR_EXECUCAO} consultas; as últimas buscas podem ficar de fora.\n"
        )

    encontrados = {}  # place ID -> linha (evita repetidos entre buscas)
    for busca in buscas:
        motivo = contador.motivo_para_parar()
        if motivo:
            print(f"PARANDO: {motivo}")
            break
        print(f'Buscando "{busca}"...')
        try:
            lugares = buscar(busca, chave, args.paginas, contador)
        except ErroBusca as erro:
            print(f"  Pulando esta busca: {erro}")
            continue
        except (ErroFatal, armazenamento.ErroArmazenamento) as erro:
            print(f"ERRO: {erro}")
            break

        novos = 0
        for lugar in lugares:
            linha = para_linha(lugar)
            if linha["place_id"] not in encontrados:
                encontrados[linha["place_id"]] = linha
                novos += 1
        print(f"  {len(lugares)} resultados, {novos} novos.")

    if encontrados:
        situacoes = Counter(linha["situacao_site"] for linha in encontrados.values())
        print(
            f"\nResumo: {len(encontrados)} estabelecimentos: {situacoes['sem_site']} sem site, "
            f"{situacoes['rede_social']} só rede social, {situacoes['tem_site']} com site."
        )
        print("Para ver os detalhes e entrar em contato, use a interface web (cwd_leads.py).")
    else:
        print("\nNada encontrado.")

    print(
        f"\nConsultas à API nesta execução: {contador.nesta_execucao} de {LIMITE_POR_EXECUCAO}"
        f" (hoje: {contador.no_dia} de {contador.limite_diario};"
        f" no mês: {contador.no_mes} de {contador.limite_mensal})."
    )


if __name__ == "__main__":
    main()
