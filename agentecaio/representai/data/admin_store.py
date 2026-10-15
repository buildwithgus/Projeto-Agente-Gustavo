"""Persistencia SQLite e regras de publicacao do painel administrativo do CAIO."""
from __future__ import annotations

import json
import logging
import re
import sqlite3
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import config

_LOGGER = logging.getLogger(__name__)
DB_PATH = Path(__file__).resolve().parent / "caio_admin.sqlite3"
STATUSES = {"rascunho", "em_revisao", "oficial", "arquivada", "retirada"}
CATEGORIAS_INICIAIS = [
    "Avisos", "Calendário", "Esta semana", "Provas", "Trabalhos", "Aulas",
    "Extensão Universitária", "Resumo",
]
CAMPOS = (
    "title", "category", "discipline", "description", "publication_date",
    "event_date", "event_end_date", "start_time", "end_time", "deadline",
    "professor", "location", "modality", "institution", "workload",
    "requirements", "reference_link", "notes", "grade",
)
_HISTORICO_RE = re.compile(r"\b(historic|historico|anterior|antiga|antigo|arquiv|versao|antes)\b")
_STOPWORDS = {
    "para", "com", "uma", "por", "que", "qual", "quais", "como", "sobre", "tem",
    "tenho", "quero", "mostre", "liste", "informe", "esta", "esse", "essa", "das",
    "dos", "nas", "nos", "aula", "aulas", "informacao", "informacoes", "dados",
}


def agora_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH, timeout=20)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    return connection


def init_db() -> None:
    with _connect() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_id TEXT NOT NULL,
                version INTEGER NOT NULL,
                status TEXT NOT NULL,
                current_official INTEGER NOT NULL DEFAULT 0,
                source TEXT NOT NULL,
                title TEXT NOT NULL,
                category TEXT NOT NULL,
                discipline TEXT NOT NULL DEFAULT '',
                professor TEXT NOT NULL DEFAULT '',
                publication_date TEXT NOT NULL DEFAULT '',
                event_date TEXT NOT NULL DEFAULT '',
                deadline TEXT NOT NULL DEFAULT '',
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                created_by TEXT NOT NULL,
                legacy_ref TEXT UNIQUE,
                UNIQUE(group_id, version)
            );
            CREATE INDEX IF NOT EXISTS idx_records_public
                ON records(status, current_official, category, event_date);
            CREATE INDEX IF NOT EXISTS idx_records_group
                ON records(group_id, version DESC);
            CREATE TABLE IF NOT EXISTS audit_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                record_id INTEGER NOT NULL REFERENCES records(id),
                group_id TEXT NOT NULL,
                action TEXT NOT NULL,
                old_status TEXT NOT NULL DEFAULT '',
                new_status TEXT NOT NULL DEFAULT '',
                before_json TEXT,
                after_json TEXT NOT NULL,
                reason TEXT NOT NULL DEFAULT '',
                changed_at TEXT NOT NULL,
                actor TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_history_group
                ON audit_history(group_id, changed_at DESC, id DESC);
            CREATE TABLE IF NOT EXISTS app_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            """
        )
        _reconcile_official_records(connection)


def _clean_payload(data: dict) -> dict[str, str]:
    return {field: str(data.get(field) or "").strip() for field in CAMPOS}


def _payload_json(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _record(row: sqlite3.Row | None) -> dict | None:
    if row is None:
        return None
    result = dict(row)
    payload = json.loads(result.pop("payload_json"))
    result.update(payload)
    result["current_official"] = bool(result["current_official"])
    result["has_official_ancestor"] = bool(result.get("has_official_ancestor", False))
    return result


def _audit(connection: sqlite3.Connection, record_id: int, group_id: str, action: str,
           before: dict | None, after: dict, old_status: str, new_status: str,
           reason: str = "", actor: str = "representante") -> None:
    connection.execute(
        """INSERT INTO audit_history
           (record_id, group_id, action, old_status, new_status, before_json,
            after_json, reason, changed_at, actor)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (record_id, group_id, action, old_status, new_status,
         _payload_json(before) if before is not None else None, _payload_json(after),
         reason.strip(), agora_iso(), actor),
    )


def _reconcile_official_records(
    connection: sqlite3.Connection, group_ids: set[str] | None = None
) -> None:
    if group_ids is None:
        groups = connection.execute(
            "SELECT DISTINCT group_id FROM records WHERE status = 'oficial'"
        ).fetchall()
        group_ids = {row["group_id"] for row in groups}

    for group_id in group_ids:
        officials = connection.execute(
            """SELECT * FROM records WHERE group_id = ? AND status = 'oficial'
               ORDER BY version DESC, updated_at DESC, id DESC""",
            (group_id,),
        ).fetchall()
        if not officials:
            continue

        current_id = officials[0]["id"]
        for previous_row in officials[1:]:
            previous = _record(previous_row)
            connection.execute(
                """UPDATE records SET status = 'arquivada', current_official = 0,
                   updated_at = ? WHERE id = ?""",
                (agora_iso(), previous["id"]),
            )
            archived = _fetch_record(connection, previous["id"])
            _audit(
                connection, previous["id"], group_id, "arquivada_por_reconciliacao",
                previous, archived, "oficial", "arquivada",
                "Reconciliação de versões oficiais duplicadas.", "sistema",
            )
        connection.execute(
            """UPDATE records SET current_official = CASE WHEN id = ? THEN 1 ELSE 0 END
               WHERE group_id = ? AND status = 'oficial'""",
            (current_id, group_id),
        )


def _fetch_record(connection: sqlite3.Connection, record_id: int) -> dict | None:
    return _record(connection.execute(
        """SELECT records.*,
                  EXISTS(SELECT 1 FROM records previous
                         WHERE previous.group_id = records.group_id
                           AND previous.id <> records.id
                           AND previous.status IN ('oficial', 'arquivada')) AS has_official_ancestor
           FROM records WHERE id = ?""",
        (record_id,),
    ).fetchone())


def _insert(connection: sqlite3.Connection, *, group_id: str, version: int, status: str,
            payload: dict[str, str], source: str, actor: str, current_official: bool = False,
            legacy_ref: str | None = None, action: str = "criado",
            before: dict | None = None, reason: str = "") -> dict:
    timestamp = agora_iso()
    cursor = connection.execute(
        """INSERT INTO records
           (group_id, version, status, current_official, source, title, category,
            discipline, professor, publication_date, event_date, deadline, payload_json,
            created_at, updated_at, created_by, legacy_ref)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (group_id, version, status, int(current_official), source, payload["title"],
         payload["category"], payload["discipline"], payload["professor"],
         payload["publication_date"], payload["event_date"], payload["deadline"],
         _payload_json(payload), timestamp, timestamp, actor, legacy_ref),
    )
    record_id = cursor.lastrowid
    _audit(connection, record_id, group_id, action, before, payload,
           before.get("status", "") if before else "", status, reason, actor)
    return _fetch_record(connection, record_id)


def create_record(data: dict, actor: str = "representante") -> dict:
    payload = _clean_payload(data)
    if not payload["title"] or not payload["category"]:
        raise ValueError("Título e categoria são obrigatórios.")
    with _connect() as connection:
        return _insert(connection, group_id=uuid4().hex, version=1, status="rascunho",
                       payload=payload, source="painel", actor=actor, action="rascunho_criado")


def update_record(record_id: int, data: dict, reason: str = "",
                  actor: str = "representante") -> dict:
    payload = _clean_payload(data)
    if not payload["title"] or not payload["category"]:
        raise ValueError("Título e categoria são obrigatórios.")
    with _connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        old = _fetch_record(connection, record_id)
        if old is None:
            raise LookupError("Registro não encontrado.")
        if old["status"] == "retirada":
            raise ValueError("Informações retiradas não podem ser editadas; crie um novo registro.")
        latest = connection.execute(
            "SELECT MAX(version) FROM records WHERE group_id = ?", (old["group_id"],)
        ).fetchone()[0]
        if old["version"] != latest:
            raise ValueError("Esta versão é antiga. Abra a versão mais recente antes de editar.")
        return _insert(connection, group_id=old["group_id"], version=old["version"] + 1,
                       status="rascunho", payload=payload, source="painel", actor=actor,
                       action="versao_corrigida", before={**old, "status": old["status"]},
                       reason=reason)


def transition_record(record_id: int, action: str, *, confirm: bool = False,
                      expected_updated_at: str = "", reason: str = "",
                      actor: str = "representante") -> dict:
    if action not in {"revisar", "oficial", "arquivar", "retirar"}:
        raise ValueError("Ação inválida.")
    with _connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        old = _fetch_record(connection, record_id)
        if old is None:
            raise LookupError("Registro não encontrado.")
        if action == "revisar":
            expected = "rascunho"
            new_status = "em_revisao"
        elif action == "oficial":
            if old["status"] == "rascunho":
                has_official_ancestor = connection.execute(
                    """SELECT 1 FROM records
                       WHERE group_id = ? AND id <> ? AND status IN ('oficial', 'arquivada') LIMIT 1""",
                    (old["group_id"], record_id),
                ).fetchone()
                if not has_official_ancestor:
                    raise ValueError("Envie o rascunho para revisão antes de publicá-lo.")
                expected = "rascunho"
            else:
                expected = "em_revisao"
            new_status = "oficial"
            if not confirm:
                raise ValueError("Confirme a prévia antes de publicar.")
            if expected_updated_at != old["updated_at"]:
                raise ValueError("O registro mudou desde a prévia. Atualize e revise novamente.")
        elif action == "arquivar":
            expected = "oficial"
            new_status = "arquivada"
        else:
            expected = old["status"]
            new_status = "retirada"
            if expected in {"arquivada", "retirada"}:
                raise ValueError("Este registro já está fora de circulação.")

        if old["status"] != expected:
            raise ValueError(f"Ação indisponível para o status {old['status']}.")
        if action in {"revisar", "oficial"}:
            latest = connection.execute(
                "SELECT MAX(version) FROM records WHERE group_id = ?", (old["group_id"],)
            ).fetchone()[0]
            if old["version"] != latest:
                raise ValueError("Esta versão foi substituída por uma correção mais recente.")
        if action == "oficial" and (not old["title"].strip() or not old["category"].strip()):
            raise ValueError("Título e categoria são obrigatórios para publicação.")

        current_official = int(old["current_official"])
        if new_status in {"arquivada", "retirada"}:
            current_official = 0
        if action == "oficial":
            previous_officials = connection.execute(
                "SELECT * FROM records WHERE group_id = ? AND current_official = 1",
                (old["group_id"],),
            ).fetchall()
            connection.execute(
                """UPDATE records SET status = 'arquivada', current_official = 0,
                   updated_at = ? WHERE group_id = ? AND current_official = 1""",
                (agora_iso(), old["group_id"]),
            )
            for previous_row in previous_officials:
                previous = _record(previous_row)
                archived = _fetch_record(connection, previous["id"])
                _audit(connection, previous["id"], old["group_id"], "arquivada_por_nova_versao",
                       previous, archived, "oficial", "arquivada", reason, actor)
            current_official = 1

        timestamp = agora_iso()
        connection.execute(
            "UPDATE records SET status = ?, current_official = ?, updated_at = ? WHERE id = ?",
            (new_status, current_official, timestamp, record_id),
        )
        after = _fetch_record(connection, record_id)
        _audit(connection, record_id, old["group_id"], action, old, after,
               old["status"], new_status, reason, actor)
        return after


def get_record(record_id: int) -> dict | None:
    with _connect() as connection:
        return _fetch_record(connection, record_id)


def get_history(record_id: int) -> list[dict]:
    with _connect() as connection:
        row = connection.execute("SELECT group_id FROM records WHERE id = ?", (record_id,)).fetchone()
        if row is None:
            return []
        entries = connection.execute(
            "SELECT * FROM audit_history WHERE group_id = ? ORDER BY changed_at DESC, id DESC",
            (row["group_id"],),
        ).fetchall()
    return [{**dict(entry), "before": json.loads(entry["before_json"]) if entry["before_json"] else None,
             "after": json.loads(entry["after_json"])} for entry in entries]


def _filter_clause(filters: dict) -> tuple[str, list]:
    where = ["1 = 1"]
    values: list = []
    exact = {"category": "category", "discipline": "discipline", "status": "status", "professor": "professor"}
    for key, column in exact.items():
        if filters.get(key):
            where.append(f"lower({column}) = lower(?)")
            values.append(filters[key])
    for key, column in (("publication_from", "publication_date"),):
        if filters.get(key):
            where.append(f"{column} <> '' AND {column} >= ?")
            values.append(filters[key])
    for key, column in (("publication_to", "publication_date"),):
        if filters.get(key):
            where.append(f"{column} <> '' AND {column} <= ?")
            values.append(filters[key])
    event_from, event_to = filters.get("event_from"), filters.get("event_to")
    if event_from and event_to:
        where.append("((event_date BETWEEN ? AND ?) OR (deadline BETWEEN ? AND ?))")
        values.extend([event_from, event_to, event_from, event_to])
    elif event_from:
        where.append("((event_date <> '' AND event_date >= ?) OR (deadline <> '' AND deadline >= ?))")
        values.extend([event_from, event_from])
    elif event_to:
        where.append("((event_date <> '' AND event_date <= ?) OR (deadline <> '' AND deadline <= ?))")
        values.extend([event_to, event_to])
    if filters.get("q"):
        like = f"%{filters['q']}%"
        where.append("(title LIKE ? OR category LIKE ? OR discipline LIKE ? OR professor LIKE ? OR payload_json LIKE ?)")
        values.extend([like] * 5)
    return " AND ".join(where), values


def list_records(filters: dict | None = None, *, limit: int = 25, offset: int = 0,
                 sort: str = "updated_at", direction: str = "desc") -> dict:
    filters = filters or {}
    clause, values = _filter_clause(filters)
    allowed_sort = {"updated_at", "created_at", "event_date", "deadline", "title", "category", "status", "publication_date"}
    sort = sort if sort in allowed_sort else "updated_at"
    direction = "ASC" if direction.lower() == "asc" else "DESC"
    with _connect() as connection:
        total = connection.execute(f"SELECT COUNT(*) FROM records WHERE {clause}", values).fetchone()[0]
        rows = connection.execute(
            f"""SELECT records.*,
                       EXISTS(SELECT 1 FROM records previous
                              WHERE previous.group_id = records.group_id
                                AND previous.id <> records.id
                                AND previous.status IN ('oficial', 'arquivada')) AS has_official_ancestor
                FROM records WHERE {clause}
                ORDER BY {sort} {direction}, id DESC LIMIT ? OFFSET ?""",
            [*values, max(1, min(int(limit), 100)), max(0, int(offset))],
        ).fetchall()
    return {"items": [_record(row) for row in rows], "total": total,
            "limit": max(1, min(int(limit), 100)), "offset": max(0, int(offset))}


def dashboard_stats() -> dict:
    with _connect() as connection:
        counts = {row["status"]: row["total"] for row in connection.execute(
            "SELECT status, COUNT(*) AS total FROM records GROUP BY status"
        ).fetchall()}
        total = connection.execute("SELECT COUNT(*) FROM records").fetchone()[0]
        imported = connection.execute(
            "SELECT value FROM app_meta WHERE key = 'sheets_base_import'"
        ).fetchone()
    return {
        "total": total,
        **{status: counts.get(status, 0) for status in sorted(STATUSES)},
        "legacy_imported": bool(imported),
        "legacy_import_ready": Path(config.CREDENCIAIS).is_file(),
    }


def categories() -> list[str]:
    with _connect() as connection:
        stored = [row[0] for row in connection.execute(
            "SELECT DISTINCT category FROM records WHERE category <> '' ORDER BY category COLLATE NOCASE"
        ).fetchall()]
    return list(dict.fromkeys([*CATEGORIAS_INICIAIS, *stored]))


def _norm(value: str) -> str:
    decomposed = unicodedata.normalize("NFD", value or "")
    return "".join(char for char in decomposed if unicodedata.category(char) != "Mn").lower()


def _tokens(value: str) -> list[str]:
    return [word for word in re.findall(r"[a-z0-9]+", _norm(value)) if len(word) > 2 and word not in _STOPWORDS]


def _related_score(question_terms: list[str], text: str) -> int:
    terms = set(_tokens(text))
    score = 0
    for word in question_terms:
        if word in terms:
            score += 1
        elif any(len(word) >= 4 and len(term) >= 4 and (word.startswith(term) or term.startswith(word)) for term in terms):
            score += 1
    return score


def public_context(question: str, limit: int = 12) -> list[dict]:
    normalized_question = _norm(question)
    include_archived = bool(_HISTORICO_RE.search(normalized_question))
    terms = _tokens(question)
    if not terms:
        return []
    try:
        with _connect() as connection:
            rows = connection.execute(
                "SELECT * FROM records WHERE (status = 'oficial' AND current_official = 1)"
                + (" OR status = 'arquivada'" if include_archived else "")
            ).fetchall()
    except sqlite3.OperationalError as exc:
        if "no such table" in str(exc).lower():
            return []
        raise
    ranked = []
    for row in rows:
        record = _record(row)
        title_text = " ".join(str(record.get(key, "")) for key in ("title", "category", "discipline"))
        detail_text = " ".join(str(record.get(key, "")) for key in CAMPOS if key not in {"title", "category", "discipline"})
        score = _related_score(terms, title_text) * 4 + _related_score(terms, detail_text)
        if score:
            ranked.append((score, record))
    ranked.sort(key=lambda item: (item[0], item[1]["updated_at"]), reverse=True)
    selected = []
    for _, record in ranked[:limit]:
        selected.append({
            "titulo": record["title"], "categoria": record["category"],
            "disciplina": record["discipline"], "professor": record["professor"],
            "publicado_em": record["publication_date"], "data": record["event_date"],
            "data_final": record["event_end_date"],
            "prazo": record["deadline"], "horario": " às ".join(filter(None, [record["start_time"], record["end_time"]])),
            "hora_inicio": record["start_time"], "hora_fim": record["end_time"],
            "local": record["location"], "modalidade": record["modality"],
            "instituicao": record["institution"], "carga_horaria": record["workload"],
            "requisitos": record["requirements"], "conteudo": record["description"],
            "material": record["reference_link"], "observacoes": record["notes"],
            "nota": record["grade"],
            "origem": record["source"], "versao": record["version"],
            "status": "histórica/arquivada" if record["status"] == "arquivada" else "oficial vigente",
        })
    return selected


def _legacy_payload(row: dict) -> dict[str, str]:
    mapping = {
        "title": "Nome", "category": "Categoria", "discipline": "Disciplina",
        "description": "Descrição", "event_date": "Data", "event_end_date": "Data_Fim",
        "deadline": "Data_Fim", "start_time": "Horário", "professor": "Professor",
        "location": "Local", "modality": "Modalidade", "grade": "Nota",
        "notes": "Observações", "publication_date": "Data_Atualização",
    }
    payload = {field: str(row.get(source) or "").strip() for field, source in mapping.items()}
    for field in ("publication_date", "event_date", "event_end_date", "deadline"):
        value = payload[field]
        for date_format in ("%d/%m/%Y", "%d/%m/%Y %H:%M", "%Y-%m-%d %H:%M:%S"):
            try:
                payload[field] = datetime.strptime(value, date_format).date().isoformat()
                break
            except ValueError:
                continue
    times = re.findall(r"\b([01]?\d|2[0-3]):([0-5]\d)\b", str(row.get("Horário") or ""))
    if times:
        payload["start_time"] = ":".join(times[0])
        if len(times) > 1:
            payload["end_time"] = ":".join(times[1])
    payload.update({"workload": "", "institution": "", "requirements": "",
                    "reference_link": "", "end_time": payload.get("end_time", "")})
    payload["description"] = "\n\n".join(filter(None, [payload["description"], str(row.get("Conteúdo_Texto") or "").strip()]))
    if not payload["title"]:
        payload["title"] = str(row.get("Tipo") or row.get("ID_Item") or "Registro importado").strip()
    return _clean_payload(payload)


def import_legacy_rows(rows: list[dict]) -> int:
    imported = 0
    imported_groups: set[str] = set()
    with _connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        for index, row in enumerate(rows, start=2):
            legacy_ref = f"base-row:{index}"
            if connection.execute("SELECT 1 FROM records WHERE legacy_ref = ?", (legacy_ref,)).fetchone():
                continue
            status_source = _norm(str(row.get("Status") or ""))
            official = str(row.get("Oficial") or "").strip().lower() in {"sim", "s", "true", "1"}
            if status_source in {"substituido", "arquivado", "arquivada"}:
                status, current = "arquivada", False
            elif status_source in {"cancelado", "retirado", "retirada"}:
                status, current = "retirada", False
            elif official:
                status, current = "oficial", True
            else:
                status, current = "em_revisao", False
            item_key = str(row.get("ID_Item") or row.get("ID") or f"linha-{index}").strip()
            group_id = f"sheets-{item_key}"
            imported_groups.add(group_id)
            try:
                version = max(1, int(float(row.get("Versão") or 1)))
            except (TypeError, ValueError):
                version = 1
            payload = _legacy_payload(row)
            try:
                _insert(connection, group_id=group_id, version=version, status=status,
                        payload=payload, source="Google Sheets / Base", actor="migração",
                        current_official=current, legacy_ref=legacy_ref,
                        action="importado_da_base")
                imported += 1
            except sqlite3.IntegrityError:
                _LOGGER.warning("Uma linha legada duplicada foi ignorada durante a importação.")
        _reconcile_official_records(connection, imported_groups)
        if imported:
            connection.execute(
                "INSERT OR REPLACE INTO app_meta(key, value) VALUES ('sheets_base_import', ?)",
                (agora_iso(),),
            )
    return imported


def import_legacy_sheet_if_available() -> int:
    """Migra a aba Base uma vez, quando credenciais locais já estão disponíveis."""
    from pathlib import Path as FilePath
    from data import sheets

    if not FilePath(config.CREDENCIAIS).is_file():
        return 0
    with _connect() as connection:
        imported_at = connection.execute(
            "SELECT value FROM app_meta WHERE key = 'sheets_base_import'"
        ).fetchone()
    if imported_at:
        return 0
    try:
        rows = sheets.ler_aba("base")
        count = import_legacy_rows(rows)
        with _connect() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO app_meta(key, value) VALUES ('sheets_base_import', ?)",
                (agora_iso(),),
            )
        return count
    except Exception as exc:
        _LOGGER.warning("Importação inicial da Base Google adiada (%s).", type(exc).__name__)
        return 0
