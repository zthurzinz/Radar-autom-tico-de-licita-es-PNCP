import csv
import time
import logging
import requests
from datetime import date, timedelta
from typing import List, Dict, Any

# =========================
# CONFIGURAÇÃO
# =========================

API_BASE = "https://pncp.gov.br/api/consulta/v1/contratacoes/publicacao"
TIMEOUT = 60
PAGE_SIZE = 50
DIAS_ATRAS = 2
DELAY = 0.4

# Municípios (IBGE)
MUNICIPIOS = [
    3524709,  # São José do Rio Preto
    3543402,  # Mirassol
    3531308,  # José Bonifácio
    3500550,  # Adolfo
    3548500,  # Nova Granada
    3510708,  # Cedral
    3557303,  # Tanabi
    3549805,  # Olímpia
]

# Modalidades
MODALIDADES = [4, 5, 6, 7]

# Palavras-chave
HIGH_PRIORITY = [
    "terraplenagem", "terraplanagem",
    "escavação", "escavacao",
    "drenagem", "galeria pluvial", "rede pluvial",
    "pavimentação", "pavimentacao",
    "retroescavadeira", "locação de maquina", "locacao de maquina",
    "fundações", "fundacoes",
    "infraestrutura",
    "aterro", "compactação", "compactacao",
]

MEDIUM_PRIORITY = [
    "ubs", "escola", "creche",
    "construção", "construcao",
    "execução", "execucao",
    "ampliação", "ampliacao",
    "obra civil",
]

LOW_PRIORITY = [
    "reforma", "manutenção", "manutencao",
    "fornecimento de material",
    "aquisição", "aquisicao",
    "medicamentos", "equipamentos de informática",
    "mobiliário", "mobiliario",
    "material de consumo",
    "limpeza urbana",
]

OUTPUT_CSV = "pncp_oportunidades.csv"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

# =========================
# FUNÇÕES
# =========================

def normalize(text: str) -> str:
    return " ".join((text or "").lower().split())

def score_text(text: str):
    txt = normalize(text)

    high_hits = [w for w in HIGH_PRIORITY if normalize(w) in txt]
    medium_hits = [w for w in MEDIUM_PRIORITY if normalize(w) in txt]
    low_hits = [w for w in LOW_PRIORITY if normalize(w) in txt]

    score = len(high_hits) * 4 + len(medium_hits) * 2 - len(low_hits) * 3

    if score >= 6:
        prioridade = "A"
    elif score >= 2:
        prioridade = "B"
    else:
        prioridade = "C"

    return prioridade, score, ", ".join(high_hits), ", ".join(medium_hits), ", ".join(low_hits)

def extract_items(payload: Any):
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ["data", "items", "resultado", "content"]:
            if isinstance(payload.get(key), list):
                return payload[key]
    return []

def extract_text(item: Dict[str, Any]) -> str:
    parts = [
        item.get("objetoCompra"),
        item.get("objetoContratacao"),
        item.get("descricao"),
        item.get("informacaoComplementar"),
        item.get("titulo"),
    ]
    return " | ".join(str(p) for p in parts if p)

def build_web_link(item: Dict[str, Any]) -> str:
    org = item.get("orgaoEntidade") or {}
    cnpj = org.get("cnpj") or item.get("cnpj", "")
    ano = item.get("anoCompra") or item.get("anoContratacao", "")
    seq = item.get("sequencialCompra") or item.get("sequencialContratacao")

    if cnpj and ano and seq is not None:
        return f"https://pncp.gov.br/app/editais/{cnpj}/{ano}/{str(seq).zfill(6)}"
    return item.get("linkSistemaOrigem", "")

def fetch_page(data_inicial, data_final, modalidade, municipio, pagina):
    params = {
        "dataInicial": data_inicial,
        "dataFinal": data_final,
        "codigoModalidadeContratacao": modalidade,
        "codigoMunicipioIbge": municipio,
        "uf": "SP",
        "pagina": pagina,
        "tamanhoPagina": PAGE_SIZE,
    }

    r = requests.get(API_BASE, params=params, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()

def search_all(data_inicial: str, data_final: str) -> List[Dict[str, Any]]:
    rows = []

    for municipio in MUNICIPIOS:
        for modalidade in MODALIDADES:
            pagina = 1

            while True:
                try:
                    payload = fetch_page(data_inicial, data_final, modalidade, municipio, pagina)
                except Exception as e:
                    log.error(f"Erro | municipio={municipio} | modalidade={modalidade} | pag={pagina} | {e}")
                    break

                items = extract_items(payload)
                if not items:
                    break

                for item in items:
                    texto = extract_text(item)
                    if not texto:
                        continue

                    prioridade, score, high, med, low = score_text(texto)
                    if prioridade == "C":
                        continue

                    unidade = item.get("unidadeOrgao") or {}

                    rows.append({
                        "prioridade": prioridade,
                        "score": score,
                        "cidade": unidade.get("municipioNome", ""),
                        "uf": unidade.get("ufSigla", ""),
                        "data_publicacao": item.get("dataPublicacaoPncp", ""),
                        "valor_estimado": item.get("valorTotalEstimado", ""),
                        "sinais_fortes": high,
                        "sinais_medios": med,
                        "sinais_fracos": low,
                        "numero_pncp": item.get("numeroControlePNCP", ""),
                        "link": build_web_link(item),
                        "texto": texto,
                    })

                total_paginas = payload.get("totalPaginas", 1)
                if pagina >= total_paginas:
                    break

                pagina += 1
                time.sleep(DELAY)

    return rows

def deduplicate(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = {}
    for row in rows:
        key = row["numero_pncp"] or row["link"] or row["texto"][:100]
        if key not in seen or row["score"] > seen[key]["score"]:
            seen[key] = row
    return list(seen.values())

def save_csv(rows: List[Dict[str, Any]]) -> None:
    if not rows:
        log.info("Nenhum resultado para salvar.")
        return

    fieldnames = [
        "prioridade", "score", "cidade", "uf", "data_publicacao", "valor_estimado",
        "sinais_fortes", "sinais_medios", "sinais_fracos",
        "numero_pncp", "link", "texto"
    ]

    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    log.info(f"CSV salvo: {OUTPUT_CSV}")

def main():
    hoje = date.today()
    # CORREÇÃO: Formato de data ajustado para YYYYMMDD (sem hífens)
    data_final = hoje.strftime("%Y%m%d")
    data_inicial = (hoje - timedelta(days=DIAS_ATRAS)).strftime("%Y%m%d")

    log.info(f"Iniciando busca | período: {data_inicial} → {data_final}")

    rows = search_all(data_inicial, data_final)
    rows = deduplicate(rows)
    rows.sort(key=lambda x: x["score"], reverse=True)

    log.info(f"Resultados úteis: {len(rows)}")
    save_csv(rows)

if __name__ == "__main__":
    main()
