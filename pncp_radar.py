import csv
import logging
import requests
import unicodedata
from datetime import date, timedelta
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# =========================
# CONFIGURAÇÃO COMERCIAL FAUS - V4 (PERFORMANCE)
# =========================
API_BASE = "https://pncp.gov.br/api/consulta/v1/contratacoes/publicacao"
TIMEOUT_CONEXAO = 10  # Tempo para estabelecer conexão
TIMEOUT_LEITURA = 35  # Reduzido para evitar o acúmulo de 50+ minutos
DIAS_ATRAS = 60
TAMANHO_PAGINA = 50
UF = "SP"

MUNICIPIOS = [
    3524709, 3543402, 3531308, 3500550, 3548500, 3510708, 3557303, 3549805,
    3511508, 3556008, 3520400, 3506003, 3515509, 3533908, 3510104, 3530607,
    3503208, 3502804, 3505500, 3537305, 3540002, 3527108, 3505906, 3522109,
    3505302, 3518602, 3533502, 3514403, 3531100, 3516408, 3542206, 3521101
]

CSV_FIELDS = ["STATUS", "SCORE", "CIDADE", "DATA", "VALOR", "LINK", "TEXTO", "SINAIS"]

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

def criar_sessao():
    session = requests.Session()
    # Backoff menor para não estender demais a execução em caso de falha repetida
    retry = Retry(
        total=2, 
        backoff_factor=1, 
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"]
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.headers.update({"User-Agent": "RadarFAUS/4.0"})
    return session

def buscar_pagina(session, municipio, modalidade, pagina, data_ini, data_fim):
    params = {
        "dataInicial": data_ini, "dataFinal": data_fim,
        "codigoModalidadeContratacao": modalidade,
        "codigoMunicipioIbge": municipio, "uf": UF,
        "pagina": pagina, "tamanhoPagina": TAMANHO_PAGINA
    }
    
    try:
        # Uso de tupla no timeout (conexão, leitura)
        response = session.get(API_BASE, params=params, timeout=(TIMEOUT_CONEXAO, TIMEOUT_LEITURA))
        
        # Validação de sanidade da resposta
        if response.status_code != 200:
            log.warning(f"Status {response.status_code} para Mun {municipio}")
            return None
        
        if "application/json" not in response.headers.get("Content-Type", "").lower():
            log.error(f"Resposta não é JSON em Mun {municipio}")
            return None

        return response.json()

    except requests.exceptions.RequestException as e:
        log.error(f"Erro na chamada Mun {municipio} | Mod {modalidade}: {type(e).__name__}")
        return None

def processar_item(item):
    # (Mantendo sua lógica de filtro original para brevidade, assumindo que avaliar_obra existe)
    # Aqui entrariam as funções avaliar_obra, simplificar_texto, etc. do seu código original
    pass 

# ... (Funções auxiliares: simplificar_texto, avaliar_obra, montar_link permanecem as mesmas)

def buscar_contratacoes():
    hoje = date.today()
    data_ini = (hoje - timedelta(days=DIAS_ATRAS)).strftime("%Y%m%d")
    data_fim = hoje.strftime("%Y%m%d")

    session = criar_sessao()
    resultados = []
    vistos = set()

    for municipio in MUNICIPIOS:
        for modalidade in [4, 5, 6, 7]:
            pagina = 1
            while True:
                payload = buscar_pagina(session, municipio, modalidade, pagina, data_ini, data_fim)
                
                if not payload or "resultado" not in payload:
                    break # Pula para a próxima combinação se a API falhar

                items = payload.get("resultado") or []
                if not items: break

                for item in items:
                    # Chame aqui a lógica de extração e avaliação
                    # registro = processar_item(item) ... 
                    pass

                if len(items) < TAMANHO_PAGINA: break
                pagina += 1
                
    return resultados

# (Funções salvar_csv, salvar_relatorio e main permanecem as mesmas)
