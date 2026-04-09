import csv
import logging
import requests
import unicodedata
from datetime import date, timedelta
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# =========================
# CONFIGURAÇÃO COMERCIAL FAUS - V3 ROBUSTA
# =========================
API_BASE = "https://pncp.gov.br/api/consulta/v1/contratacoes/publicacao"
TIMEOUT = 60
DIAS_ATRAS = 60
TAMANHO_PAGINA = 50
UF = "SP"

MUNICIPIOS = [
    3524709, 3543402, 3531308, 3500550, 3548500, 3510708, 3557303, 3549805,
    3511508, 3556008, 3520400, 3506003, 3515509, 3533908, 3510104, 3530607,
    3503208, 3502804, 3505500, 3537305, 3540002, 3527108, 3505906, 3522109,
    3505302, 3518602, 3533502, 3514403, 3531100, 3516408, 3542206, 3521101
]

OBRA_NOVA = [
    "construcao", "implantacao", "execucao de obra", "unidade basica",
    "ubs", "creche", "escola", "ampliacao", "pavimentacao"
]

TERRA_PESADA = [
    "terraplenagem", "terraplanagem", "escavacao", "drenagem",
    "limpeza de terreno", "demolicao", "aterro", "valas",
    "fundacao", "infraestrutura"
]

FILTRO_LIXO = [
    "marmitex", "alimento", "merenda", "informatica", "rocada", "roçada",
    "poda", "limpeza urbana", "aquisicao de", "aquisição de",
    "registro de preco", "registro de preço",
    "fornecimento de material", "compra de tubos",
    "aquisicao de tubos", "aquisição de tubos"
]

CSV_FIELDS = [
    "STATUS", "SCORE", "CIDADE", "DATA", "VALOR", "LINK", "TEXTO", "SINAIS"
]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger(__name__)


def criar_sessao():
    session = requests.Session()

    retry = Retry(
        total=3,
        connect=3,
        read=3,
        backoff_factor=1.0,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"]
    )

    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)

    session.headers.update({
        "User-Agent": "RadarFAUS/3.0"
    })

    return session


def simplificar_texto(texto):
    if not texto:
        return ""
    texto = str(texto)
    return "".join(
        c for c in unicodedata.normalize("NFD", texto)
        if unicodedata.category(c) != "Mn"
    ).lower()


def avaliar_obra(texto_original):
    txt = simplificar_texto(texto_original)

    if any(lixo in txt for lixo in FILTRO_LIXO):
        return "C", 0, ""

    score = 0
    sinais = []

    for termo in OBRA_NOVA:
        if termo in txt:
            score += 15
            sinais.append(termo.upper())

    for termo in TERRA_PESADA:
        if termo in txt:
            score += 5
            sinais.append(termo.upper())

    if score >= 15:
        return "⭐ OURO: OBRA NOVA", score, ", ".join(sinais)
    if score >= 5:
        return "✅ PRATA: MÁQUINA/TERRA", score, ", ".join(sinais)

    return "C", 0, ""


def safe_str(value, default=""):
    if value is None:
        return default
    return str(value)


def safe_date_yyyy_mm_dd(value):
    if not value:
        return ""
    value = safe_str(value)
    return value[:10]


def safe_float(value, default=0):
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def montar_link(item):
    orgao = item.get("orgaoEntidade") or {}
    cnpj = safe_str(orgao.get("cnpj"))
    ano = safe_str(item.get("anoCompra"))
    sequencial = safe_str(item.get("sequencialCompra")).zfill(6)

    if not cnpj or not ano or not sequencial.strip("0"):
        return ""

    return f"https://pncp.gov.br/app/editais/{cnpj}/{ano}/{sequencial}"


def extrair_descricao(item):
    objeto = safe_str(item.get("objetoCompra"))
    descricao = safe_str(item.get("descricao"))
    texto = f"{objeto} {descricao}".strip()
    return " ".join(texto.split())  # remove espaços duplicados


def buscar_pagina(session, municipio, modalidade, pagina, data_ini, data_fim):
    params = {
        "dataInicial": data_ini,
        "dataFinal": data_fim,
        "codigoModalidadeContratacao": modalidade,
        "codigoMunicipioIbge": municipio,
        "uf": UF,
        "pagina": pagina,
        "tamanhoPagina": TAMANHO_PAGINA
    }

    response = session.get(API_BASE, params=params, timeout=TIMEOUT)
    response.raise_for_status()

    try:
        return response.json()
    except ValueError as exc:
        raise RuntimeError(f"Resposta não é JSON válido. Texto: {response.text[:300]}") from exc


def processar_item(item):
    desc = extrair_descricao(item)
    status, score, sinais = avaliar_obra(desc)

    if status == "C":
        return None

    unidade = item.get("unidadeOrgao") or {}
    cidade = safe_str(unidade.get("municipioNome")).upper()

    return {
        "STATUS": status,
        "SCORE": score,
        "CIDADE": cidade,
        "DATA": safe_date_yyyy_mm_dd(item.get("dataPublicacaoPncp")),
        "VALOR": safe_float(item.get("valorTotalEstimado"), 0),
        "LINK": montar_link(item),
        "TEXTO": desc[:300],
        "SINAIS": sinais
    }


def buscar_contratacoes():
    hoje = date.today()
    data_ini = (hoje - timedelta(days=DIAS_ATRAS)).strftime("%Y%m%d")
    data_fim = hoje.strftime("%Y%m%d")

    session = criar_sessao()
    resultados = []
    vistos = set()

    for municipio in MUNICIPIOS:
        log.info("Buscando município %s", municipio)

        for modalidade in [4, 5, 6, 7]:
            pagina = 1

            while True:
                try:
                    payload = buscar_pagina(
                        session=session,
                        municipio=municipio,
                        modalidade=modalidade,
                        pagina=pagina,
                        data_ini=data_ini,
                        data_fim=data_fim
                    )

                    items = payload.get("resultado") or []
                    if not items:
                        break

                    log.info(
                        "Mun %s | Mod %s | Página %s | %s itens",
                        municipio, modalidade, pagina, len(items)
                    )

                    for item in items:
                        registro = processar_item(item)
                        if not registro:
                            continue

                        chave_unica = (
                            registro["LINK"],
                            registro["DATA"],
                            registro["CIDADE"],
                            registro["TEXTO"]
                        )

                        if chave_unica in vistos:
                            continue

                        vistos.add(chave_unica)
                        resultados.append(registro)

                    # Se retornou menos que o tamanho da página, acabou
                    if len(items) < TAMANHO_PAGINA:
                        break

                    pagina += 1

                except requests.HTTPError as exc:
                    status_code = getattr(exc.response, "status_code", "sem_status")
                    body = getattr(exc.response, "text", "")[:300]
                    log.error(
                        "HTTP error | mun=%s mod=%s pag=%s status=%s body=%s",
                        municipio, modalidade, pagina, status_code, body
                    )
                    break

                except requests.RequestException as exc:
                    log.exception(
                        "Erro de rede | mun=%s mod=%s pag=%s | %s",
                        municipio, modalidade, pagina, exc
                    )
                    break

                except Exception as exc:
                    log.exception(
                        "Erro inesperado | mun=%s mod=%s pag=%s | %s",
                        municipio, modalidade, pagina, exc
                    )
                    break

    return resultados


def salvar_csv(resultados, caminho="radar_faus_completo.csv"):
    with open(caminho, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        if resultados:
            writer.writerows(resultados)


def salvar_relatorio(resultados, caminho="relatorio_leitura_faus.txt"):
    with open(caminho, "w", encoding="utf-8") as f:
        f.write(f"RELATORIO FAUS - {len(resultados)} OPORTUNIDADES\n\n")

        if not resultados:
            f.write("Nenhuma oportunidade encontrada.\n")
            return

        for r in resultados:
            valor_formatado = f"R$ {r['VALOR']:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            f.write(
                f"{r['STATUS']} - {r['CIDADE']}\n"
                f"DATA: {r['DATA']}\n"
                f"VALOR: {valor_formatado}\n"
                f"SINAIS: {r['SINAIS']}\n"
                f"LINK: {r['LINK']}\n"
                f"TEXTO: {r['TEXTO']}\n\n"
            )


def main():
    log.info("Iniciando coleta PNCP...")
    resultados = buscar_contratacoes()

    # opcional: ordenar por score e valor
    resultados.sort(key=lambda x: (x["SCORE"], x["VALOR"]), reverse=True)

    salvar_csv(resultados)
    salvar_relatorio(resultados)

    log.info("Finalizado. %s oportunidades salvas.", len(resultados))


if __name__ == "__main__":
    main()
