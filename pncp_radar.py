import csv
import time
import logging
import requests
import unicodedata
from datetime import date, timedelta

# =========================
# CONFIGURAÇÃO COMERCIAL FAUS - V2 BLINDADA
# =========================
API_BASE = "https://pncp.gov.br/api/consulta/v1/contratacoes/publicacao"
TIMEOUT = 60
DIAS_ATRAS = 60 

# Municípios expandidos
MUNICIPIOS = [
    3524709, 3543402, 3531308, 3500550, 3548500, 3510708, 3557303, 3549805,
    3511508, 3556008, 3520400, 3506003, 3515509, 3533908, 3510104, 3530607,
    3503208, 3502804, 3505500, 3537305, 3540002, 3527108, 3505906, 3522109,
    3505302, 3518602, 3533502, 3514403, 3531100, 3516408, 3542206, 3521101
]

# Termos normalizados (sem acento para busca cega)
OBRA_NOVA = ["construcao", "implantacao", "execucao de obra", "unidade basica", "ubs", "creche", "escola"]
TERRA_PESADA = ["terraplenagem", "terraplanagem", "escavacao", "drenagem", "limpeza de terreno", "demolicao", "aterro", "valas"]
FILTRO_LIXO = ["marmitex", "alimento", "merenda", "informatica", "roçada", "poda"]

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

def simplificar_texto(texto):
    if not texto: return ""
    # Remove acentos e deixa minúsculo
    return "".join(c for c in unicodedata.normalize('NFD', texto) if unicodedata.category(c) != 'Mn').lower()

def avaliar_obra(texto_original):
    txt = simplificar_texto(texto_original)
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

def main():
    hoje = date.today()
    data_ini = (hoje - timedelta(days=DIAS_ATRAS)).strftime("%Y%m%d")
    data_fim = hoje.strftime("%Y%m%d")
    results = []

    for mun in MUNICIPIOS:
        log.info(f"Buscando em {mun}...")
        for mod in [4, 5, 6, 7]:
            try:
                params = {"dataInicial": data_ini, "dataFinal": data_fim, "codigoModalidadeContratacao": mod, "codigoMunicipioIbge": mun, "uf": "SP", "pagina": 1, "tamanhoPagina": 50}
                r = requests.get(API_BASE, params=params, timeout=TIMEOUT)
                if r.status_code == 200:
                    data = r.json()
                    items = data.get('resultado', [])
                    for item in items:
                        desc = f"{item.get('objetoCompra','')} {item.get('descricao','')}"
                        status, score, sinais = avaliar_obra(desc)
                        if status != "C":
                            results.append({
                                "STATUS": status, "SCORE": score, "CIDADE": item.get('unidadeOrgao', {}).get('municipioNome', '').upper(),
                                "DATA": item.get('dataPublicacaoPncp', '')[:10], "VALOR": item.get('valorTotalEstimado', 0),
                                "LINK": f"https://pncp.gov.br/app/editais/{item.get('orgaoEntidade', {}).get('cnpj', '')}/{item.get('anoCompra', '')}/{str(item.get('sequencialCompra', '')).zfill(6)}",
                                "TEXTO": desc[:300]
                            })
            except: continue

    # CRIA OS ARQUIVOS MESMO SE ESTIVEREM VAZIOS PARA NÃO DAR ERRO NO GITHUB
    with open("radar_faus_completo.csv", "w", encoding="utf-8-sig") as f:
        if results:
            writer = csv.DictWriter(f, fieldnames=results[0].keys())
            writer.writeheader()
            writer.writerows(results)
    
    with open("relatorio_leitura_faus.txt", "w", encoding="utf-8") as f:
        f.write(f"RELATORIO FAUS - {len(results)} OPORTUNIDADES\n\n")
        for r in results:
            f.write(f"{r['STATUS']} - {r['CIDADE']}\nVALOR: R$ {r['VALOR']}\nLINK: {r['LINK']}\n\n")

if __name__ == "__main__":
    main()
