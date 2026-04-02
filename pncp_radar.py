import csv
import time
import logging
import requests
from datetime import date, timedelta
from typing import List, Dict, Any

# =========================
# CONFIGURAÇÃO COMERCIAL FAUS
# =========================
API_BASE = "https://pncp.gov.br/api/consulta/v1/contratacoes/publicacao"
TIMEOUT = 60
PAGE_SIZE = 50
DIAS_ATRAS = 60 
DELAY = 0.5

# RAIO DE 200KM (Principais cidades da região de Rio Preto, Noroeste e arredores)
MUNICIPIOS = [
    3524709, 3543402, 3531308, 3500550, 3548500, 3510708, 3557303, 3549805, # Iniciais
    3511508, 3556008, 3520400, 3506003, 3515509, 3533908, 3510104, 3530607, # Polo Catanduva/Votuporanga
    3503208, 3502804, 3505500, 3537305, 3540002, 3527108, 3505906, 3522109, # Polo Araçatuba/Lins
    3505302, 3518602, 3533502, 3514403, 3531100, 3516408, 3542206, 3521101  # Polo Barretos/Araraquara
]

MODALIDADES = [4, 5, 6, 7]

# PALAVRAS-CHAVE CALIBRADAS (VISÃO CLAUDE + GEMINI)
OBRA_NOVA = ["construção de", "construcao de", "implantação de", "execução de obra de", "unidade básica", "ubs", "creche", "escola municipal"]
TERRA_PESADA = ["terraplenagem", "terraplanagem", "escavação", "escavacao", "drenagem", "limpeza de terreno", "demolição", "demolicao", "aterro", "valas"]
FILTRO_LIXO = ["marmitex", "alimento", "merenda", "informática", "limpeza urbana", "roçada", "poda", "ar condicionado", "elétrica"]

OUTPUT_CSV = "radar_faus_completo.csv"
OUTPUT_TXT = "relatorio_leitura_faus.txt"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

# =========================
# MOTOR ROBUSTO (NÃO MEXER)
# =========================

def score_obra(texto):
    txt = (texto or "").lower()
    if any(l in txt for l in FILTRO_LIXO): return "C", 0, ""
    
    score = 0
    sinais = []
    
    for p in OBRA_NOVA:
        if p in txt:
            score += 15
            sinais.append(p.upper())
    
    for p in TERRA_PESADA:
        if p in txt:
            score += 5
            sinais.append(p.upper())
            
    if score >= 15: return "⭐ OURO: OBRA NOVA", score, ", ".join(sinais)
    if score >= 5: return "✅ PRATA: MÁQUINA/TERRA", score, ", ".join(sinais)
    return "C", 0, ""

def fetch_page(data_inicial, data_final, modalidade, municipio, pagina, max_tentativas=3):
    params = {
        "dataInicial": data_inicial, "dataFinal": data_final,
        "codigoModalidadeContratacao": modalidade, "codigoMunicipioIbge": municipio,
        "uf": "SP", "pagina": pagina, "tamanhoPagina": PAGE_SIZE,
    }
    for tentativa in range(1, max_tentativas + 1):
        try:
            r = requests.get(API_BASE, params=params, timeout=TIMEOUT)
            r.raise_for_status()
            if not r.text.strip(): return []
            return r.json()
        except Exception as e:
            log.warning(f"Tentativa {tentativa} falhou em {municipio}: {e}")
            if tentativa < max_tentativas: time.sleep(2 * tentativa)
    return {}

def search_all(data_ini, data_fim):
    results = []
    for mun in MUNICIPIOS:
        for mod in MODALIDADES:
            pag = 1
            while True:
                payload = fetch_page(data_ini, data_fim, mod, mun, pag)
                items = payload.get('resultado', []) if isinstance(payload, dict) else payload
                if not items: break
                
                for item in items:
                    desc = f"{item.get('objetoCompra','')} {item.get('descricao','')}"
                    status, score, sinais = score_obra(desc)
                    if status == "C": continue
                    
                    results.append({
                        "STATUS": status,
                        "SCORE": score,
                        "CIDADE": item.get('unidadeOrgao', {}).get('municipioNome', '').upper(),
                        "DATA": item.get('dataPublicacaoPncp', '')[:10],
                        "VALOR": item.get('valorTotalEstimado', 0),
                        "SINAIS": sinais,
                        "LINK": f"https://pncp.gov.br/app/editais/{item.get('orgaoEntidade', {}).get('cnpj', '')}/{item.get('anoCompra', '')}/{str(item.get('sequencialCompra', '')).zfill(6)}",
                        "TEXTO": desc[:300]
                    })
                
                if not isinstance(payload, dict) or pag >= payload.get('totalPaginas', 1): break
                pag += 1
                time.sleep(DELAY)
    return results

def save_outputs(results):
    if not results: return
    # Ordenar por Score e Data
    results.sort(key=lambda x: (x['SCORE'], x['DATA']), reverse=True)
    
    # Salvar CSV
    keys = results[0].keys()
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        writer.writerows(results)
    
    # Salvar TXT Visual
    with open(OUTPUT_TXT, "w", encoding="utf-8") as f:
        f.write(f"=== RELATÓRIO DE PROSPECÇÃO FAUS ENGENHARIA ===\nGerado em: {date.today()}\n\n")
        for r in results:
            f.write(f"{r['STATUS']} em {r['CIDADE']}\n")
            f.write(f"VALOR: R$ {r['VALOR']:,.2f} | DATA: {r['DATA']}\n")
            f.write(f"SINAIS: {r['SINAIS']}\n")
            f.write(f"RESUMO: {r['TEXTO']}...\n")
            f.write(f"LINK: {r['LINK']}\n")
            f.write(f"{'-'*60}\n\n")

def main():
    hoje = date.today()
    data_fim = hoje.strftime("%Y%m%d")
    data_ini = (hoje - timedelta(days=DIAS_ATRAS)).strftime("%Y%m%d")
    log.info(f"Iniciando busca robusta: {data_ini} a {data_fim}")
    res = search_all(data_ini, data_fim)
    save_outputs(res)
    log.info(f"Finalizado. {len(res)} oportunidades encontradas.")

if __name__ == "__main__":
    main()
