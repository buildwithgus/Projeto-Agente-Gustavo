"""Acesso ao Google Sheets. O código só ESCREVE em Duvidas_Sem_Resposta e Log_Consultas;
a aba Base é somente leitura (quem edita é o representante)."""
import os
import time
import gspread
from google.oauth2.service_account import Credentials
import config

_ESCOPOS = ["https://www.googleapis.com/auth/spreadsheets"]
_planilha = None
_cache = {}


def _arquivo_credenciais_existe():
    return bool(config.CREDENCIAIS) and os.path.exists(config.CREDENCIAIS)


def _abrir():
    global _planilha
    if _planilha is None:
        if not _arquivo_credenciais_existe():
            raise FileNotFoundError(
                "Arquivo de credenciais do Google não encontrado. "
                f"Verifique a variável GOOGLE_CREDENTIALS_FILE ({config.CREDENCIAIS})."
            )
        cred = Credentials.from_service_account_file(config.CREDENCIAIS, scopes=_ESCOPOS)
        _planilha = gspread.authorize(cred).open(config.PLANILHA_NOME)
    return _planilha


def ler_aba(chave):
    """Lê a aba como lista de dicts, com cache curto para não estourar a cota."""
    agora = time.time()
    if chave in _cache and agora - _cache[chave][0] < config.CACHE_SEGUNDOS:
        return _cache[chave][1]
    try:
        linhas = _abrir().worksheet(config.ABAS[chave]).get_all_records()
    except FileNotFoundError:
        return []
    _cache[chave] = (agora, linhas)
    return linhas


def adicionar_linha(chave, valores):
    try:
        _abrir().worksheet(config.ABAS[chave]).append_row(valores, value_input_option="USER_ENTERED")
    except FileNotFoundError:
        return False
    _cache.pop(chave, None)
    return True
