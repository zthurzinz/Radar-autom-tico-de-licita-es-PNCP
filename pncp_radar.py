import csv
import time
import logging
import requests
from datetime import date, timedelta
from typing import List, Dict, Any

# =========================
# CONFIGURAÇÃO COMERCIAL
# =========================

API_BASE = "https://pncp.gov.br/api/consulta/v1/contratacoes/publicacao"
TIMEOUT = 60
PAGE_SIZE = 50
DIAS_ATRAS = 60  # Puxando os últimos 2 meses
DELAY = 0.4

# Municípios foco da Faus Engenharia
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

MODALIDADES = [4, 5, 6, 7]

# Filtros de Ouro (Infraestrutura e Locação)
HIGH_PRIORITY = [
    "terraplenagem", "terraplanagem", "escavação", "escavacao",
    "drenagem", "galeria pluvial", "rede pluvial",
    "pavimentação", "pavimentacao", "asfáltica", "asfaltica", "recapeamento",
    "retroescavadeira", "locação de maquina", "locacao de maquina",
    "fundações", "fundacoes", "guias e sarjetas", "infraestrutura urbana"
]

# Palavras que tiram pontos (Marmitex, TI, Alimentos)
LOW_PRIORITY = [
    "alimento", "marmitex", "refeição", "merenda", "escola", "creche",
    "informática", "software", "medicamentos", "limpeza urbana"
]

OUTPUT_REPORT = "relatorio_obras_faus.txt"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

# =========================
# FUNÇÕES DE INTELIGÊNCIA
# =========================

def normalize(text: str) -> str:
    return " ".join((text or "").lower().split())

def score_text(text: str):
    txt = normalize(text)
    
    # Se contiver palavras irrelevantes, descarta (prioridade C)
    if any(w in txt for w in LOW_PRIORITY):
        return "C", 0, ""

    high_hits = [w for w in HIGH_PRIORITY if w in txt]
    score = len(high_hits) * 5

    if score >= 5:
        return "⭐ ALTA (Ouro)", score, ", ".join(high_hits).upper()
    return "C", 0, ""

def fetch_page(data_inicial, data_final, modalidade, municipio, pagina, max_tentativas=3):
    params = {
        "dataInicial": data_inicial,
        "dataFinal": data_final,
        "codigoModalidadeContratacao": modalidade,
        "codigoMunicipioIbge": municipio,
        "uf": "SP",
        "pagina": pagina,
        "tamanhoPagina": PAGE_SIZE,
    }

    for tentativa in range(1, max_tentativas + 1):
        try:
            r = requests.get(API_BASE, params=params, timeout=TIMEOUT)
            r.raise_for_status()
            if not r.text.strip(): return []
            return r.json()
        except Exception:
            if tentativa < max_tentativas: time.sleep(2 * tentativa)
    return {}

def search_all(data_inicial: str, data_final: str):
    opportunities = []

    for municipio in MUNICIPIOS:
        for modalidade in MODALIDADES:
            pagina = 1
            while True:
                payload = fetch_page(data_inicial, data_final, modalidade, municipio, pagina)
                items = []
                if isinstance(payload, dict):
                    items = payload.get("resultado", []) or payload.get("data", [])
                
                if not items: break

                for item in items:
                    unidade = item.get("unidadeOrgao") or {}
                    texto_completo = f"{item.get('objetoCompra','')} {item.get('descricao','')}"
                    status, score, sinais = score_text(texto_completo)

                    if status == "C": continue

                    opportunities.append({
                        "status": status,
                        "cidade": unidade.get("municipioNome", "N/A").upper(),
                        "valor": item.get("valorTotalEstimado", 0),
                        "data": item.get("dataPublicacaoPncp", "")[:10],
                        "sinais": sinais,
                        "link": f"https://pncp.gov.br/app/editais/{item.get('orgaoEntidade', {}).get('cnpj', '')}/{item.get('anoCompra', '')}/{str(item.get('sequencialCompra', '')).zfill(6)}",
                        "resumo": texto_completo[:400]
                    })

                if pagina >= payload.get("totalPaginas", 1): break
                pagina += 1
                time.sleep(DELAY)

    return opportunities

def generate_visual_report(opportunities):
    hoje = date.today().strftime("%d/%m/%Y")
    lines = [
        "===========================================================\n",
        f"   RELATÓRIO DE OPORTUNIDADES - FAUS ENGENHARIA\n",
        f"   DATA DO RELATÓRIO: {hoje}\n",
        "===========================================================\n\n"
    ]

    if not opportunities:
        lines.append("Nenhuma obra relevante encontrada no período.\n")
    else:
        # Ordena pelas mais recentes
        opportunities.sort(key=lambda x: x['data'], reverse=True)
        
        for op in opportunities:
            lines.append(f"📍 CIDADE: {op['cidade']}\n")
            lines.append(f"📊 STATUS: {op['status']}\n")
            lines.append(f"📅 DATA PUBLICAÇÃO: {op['data']}\n")
            lines.append(f"💰 VALOR ESTIMADO: R$ {op['valor']:,.2f}\n")
            lines.append(f"🛠 SERVIÇOS DETECTADOS: {op['sinais']}\n")
            lines.append(f"📝 RESUMO: {op['resumo']}...\n")
            lines.append(f"🔗 LINK DIRETO: {op['link']}\n")
            lines.append("-" * 60 + "\n\n")

    with open(OUTPUT_REPORT, "w", encoding="utf-8") as f:
        f.writelines(lines)
    log.info(f"Relatório visual gerado: {OUTPUT_REPORT}")

def main():
    hoje = date.today()
    data_final = hoje.strftime("%Y%m%d")
    data_inicial = (hoje - timedelta(days=DIAS_ATRAS)).strftime("%Y%m%d")

    log.info(f"Iniciando Radar Faus | Período: {data_inicial} → {data_final}")

    results = search_all(data_inicial, data_final)
    generate_visual_report(results)

if __name__ == "__main__":
    main()
