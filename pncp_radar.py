import csv
import logging
import requests
import unicodedata
from datetime import date, timedelta
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Configurações de Rede
TIMEOUT_LEITURA = 40
MUNICIPIOS = [3524709, 3543402, 3531308, 3500550, 3548500, 3510708, 3557303, 3549805, 3511508, 3556008, 3520400, 3506003, 3515509, 3533908, 3510104, 3530607, 3503208, 3502804, 3505500, 3537305, 3540002, 3527108, 3505906, 3522109, 3505302, 3518602, 3533502, 3514403, 3531100, 3516408, 3542206, 3521101]

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

def buscar_pagina(session, municipio, modalidade, data_ini, data_fim):
    params = {
        "dataInicial": data_ini, "dataFinal": data_fim,
        "codigoModalidadeContratacao": modalidade,
        "codigoMunicipioIbge": municipio, "uf": "SP",
        "pagina": 1, "tamanhoPagina": 50
    }
    try:
        resp = session.get("https://pncp.gov.br/api/consulta/v1/contratacoes/publicacao", params=params, timeout=(10, TIMEOUT_LEITURA))
        if resp.status_code == 200:
            return resp.json(), False # Sucesso, sem falha
        return None, True # Resposta errada da API (Falha)
    except:
        return None, True # Timeout ou queda (Falha)

def main():
    log.info("Iniciando Radar FAUS V6...")
    hoje = date.today()
    data_ini = (hoje - timedelta(days=60)).strftime("%Y%m%d")
    data_fim = hoje.strftime("%Y%m%d")
    
    session = requests.Session()
    session.mount("https://", HTTPAdapter(max_retries=Retry(total=2)))
    
    resultados = []
    total_falhas = 0
    total_tentativas = 0

    for mun in MUNICIPIOS:
        for mod in [4, 5, 6, 7]:
            total_tentativas += 1
            payload, houve_falha = buscar_pagina(session, mun, mod, data_ini, data_fim)
            
            if houve_falha:
                total_falhas += 1
                continue
            
            if payload:
                items = payload.get("resultado") or []
                # ... aqui entra sua lógica de processar_item() e avaliar_obra() ...
                # Para o exemplo, vamos supor que preenchemos 'resultados'
                pass

    # ==========================
    # LÓGICA OBJETIVA DE SUCESSO
    # ==========================
    num_registros = len(resultados)
    
    log.info(f"Tentativas: {total_tentativas} | Falhas de API: {total_falhas} | Registros: {num_registros}")

    # A trava:
    if num_registros == 0 and total_falhas > 0:
        msg_erro = f"ERRO CRÍTICO: 0 registros encontrados, mas houve {total_falhas} falhas de conexão/API."
        log.error(msg_erro)
        raise RuntimeError(msg_erro) # Isso mata o pipeline e te avisa

    # Salvamento garantido
    with open("radar_faus_completo.csv", "w", encoding="utf-8-sig", newline="") as f:
        # writer = csv.DictWriter... writer.writeheader()... writer.writerows(resultados)
        pass
    
    log.info("Processo finalizado com integridade.")

if __name__ == "__main__":
    main()
