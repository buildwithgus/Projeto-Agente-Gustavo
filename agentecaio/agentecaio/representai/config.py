import os
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from dotenv import dotenv_values, load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent
DOTENV_PATH = PROJECT_ROOT / ".env"
_DOTENV_VALUES = dotenv_values(DOTENV_PATH)
load_dotenv(dotenv_path=DOTENV_PATH)


def _normalize_endpoint(value: str) -> str:
    v = (value or "").strip().rstrip("/")
    for suffix in ("/openai/v1", "/openai"):
        if v.lower().endswith(suffix):
            return v[: -len(suffix)]
    return v


try:
    ZoneInfo("America/Sao_Paulo")
    FUSO = "America/Sao_Paulo"
except ZoneInfoNotFoundError:
    FUSO = "UTC"

# --- Microsoft Foundry / Azure AI Projects
FOUNDRY_AGENT_NAME = os.getenv("FOUNDRY_AGENT_NAME", "")
FOUNDRY_AGENT_ID = os.getenv("FOUNDRY_AGENT_ID", "")
FOUNDRY_ENDPOINT = _normalize_endpoint(os.getenv("FOUNDRY_ENDPOINT", ""))
FOUNDRY_PROJECT_ENDPOINT = _normalize_endpoint(os.getenv("FOUNDRY_PROJECT_ENDPOINT", ""))
FOUNDRY_DEPLOYMENT = os.getenv("FOUNDRY_DEPLOYMENT", "")
FOUNDRY_API_KEY = os.getenv("FOUNDRY_API_KEY", "")
FOUNDRY_API_VERSION = os.getenv("FOUNDRY_API_VERSION", "2024-10-21")


def validate_foundry_config():
    required = {
        "FOUNDRY_PROJECT_ENDPOINT": FOUNDRY_PROJECT_ENDPOINT,
        "FOUNDRY_AGENT_NAME": FOUNDRY_AGENT_NAME,
    }
    missing = [name for name, value in required.items() if not str(value).strip()]
    return missing


TURMA = {
    "instituicao": "Universidade Metodista de São Paulo",
    "curso": "Análise e Desenvolvimento de Sistemas",
    "turma": "1",
    "semestre": "4º semestre",
}
PLANILHA_NOME = os.getenv("PLANILHA_NOME", "RepresentAIPlanilha")
CREDENCIAIS = os.getenv("GOOGLE_CREDENTIALS_FILE", "credenciais.json")
TOKEN_REPRESENTANTE_MIN_LENGTH = 32
_ENV_REPRESENTANTE_TOKEN = os.getenv("REPRESENTANTE_TOKEN")
_DOTENV_REPRESENTANTE_TOKEN = _DOTENV_VALUES.get("REPRESENTANTE_TOKEN")


def _resolve_representante_token(environment_value: str | None, dotenv_value: str | None) -> str:
    if environment_value and environment_value.strip():
        return environment_value
    return dotenv_value or ""


TOKEN_REPRESENTANTE = _resolve_representante_token(
    _ENV_REPRESENTANTE_TOKEN, _DOTENV_REPRESENTANTE_TOKEN
)


def representante_token_status() -> dict[str, bool | int]:
    value = TOKEN_REPRESENTANTE
    found = bool(value.strip())
    return {
        "found": found,
        "length": len(value),
        "valid": found and len(value) >= TOKEN_REPRESENTANTE_MIN_LENGTH,
    }


CACHE_SEGUNDOS = 60

ABAS = {
    "base": "Base",
    "duvidas": "Duvidas_Sem_Resposta",
    "log": "Log_Consultas",
}
COLUNAS_BASE = [
    "ID", "ID_Item", "Versão", "Categoria", "Disciplina", "Professor", "Tipo",
    "Nome", "Descrição", "Data", "Data_Fim", "Dia_Semana", "Horário", "Local",
    "Modalidade", "Nota", "Status", "Oficial", "Data_Atualização",
    "Observações", "Conteúdo_Texto",
]
COLUNAS_DUVIDAS = ["Data_Hora", "Pergunta", "Categoria", "Disciplina", "Motivo", "Status", "Resposta_Representante"]
COLUNAS_LOG = ["Data_Hora", "Pergunta", "Categoria", "Disciplina", "Respondida", "Ferramentas"]
