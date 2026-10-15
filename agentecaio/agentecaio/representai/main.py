import base64
import hashlib
import hmac
import json
import secrets
import threading
import time
from contextlib import asynccontextmanager
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
import config
from agent import foundry_agent
from data import admin_store

_LOGIN_ATTEMPTS: dict[str, list[float]] = {}
_LOGIN_LOCK = threading.Lock()
_SESSION_SECONDS = 8 * 60 * 60
_LOGIN_WINDOW_SECONDS = 60
_MAX_LOGIN_ATTEMPTS = 8


@asynccontextmanager
async def lifespan(_app: FastAPI):
    admin_store.init_db()
    admin_store.import_legacy_sheet_if_available()
    yield


app = FastAPI(title="CAIO", lifespan=lifespan)


class Pergunta(BaseModel):
    pergunta: str
    historico: list[dict] = Field(default_factory=list)


class LoginInput(BaseModel):
    token: str = Field(min_length=1, max_length=512)


class RegistroInput(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    category: str = Field(min_length=1, max_length=100)
    discipline: str = Field(default="", max_length=160)
    description: str = Field(default="", max_length=30000)
    publication_date: str = Field(default="", max_length=30)
    event_date: str = Field(default="", max_length=30)
    event_end_date: str = Field(default="", max_length=30)
    start_time: str = Field(default="", max_length=20)
    end_time: str = Field(default="", max_length=20)
    deadline: str = Field(default="", max_length=30)
    professor: str = Field(default="", max_length=160)
    location: str = Field(default="", max_length=240)
    modality: str = Field(default="", max_length=100)
    institution: str = Field(default="", max_length=200)
    workload: str = Field(default="", max_length=100)
    requirements: str = Field(default="", max_length=4000)
    reference_link: str = Field(default="", max_length=2000)
    notes: str = Field(default="", max_length=4000)
    grade: str = Field(default="", max_length=100)
    reason: str = Field(default="", max_length=1000)


class AcaoRegistro(BaseModel):
    reason: str = Field(default="", max_length=1000)
    confirm: bool = False
    expected_updated_at: str = ""


def _secret_administrativo() -> str:
    value = config.TOKEN_REPRESENTANTE
    if len(value) < config.TOKEN_REPRESENTANTE_MIN_LENGTH:
        raise HTTPException(
            503,
            "A autenticação administrativa precisa de um segredo aleatório com pelo menos 32 caracteres em REPRESENTANTE_TOKEN.",
        )
    return value


def _tentativas_restantes(ip: str) -> bool:
    now = time.monotonic()
    with _LOGIN_LOCK:
        attempts = [stamp for stamp in _LOGIN_ATTEMPTS.get(ip, []) if now - stamp < _LOGIN_WINDOW_SECONDS]
        _LOGIN_ATTEMPTS[ip] = attempts
        return len(attempts) < _MAX_LOGIN_ATTEMPTS


def _registrar_falha_login(ip: str) -> None:
    with _LOGIN_LOCK:
        _LOGIN_ATTEMPTS.setdefault(ip, []).append(time.monotonic())


def _limpar_falhas_login(ip: str) -> None:
    with _LOGIN_LOCK:
        _LOGIN_ATTEMPTS.pop(ip, None)


def _assinar_sessao(payload: dict, secret: str) -> str:
    encoded = base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":")).encode("utf-8")
    ).decode("ascii").rstrip("=")
    signature = hmac.new(secret.encode("utf-8"), encoded.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{encoded}.{signature}"


def _ler_sessao(value: str, secret: str) -> dict | None:
    try:
        encoded, signature = value.split(".", 1)
        expected = hmac.new(secret.encode("utf-8"), encoded.encode("ascii"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            return None
        padded = encoded + "=" * (-len(encoded) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded).decode("utf-8"))
        return payload if int(payload.get("exp", 0)) > time.time() else None
    except (ValueError, TypeError, json.JSONDecodeError):
        return None


def exigir_representante(
    request: Request,
    csrf_header: str = Header(default="", alias="X-CSRF-Token"),
) -> dict:
    secret = config.TOKEN_REPRESENTANTE
    if len(secret) < config.TOKEN_REPRESENTANTE_MIN_LENGTH:
        raise HTTPException(503, "A autenticação administrativa precisa de configuração segura.")
    session = _ler_sessao(request.cookies.get("caio_admin", ""), secret)
    if not session:
        raise HTTPException(401, "Sessão administrativa inválida ou expirada.")
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        cookie_csrf = request.cookies.get("caio_csrf", "")
        expected_csrf = str(session.get("csrf", ""))
        if not cookie_csrf or not csrf_header or not hmac.compare_digest(cookie_csrf, expected_csrf) or not hmac.compare_digest(csrf_header, expected_csrf):
            raise HTTPException(403, "Validação da requisição administrativa falhou.")
    return session


@app.post("/api/perguntar")
def perguntar(p: Pergunta):
    texto = p.pergunta.strip()[:500]
    if not texto:
        raise HTTPException(400, "Escreva sua dúvida.")
    try:
        res = foundry_agent.responder(texto, p.historico)
    except Exception as e:
        raise HTTPException(503, f"Agente indisponível: {type(e).__name__}. Verifique o .env (Foundry).")
    return {"resposta": res["resposta"], "respondida": res["respondida"]}

@app.get("/api/dashboard")
def dashboard(dias: int = 30, _admin: dict = Depends(exigir_representante)):
    stats = admin_store.dashboard_stats()
    return {
        "total": stats["total"],
        "sem_resposta": 0,
        "dias": dias,
        "categorias": [],
        "disciplinas": [],
        "frequentes": [],
        "pendentes": [],
        "dificuldade": [],
    }


@app.post("/api/admin/login")
def admin_login(payload: LoginInput, request: Request, response: Response):
    secret = _secret_administrativo()
    ip = request.client.host if request.client else "unknown"
    if not _tentativas_restantes(ip):
        raise HTTPException(429, "Muitas tentativas de acesso. Aguarde um minuto.")
    if not hmac.compare_digest(payload.token, secret):
        _registrar_falha_login(ip)
        raise HTTPException(401, "Credencial inválida.")

    _limpar_falhas_login(ip)
    csrf = secrets.token_urlsafe(32)
    cookie_value = _assinar_sessao({"exp": int(time.time()) + _SESSION_SECONDS, "csrf": csrf}, secret)
    forwarded_proto = request.headers.get("x-forwarded-proto", "").split(",", 1)[0].strip().lower()
    secure = request.url.scheme == "https" or forwarded_proto == "https"
    response.set_cookie("caio_admin", cookie_value, max_age=_SESSION_SECONDS, httponly=True,
                        secure=secure, samesite="strict", path="/")
    response.set_cookie("caio_csrf", csrf, max_age=_SESSION_SECONDS, httponly=False,
                        secure=secure, samesite="strict", path="/")
    return {"authenticated": True}


@app.get("/api/admin/config-status")
def admin_config_status():
    return config.representante_token_status()


@app.get("/api/admin/session")
def admin_session(session: dict = Depends(exigir_representante)):
    return {"authenticated": True, "expires_at": session["exp"]}


@app.post("/api/admin/logout")
def admin_logout(response: Response, _admin: dict = Depends(exigir_representante)):
    response.delete_cookie("caio_admin", path="/", httponly=True, samesite="strict")
    response.delete_cookie("caio_csrf", path="/", samesite="strict")
    return {"authenticated": False}


@app.get("/api/admin/dashboard")
def admin_dashboard(_admin: dict = Depends(exigir_representante)):
    return admin_store.dashboard_stats()


@app.get("/api/admin/categories")
def admin_categories(_admin: dict = Depends(exigir_representante)):
    return {"items": admin_store.categories()}


@app.get("/api/admin/records")
def admin_records(
    category: str = "", discipline: str = "", status: str = "", professor: str = "",
    publication_from: str = "", publication_to: str = "", event_from: str = "",
    event_to: str = "", q: str = "", sort: str = "updated_at", direction: str = "desc",
    limit: int = Query(default=25, ge=1, le=100), offset: int = Query(default=0, ge=0),
    _admin: dict = Depends(exigir_representante),
):
    return admin_store.list_records(
        {"category": category, "discipline": discipline, "status": status,
         "professor": professor, "publication_from": publication_from,
         "publication_to": publication_to, "event_from": event_from,
         "event_to": event_to, "q": q},
        limit=limit, offset=offset, sort=sort, direction=direction,
    )


@app.post("/api/admin/records", status_code=201)
def admin_create_record(payload: RegistroInput, _admin: dict = Depends(exigir_representante)):
    try:
        return {"item": admin_store.create_record(payload.model_dump(), actor="representante")}
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.get("/api/admin/records/{record_id}")
def admin_get_record(record_id: int, _admin: dict = Depends(exigir_representante)):
    item = admin_store.get_record(record_id)
    if not item:
        raise HTTPException(404, "Registro não encontrado.")
    return {"item": item}


@app.put("/api/admin/records/{record_id}")
def admin_update_record(record_id: int, payload: RegistroInput, _admin: dict = Depends(exigir_representante)):
    try:
        item = admin_store.update_record(record_id, payload.model_dump(), payload.reason, actor="representante")
        return {"item": item}
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@app.get("/api/admin/records/{record_id}/history")
def admin_record_history(record_id: int, _admin: dict = Depends(exigir_representante)):
    if not admin_store.get_record(record_id):
        raise HTTPException(404, "Registro não encontrado.")
    return {"items": admin_store.get_history(record_id)}


def _admin_transition(record_id: int, action: str, payload: AcaoRegistro):
    try:
        item = admin_store.transition_record(
            record_id, action, confirm=payload.confirm,
            expected_updated_at=payload.expected_updated_at,
            reason=payload.reason, actor="representante",
        )
        return {"item": item}
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@app.post("/api/admin/records/{record_id}/review")
def admin_review_record(record_id: int, payload: AcaoRegistro, _admin: dict = Depends(exigir_representante)):
    return _admin_transition(record_id, "revisar", payload)


@app.post("/api/admin/records/{record_id}/publish")
def admin_publish_record(record_id: int, payload: AcaoRegistro, _admin: dict = Depends(exigir_representante)):
    return _admin_transition(record_id, "oficial", payload)


@app.post("/api/admin/records/{record_id}/archive")
def admin_archive_record(record_id: int, payload: AcaoRegistro, _admin: dict = Depends(exigir_representante)):
    return _admin_transition(record_id, "arquivar", payload)


@app.post("/api/admin/records/{record_id}/withdraw")
def admin_withdraw_record(record_id: int, payload: AcaoRegistro, _admin: dict = Depends(exigir_representante)):
    return _admin_transition(record_id, "retirar", payload)

app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
def home():
    return FileResponse("static/index.html")

@app.get("/representante")
def painel():
    return FileResponse("static/representante.html")
