import json
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import config
import main
from data import admin_store


@pytest.fixture

def store_db(tmp_path, monkeypatch):
    monkeypatch.setattr(admin_store, "DB_PATH", tmp_path / "caio_admin.sqlite3")
    admin_store.init_db()
    return admin_store


def dados(**overrides):
    registro = {
        "title": "Prova de Estruturas",
        "category": "Provas",
        "discipline": "Estrutura de Dados",
        "description": "Avaliação do semestre",
        "publication_date": "2026-10-10",
        "event_date": "2026-11-20",
        "start_time": "19:30",
        "end_time": "21:10",
        "modality": "Presencial",
        "professor": "Professora Exemplo",
    }
    registro.update(overrides)
    return registro


def publicar(store, record):
    enviado = store.transition_record(record["id"], "revisar")
    return store.transition_record(
        enviado["id"], "oficial", confirm=True,
        expected_updated_at=enviado["updated_at"],
    )


def test_rascunho_revisao_e_publicacao_confirmada(store_db):
    draft = store_db.create_record(dados())

    assert draft["status"] == "rascunho"
    assert store_db.public_context("prova de estruturas") == []
    with pytest.raises(ValueError, match="Envie o rascunho"):
        store_db.transition_record(
            draft["id"], "oficial", confirm=True,
            expected_updated_at=draft["updated_at"],
        )

    reviewed = store_db.transition_record(draft["id"], "revisar")
    with pytest.raises(ValueError, match="Confirme a prévia"):
        store_db.transition_record(
            draft["id"], "oficial", confirm=False,
            expected_updated_at=reviewed["updated_at"],
        )
    official = store_db.transition_record(
        draft["id"], "oficial", confirm=True,
        expected_updated_at=reviewed["updated_at"],
    )
    assert official["status"] == "oficial"
    assert store_db.public_context("prova de estruturas")[0]["titulo"] == "Prova de Estruturas"


def test_correcao_preserva_versao_publicada_ate_aprovacao(store_db):
    initial = publicar(store_db, store_db.create_record(dados()))
    draft = store_db.update_record(initial["id"], dados(event_date="2026-11-27"), reason="Data corrigida")

    assert draft["version"] == 2
    assert draft["status"] == "rascunho"
    assert store_db.public_context("prova de estruturas")[0]["data"] == "2026-11-20"

    reviewed = store_db.transition_record(draft["id"], "revisar")
    updated = store_db.transition_record(
        draft["id"], "oficial", confirm=True,
        expected_updated_at=reviewed["updated_at"],
    )
    current = store_db.public_context("prova de estruturas")
    assert updated["status"] == "oficial"
    assert len(current) == 1 and current[0]["data"] == "2026-11-27"
    assert store_db.get_record(initial["id"])["status"] == "arquivada"
    assert any(item["reason"] == "Data corrigida" for item in store_db.get_history(draft["id"]))


def test_filtros_combinados_paginacao_e_historico(store_db):
    first = publicar(store_db, store_db.create_record(dados()))
    second = store_db.create_record(dados(
        title="Aviso de Recesso", category="Avisos", discipline="",
        event_date="2026-12-01", professor="Coordenação",
    ))

    result = store_db.list_records(
        {"category": "Provas", "discipline": "Estrutura de Dados",
         "status": "oficial", "publication_from": "2026-10-01",
         "publication_to": "2026-10-31", "event_from": "2026-11-01",
         "event_to": "2026-11-30", "professor": "Professora Exemplo",
         "q": "Estruturas"},
        limit=1, offset=0, sort="event_date", direction="asc",
    )

    assert result["total"] == 1
    assert result["items"][0]["id"] == first["id"]
    assert store_db.dashboard_stats()["rascunho"] == 1
    assert store_db.transition_record(first["id"], "arquivar")["status"] == "arquivada"
    assert store_db.public_context("historico da prova de estruturas")
    assert store_db.public_context("prova de estruturas") == []
    assert second["status"] == "rascunho"


def test_api_admin_exige_sessao_csrf_e_nao_aceita_status_do_cliente(tmp_path, monkeypatch):
    monkeypatch.setattr(admin_store, "DB_PATH", tmp_path / "http_admin.sqlite3")
    monkeypatch.setattr(config, "TOKEN_REPRESENTANTE", "A" * 48)
    with TestClient(main.app) as client:
        assert client.get("/api/admin/records").status_code == 401
        login = client.post("/api/admin/login", json={"token": "A" * 48})
        assert login.status_code == 200
        csrf = client.cookies.get("caio_csrf")
        assert csrf
        assert client.post("/api/admin/records", json=dados()).status_code == 403

        payload = {**dados(), "status": "oficial", "current_official": True}
        created = client.post("/api/admin/records", json=payload, headers={"X-CSRF-Token": csrf})
        assert created.status_code == 201
        assert created.json()["item"]["status"] == "rascunho"
        assert created.json()["item"]["current_official"] is False
        assert client.get("/api/admin/session").json()["authenticated"] is True
        assert client.post("/api/admin/logout", json={}, headers={"X-CSRF-Token": csrf}).status_code == 200
        assert client.get("/api/admin/records").status_code == 401


def test_login_recusa_segredo_administrativo_fraco(monkeypatch):
    monkeypatch.setattr(config, "TOKEN_REPRESENTANTE", "curto")
    with TestClient(main.app) as client:
        response = client.post("/api/admin/login", json={"token": "curto"})

    assert response.status_code == 503
    assert "32 caracteres" in response.json()["detail"]


def test_diagnostico_configuracao_retorna_somente_metadados_seguros(monkeypatch):
    secret = "Z" * 36
    monkeypatch.setattr(config, "TOKEN_REPRESENTANTE", secret)

    with TestClient(main.app) as client:
        response = client.get("/api/admin/config-status")

    assert response.status_code == 200
    assert response.json() == {"found": True, "length": 36, "valid": True}
    assert secret not in response.text


def test_token_de_ambiente_vazio_usa_valor_do_dotenv():
    value = config._resolve_representante_token("", "D" * 40)

    assert value == "D" * 40


def test_edicao_oficial_publicacao_explicita_historico_e_chat_apos_reinicializacao(
    monkeypatch, tmp_path
):
    from types import SimpleNamespace

    monkeypatch.setattr(admin_store, "DB_PATH", tmp_path / "official_update.sqlite3")
    monkeypatch.setattr(config, "TOKEN_REPRESENTANTE", "T" * 48)
    monkeypatch.setattr(config, "FOUNDRY_PROJECT_ENDPOINT", "")
    monkeypatch.setattr(config, "FOUNDRY_AGENT_ID", "")
    calls = {}

    class FakeResponses:
        def create(self, **kwargs):
            calls.update(kwargs)
            return SimpleNamespace(output_text="O evento corrigido será em 27/11/2026.")

    fake_client = SimpleNamespace(
        conversations=SimpleNamespace(create=lambda: SimpleNamespace(id="conversation-update")),
        responses=FakeResponses(),
    )
    monkeypatch.setattr(main.foundry_agent, "_get_cliente", lambda: fake_client)

    with TestClient(main.app) as client:
        login = client.post("/api/admin/login", json={"token": "T" * 48})
        assert login.status_code == 200
        csrf = client.cookies.get("caio_csrf")
        headers = {"X-CSRF-Token": csrf}

        created_response = client.post(
            "/api/admin/records",
            json=dados(
                title="Projeto Farol",
                category="Trabalhos",
                description="Entrega do proejto Farol",
                event_date="2026-11-20",
            ),
            headers=headers,
        )
        assert created_response.status_code == 201
        original = created_response.json()["item"]
        assert original["status"] == "rascunho"
        assert admin_store.public_context("Qual a data do Projeto Farol?") == []

        reviewed = client.post(
            f"/api/admin/records/{original['id']}/review", json={}, headers=headers
        ).json()["item"]
        original = client.post(
            f"/api/admin/records/{original['id']}/publish",
            json={"confirm": True, "expected_updated_at": reviewed["updated_at"]},
            headers=headers,
        ).json()["item"]
        assert original["status"] == "oficial"
        assert admin_store.public_context("Qual a data do Projeto Farol?")[0]["data"] == "2026-11-20"

        corrected_response = client.put(
            f"/api/admin/records/{original['id']}",
            json=dados(
                title="Projeto Farol",
                category="Trabalhos",
                description="Entrega do projeto Farol",
                event_date="2026-11-27",
            ),
            headers=headers,
        )
        assert corrected_response.status_code == 200
        draft = corrected_response.json()["item"]
        assert draft["id"] != original["id"]
        assert draft["group_id"] == original["group_id"]
        assert draft["version"] == 2
        assert draft["status"] == "rascunho"
        assert draft["event_date"] == "2026-11-27"
        assert draft["has_official_ancestor"] is True

        current = admin_store.public_context("Qual a data do Projeto Farol?")[0]
        assert current["versao"] == 1
        assert current["data"] == "2026-11-20"
        assert client.get(f"/api/admin/records/{draft['id']}").json()["item"]["description"] == "Entrega do projeto Farol"

        published_response = client.post(
            f"/api/admin/records/{draft['id']}/publish",
            json={"confirm": True, "expected_updated_at": draft["updated_at"]},
            headers=headers,
        )
        assert published_response.status_code == 200
        published = published_response.json()["item"]
        assert published["id"] == draft["id"]
        assert published["status"] == "oficial"
        assert published["current_official"] is True
        assert published["version"] == 2

        current_rows = client.get(
            "/api/admin/records",
            params={"category": "Trabalhos", "q": "Projeto Farol", "limit": 100},
            headers=headers,
        ).json()["items"]
        group_rows = [item for item in current_rows if item["group_id"] == original["group_id"]]
        assert len(group_rows) == 2
        assert sum(item["current_official"] for item in group_rows) == 1
        assert client.get(f"/api/admin/records/{original['id']}").json()["item"]["status"] == "arquivada"

        history = client.get(f"/api/admin/records/{published['id']}/history").json()["items"]
        assert any(item["action"] == "versao_corrigida" for item in history)
        assert any(item["action"] == "oficial" for item in history)
        assert any(item["before"]["event_date"] == "2026-11-20" for item in history)
        assert any(item["after"]["event_date"] == "2026-11-27" for item in history)

        current = admin_store.public_context("Qual a data do Projeto Farol?")[0]
        assert current["versao"] == 2
        assert current["conteudo"] == "Entrega do projeto Farol"
        assert current["data"] == "2026-11-27"
        assert current["data_final"] == ""
        assert current["hora_inicio"] == "19:30"
        assert "2026-11-20" not in str(current)

        answer = client.post(
            "/api/perguntar",
            json={
                "pergunta": "Qual a data do Projeto Farol?",
                "historico": [
                    {"role": "user", "content": "Qual era a data?"},
                    {"role": "assistant", "content": "A data antiga era 20/11/2026."},
                ],
            },
        )
        assert answer.status_code == 200
        assert "27/11/2026" in answer.json()["resposta"]
        current_prompt = calls["input"][-1]["content"]
        assert "Entrega do projeto Farol" in current_prompt
        assert "2026-11-27" in current_prompt
        assert "2026-11-20" not in current_prompt
        assert "ignore conflitos no PDF, File Search e histórico" in current_prompt

        restarted_process = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "import json, sys; from pathlib import Path; "
                    "from data import admin_store; "
                    "admin_store.DB_PATH = Path(sys.argv[1]); "
                    "admin_store.init_db(); "
                    "print(json.dumps(admin_store.public_context('Qual a data do Projeto Farol?'), "
                    "ensure_ascii=False))"
                ),
                str(admin_store.DB_PATH),
            ],
            cwd=Path(__file__).resolve().parents[1],
            check=True,
            capture_output=True,
            text=True,
        )
        restarted = json.loads(restarted_process.stdout)[0]
        assert restarted["versao"] == 2
        assert restarted["data"] == "2026-11-27"


def test_importacao_legada_nao_expoe_versoes_oficiais_antigas(store_db):
    imported = store_db.import_legacy_rows([
        {
            "ID_Item": "import-projeto-farol",
            "Versão": "1",
            "Categoria": "Trabalhos",
            "Tipo": "Entrega",
            "Nome": "Projeto Farol",
            "Descrição": "Versão antiga",
            "Data": "20/11/2026",
            "Status": "Vigente",
            "Oficial": "Sim",
        },
        {
            "ID_Item": "import-projeto-farol",
            "Versão": "2",
            "Categoria": "Trabalhos",
            "Tipo": "Entrega",
            "Nome": "Projeto Farol",
            "Descrição": "Versão atual",
            "Data": "27/11/2026",
            "Status": "Vigente",
            "Oficial": "Sim",
        },
    ])

    assert imported == 2
    with store_db._connect() as connection:
        connection.execute(
            """UPDATE records SET status = 'oficial', current_official = 1
               WHERE group_id = 'sheets-import-projeto-farol' AND version = 1"""
        )
    store_db.init_db()

    current = store_db.public_context("Qual a data do Projeto Farol?")
    rows = store_db.list_records({"q": "Projeto Farol"}, limit=100)["items"]
    assert len(current) == 1
    assert current[0]["data"] == "2026-11-27"
    assert current[0]["conteudo"] == "Versão atual"
    assert [record["status"] for record in rows].count("oficial") == 1
    assert [record["status"] for record in rows].count("arquivada") == 1


def test_fluxo_http_completo_persiste_e_publica_versoes(monkeypatch, tmp_path):
    monkeypatch.setattr(admin_store, "DB_PATH", tmp_path / "flow_admin.sqlite3")
    monkeypatch.setattr(config, "TOKEN_REPRESENTANTE", "S" * 48)
    payload = dados()
    with TestClient(main.app) as client:
        login = client.post("/api/admin/login", json={"token": "S" * 48})
        csrf = client.cookies.get("caio_csrf")
        headers = {"X-CSRF-Token": csrf}
        created = client.post("/api/admin/records", json=payload, headers=headers).json()["item"]
        assert created["status"] == "rascunho"
        assert client.get("/api/dashboard").status_code == 200
        assert admin_store.public_context("prova de estruturas") == []

        reviewing = client.post(
            f"/api/admin/records/{created['id']}/review", json={}, headers=headers
        ).json()["item"]
        assert reviewing["status"] == "em_revisao"
        assert client.post(
            f"/api/admin/records/{created['id']}/publish", json={}, headers=headers
        ).status_code == 409
        official = client.post(
            f"/api/admin/records/{created['id']}/publish",
            json={"confirm": True, "expected_updated_at": reviewing["updated_at"]},
            headers=headers,
        ).json()["item"]
        assert official["status"] == "oficial"
        assert admin_store.public_context("prova de estruturas")[0]["data"] == "2026-11-20"

        corrected = client.put(
            f"/api/admin/records/{created['id']}",
            json={**payload, "event_date": "2026-11-27", "reason": "Data corrigida"},
            headers=headers,
        ).json()["item"]
        assert corrected["status"] == "rascunho"
        assert admin_store.public_context("prova de estruturas")[0]["data"] == "2026-11-20"
        reviewed = client.post(
            f"/api/admin/records/{corrected['id']}/review", json={}, headers=headers
        ).json()["item"]
        current = client.post(
            f"/api/admin/records/{corrected['id']}/publish",
            json={"confirm": True, "expected_updated_at": reviewed["updated_at"]},
            headers=headers,
        ).json()["item"]
        assert current["version"] == 2
        assert current["status"] == "oficial"
        assert client.get(f"/api/admin/records/{created['id']}/history").json()["items"]
        assert any(item["action"] == "arquivada_por_nova_versao"
                   for item in admin_store.get_history(corrected["id"]))

        archived = client.post(
            f"/api/admin/records/{corrected['id']}/archive", json={}, headers=headers
        ).json()["item"]
        assert archived["status"] == "arquivada"
        assert admin_store.public_context("prova de estruturas") == []
        assert admin_store.public_context("historico prova de estruturas")

        record_id = corrected["id"]
        assert client.post("/api/admin/logout", json={}, headers=headers).status_code == 200
        assert client.get("/api/admin/records").status_code == 401

    admin_store.init_db()
    assert admin_store.get_record(record_id)["status"] == "arquivada"
