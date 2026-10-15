"""Agente CAIO integrado ao agente existente no Microsoft Foundry usando a API de Responses."""
from __future__ import annotations

import logging
import json
import re
import socket
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from azure.core.exceptions import ClientAuthenticationError, ServiceRequestError, ServiceResponseError
from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential
from openai import APIConnectionError, APITimeoutError, AuthenticationError, PermissionDeniedError

import config
from data import admin_store

INSTRUCOES = (Path(__file__).parent / "instructions.md").read_text(encoding="utf-8")
_PROJECT_CLIENT = None
_OPENAI_CLIENT = None
_LOGGER = logging.getLogger(__name__)
FORMATO_RESPOSTA = (
    "Responda sempre em português brasileiro. Para várias provas, avisos, eventos ou etapas, "
    "prefira Markdown estruturado: título curto, linha em branco e cada item em bloco separado. "
    "Agrupe dados relacionados com marcadores; destaque nomes, datas, horários, prazos e valores "
    "com **negrito**, mantendo-os exatamente como constam na fonte. Para provas e trabalhos, "
    "organize cada disciplina ou atividade em um bloco e inclua apenas os campos disponíveis. "
    "Para extensão universitária, separe cada projeto e inclua instituição, descrição, carga horária, "
    "período, prazo, requisitos e link somente quando disponíveis. Para resumos, use subtítulos e "
    "tópicos apenas quando ajudarem a compreensão; preserve conceitos e detalhes relevantes. "
    "Para aulas, agrupe por disciplina e organize várias aulas em ordem cronológica, incluindo data, "
    "horário, professor, conteúdo e modalidade somente se constarem na fonte. Use listas numeradas "
    "para sequências e responda perguntas simples em uma frase curta, sem lista desnecessária. "
    "Não invente, não omita informações relevantes e não reproduza marcadores técnicos de citação."
)
_MARCADORES_CITACAO = re.compile(
    r"\uE200(?:filecite|cite)\uE200turn\d+(?:file|search|news|video)\d+"
    r"(?:\uE200turn\d+(?:file|search|news|video)\d+)*\uE201"
)


def _limpar_marcadores_citacao(texto: str) -> str:
    return _MARCADORES_CITACAO.sub("", texto)


def formata_resposta_sem_dado():
    return (
        "Não encontrei essa informação na base de conhecimento disponível no momento. "
        "Posso tentar reescrever a pergunta ou, se preferir, você pode pedir ao representante para validar a dúvida."
    )


def _classificar_erro_foundry(exc: Exception) -> str:
    status = getattr(exc, "status_code", None)
    body = getattr(exc, "body", None)
    details = f"{exc} {body or ''}".lower()
    request = getattr(exc, "request", None)
    request_path = str(getattr(request, "url", "")).lower()

    if isinstance(exc, (APIConnectionError, APITimeoutError, ServiceRequestError, ServiceResponseError, socket.gaierror, ConnectionError, TimeoutError)):
        return "Falha de rede/DNS ao conectar ao Microsoft Foundry. Verifique a conexão e a resolução DNS."
    if isinstance(exc, (AuthenticationError, ClientAuthenticationError)) or status == 401:
        return "Falha de autenticação no Azure. Confirme a sessão do Azure CLI e a identidade usada pelo processo Python."
    if isinstance(exc, PermissionDeniedError) or status == 403:
        return "A identidade autenticada não tem autorização para acessar o projeto ou o agente do Foundry."
    if status == 404:
        if "agent" in details or "assistant" in details or "/agents/" in request_path:
            return "O agente não foi encontrado no projeto. Confirme FOUNDRY_AGENT_NAME e o projeto do Foundry."
        if "/deployments/" in request_path or "/chat/completions" in request_path:
            return "A rota ou deployment de Chat Completions não foi encontrado. Para o agente configurado, use Responses sem inventar um deployment."
        if "project" in details or ("/api/projects/" in request_path and "/openai/" not in request_path):
            return "O projeto/endpoint do Foundry não foi encontrado. Confirme FOUNDRY_PROJECT_ENDPOINT."
        return "O Foundry retornou HTTP 404 para o recurso solicitado; confira endpoint do projeto, agente e operação usada."
    return f"Falha não categorizada no Microsoft Foundry ({type(exc).__name__}). Consulte o erro no terminal."


def _resposta_erro_foundry(exc: Exception):
    message = str(exc)
    message = re.sub(r"(?i)Bearer\s+\S+", "Bearer [REDACTED]", message)
    message = re.sub(
        r"(?i)(authorization|access[_ -]?token|refresh[_ -]?token|client[_ -]?secret|api[_ -]?key|password)\s*[:=]\s*[^\s,;]+",
        r"\1=[REDACTED]",
        message,
    )
    _LOGGER.error("Exceção Foundry %s: %s", type(exc).__name__, message)
    return {
        "resposta": _classificar_erro_foundry(exc),
        "respondida": False,
        "categoria": "Geral",
        "disciplina": "",
        "ferramentas": [],
    }


def _validar_configuracao():
    missing = config.validate_foundry_config()
    if missing:
        raise RuntimeError(
            "Configuração do Foundry incompleta. Faltam variáveis: " + ", ".join(missing)
        )


def _get_project_client() -> AIProjectClient:
    global _PROJECT_CLIENT
    if _PROJECT_CLIENT is None:
        _validar_configuracao()
        _PROJECT_CLIENT = AIProjectClient(
            endpoint=config.FOUNDRY_PROJECT_ENDPOINT,
            credential=DefaultAzureCredential(),
            allow_preview=True,
        )
    return _PROJECT_CLIENT


def _get_agent_client():
    return _get_project_client().agents


def _get_cliente():
    return _get_openai_client()


def _get_openai_client():
    global _OPENAI_CLIENT
    if _OPENAI_CLIENT is None:
        project_client = _get_project_client()
        _OPENAI_CLIENT = project_client.get_openai_client(agent_name=config.FOUNDRY_AGENT_NAME)
    return _OPENAI_CLIENT


def _sistema():
    agora = datetime.now(ZoneInfo(config.FUSO))
    dias = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]
    return (
        f"{INSTRUCOES}\n\nHoje é {dias[agora.weekday()]}, {agora:%d/%m/%Y}.\n"
        "Para informações acadêmicas cadastradas pelo representante, consulte primeiro os registros oficiais "
        "vigentes fornecidos no contexto da pergunta. Esses registros atuais prevalecem sobre o PDF, File Search "
        "e histórico da conversa. Não apresente conteúdo de arquivo ou histórico como oficial quando não houver "
        "registro atual correspondente."
    )


def _normalizar_input(historico: list[dict] | None) -> list[dict[str, str]]:
    itens: list[dict[str, str]] = []
    for msg in (historico or [])[-8:]:
        role = str(msg.get("role", "")).strip()
        content = msg.get("content")
        if role not in {"user", "assistant"} or not content:
            continue
        itens.append({"role": role, "content": str(content)[:1500]})
    return itens


def _contexto_administrativo(pergunta: str) -> str:
    try:
        registros = admin_store.public_context(pergunta)
    except Exception as exc:
        _LOGGER.warning("Consulta dos registros administrativos indisponível (%s).", type(exc).__name__)
        registros = []
    if registros:
        return (
            "FONTE ADMINISTRATIVA ATUAL E AUTORITATIVA: os registros abaixo foram lidos diretamente do "
            "banco persistente nesta solicitação e são a versão oficial vigente. Para os assuntos cobertos "
            "por eles, use exclusivamente estes valores, ignore conflitos no PDF, File Search e histórico "
            "da conversa e não recupere datas ou textos antigos. Os registros podem omitir campos vazios:\n"
            + json.dumps(registros, ensure_ascii=False, indent=2)
            + "\nUse somente os campos preenchidos; não complete campos ausentes. Se a pergunta pedir um "
            "valor que não aparece aqui, diga que não há confirmação oficial desse valor."
        )
    return (
        "O banco persistente não retornou registro oficial vigente correspondente a esta pergunta. Não afirme "
        "que um dado do PDF/File Search ou do histórico é oficial ou atual, e não responda datas, horários, "
        "prazos, status ou outras informações administrativas com base em versões antigas. O File Search "
        "continua disponível para conteúdo geral de referência, identificado como não confirmado pelo "
        "representante; para informação administrativa atual, diga que não encontrou confirmação oficial."
    )


def _pergunta_com_contexto(pergunta: str) -> str:
    return (
        f"Pergunta do aluno:\n{pergunta}\n\n{_contexto_administrativo(pergunta)}"
        f"\n\nEsta instrução de prioridade se aplica mesmo se o documento, File Search ou mensagens anteriores "
        f"discordarem. Diretrizes de apresentação: {FORMATO_RESPOSTA}"
    )


def _extrair_texto_resposta(resposta: Any) -> str:
    if isinstance(resposta, str):
        return _limpar_marcadores_citacao(resposta.strip())

    content = getattr(resposta, "content", None)
    if isinstance(content, str):
        return _limpar_marcadores_citacao(content.strip())
    if isinstance(content, dict):
        value = content.get("text")
        if isinstance(value, dict):
            texto = value.get("value")
            if texto:
                return _limpar_marcadores_citacao(str(texto).strip())
        value = content.get("value")
        if value:
            return _limpar_marcadores_citacao(str(value).strip())

    texto = getattr(resposta, "output_text", None)
    if texto:
        return _limpar_marcadores_citacao(str(texto).strip())

    if content is not None:
        partes: list[str] = []
        for item in content if isinstance(content, list) else [content]:
            if isinstance(item, dict):
                value = item.get("text")
                if isinstance(value, dict):
                    txt = value.get("value")
                    if txt:
                        partes.append(str(txt))
                        continue
                value = item.get("value")
                if value:
                    partes.append(str(value))
            elif hasattr(item, "text"):
                txt = getattr(item, "text", None)
                if isinstance(txt, dict):
                    value = txt.get("value")
                    if value:
                        partes.append(str(value))
        if partes:
            return _limpar_marcadores_citacao("\n".join(partes).strip())

    saida = getattr(resposta, "output", []) or []
    partes: list[str] = []
    for item in saida:
        item_type = getattr(item, "type", None)
        if item_type == "message":
            for bloco in getattr(item, "content", []) or []:
                if isinstance(bloco, dict):
                    value = bloco.get("text")
                    if isinstance(value, str):
                        partes.append(value)
                    elif isinstance(value, dict):
                        partes.append(str(value.get("value", "")))
                elif hasattr(bloco, "text"):
                    texto_bloco = getattr(bloco, "text", None)
                    if isinstance(texto_bloco, str):
                        partes.append(texto_bloco)
                    elif isinstance(texto_bloco, dict):
                        partes.append(str(texto_bloco.get("value", "")))
    return _limpar_marcadores_citacao("\n".join(partes).strip())


def responder(pergunta: str, historico: list[dict] | None = None):
    pergunta = (pergunta or "").strip()
    if not pergunta:
        return {"resposta": "Escreva uma dúvida para enviar ao agente do Foundry.", "respondida": False, "categoria": "Geral", "disciplina": "", "ferramentas": []}

    if config.FOUNDRY_PROJECT_ENDPOINT and config.FOUNDRY_AGENT_ID:
        try:
            client = _get_agent_client()
            thread = client.create_thread()
            for msg in (historico or [])[-8:]:
                if msg.get("role") == "user" and msg.get("content"):
                    client.create_message(thread_id=thread.id, role="user", content=str(msg["content"])[:1500])
            client.create_message(thread_id=thread.id, role="user", content=_pergunta_com_contexto(pergunta))
            run = client.create_run(thread_id=thread.id, assistant_id=config.FOUNDRY_AGENT_ID)
            while getattr(run, "status", None) in {"queued", "in_progress", "requires_action"}:
                import time
                time.sleep(1)
                run = client.get_run(thread_id=thread.id, run_id=run.id)
            messages = client.list_messages(thread_id=thread.id)
            for item in reversed((getattr(messages, "data", None) or [])):
                if getattr(item, "role", None) == "assistant":
                    texto = _extrair_texto_resposta(item)
                    if texto:
                        return {
                            "resposta": texto,
                            "categoria": "Geral",
                            "disciplina": "",
                            "respondida": True,
                            "ferramentas": [],
                        }
            return {
                "resposta": formata_resposta_sem_dado(),
                "categoria": "Geral",
                "disciplina": "",
                "respondida": False,
                "ferramentas": [],
            }
        except Exception as exc:  # pragma: no cover - depende do ambiente Azure real
            return _resposta_erro_foundry(exc)

    try:
        client = _get_cliente()
        conversation = client.conversations.create()
        entrada = _normalizar_input(historico)
        entrada.append({
            "role": "user",
            "content": _pergunta_com_contexto(pergunta),
        })
        resposta = client.responses.create(
            conversation=conversation.id,
            input=entrada,
        )
        texto = _extrair_texto_resposta(resposta)
        if not texto:
            texto = formata_resposta_sem_dado()
    except Exception as exc:  # pragma: no cover - depende de ambiente Azure real
        return _resposta_erro_foundry(exc)

    return {
        "resposta": texto,
        "categoria": "Geral",
        "disciplina": "",
        "respondida": bool(texto and texto.strip()),
        "ferramentas": [],
    }
