from types import SimpleNamespace

from agent import foundry_agent


def test_responder_usa_responses_do_agente_configurado(monkeypatch):
    calls = {}
    markdown = "**Provas cadastradas**\n\n**1. Gestão de Projetos**\n\n- **Data:** 23/11/2026"

    def fake_create(**kwargs):
        calls.update(kwargs)
        return SimpleNamespace(output_text=markdown)

    fake_client = SimpleNamespace(
        conversations=SimpleNamespace(create=lambda: SimpleNamespace(id="conversation-123")),
        responses=SimpleNamespace(create=fake_create),
    )

    monkeypatch.setattr(foundry_agent, "_get_cliente", lambda: fake_client)
    monkeypatch.setattr(foundry_agent.admin_store, "public_context", lambda _: [])

    resultado = foundry_agent.responder("Explique o conteúdo do documento.", historico=[])

    assert calls["conversation"] == "conversation-123"
    assert calls["input"] == [{"role": "user", "content": foundry_agent._pergunta_com_contexto("Explique o conteúdo do documento.")}]
    assert resultado["resposta"] == markdown
    assert resultado["respondida"] is True
    assert resultado["ferramentas"] == []


def test_classifica_erros_http_separadamente():
    class HttpError(Exception):
        def __init__(self, status_code, message="", url=""):
            super().__init__(message)
            self.status_code = status_code
            self.request = SimpleNamespace(url=url)

    assert "autenticação" in foundry_agent._classificar_erro_foundry(HttpError(401)).lower()
    assert "autorização" in foundry_agent._classificar_erro_foundry(HttpError(403)).lower()
    assert "agente" in foundry_agent._classificar_erro_foundry(HttpError(404, "Agent not found")).lower()
    assert "projeto/endpoint" in foundry_agent._classificar_erro_foundry(
        HttpError(404, url="https://example.invalid/api/projects/missing")
    ).lower()
    assert "deployment" in foundry_agent._classificar_erro_foundry(
        HttpError(404, url="https://example.invalid/openai/deployments/missing/chat/completions")
    ).lower()


def test_classifica_falha_de_rede_dns():
    mensagem = foundry_agent._classificar_erro_foundry(ConnectionError("DNS lookup failed"))

    assert "rede/dns" in mensagem.lower()


def test_extrai_resposta_removendo_apenas_marcadores_de_citacao():
    inicio = chr(0xE200)
    fim = chr(0xE201)
    marcador = f"{inicio}filecite{inicio}turn0file0{inicio}turn0file2{fim}"
    texto = f"**Projeto Mundo Digital** {marcador} atende ADS. {{referência legítima}}"

    resultado = foundry_agent._extrair_texto_resposta(SimpleNamespace(output_text=texto))

    assert resultado == "**Projeto Mundo Digital**  atende ADS. {referência legítima}"


def test_prompt_do_foundry_prioriza_registros_oficiais_e_identifica_origem(monkeypatch):
    records = [{"titulo": "Prova de Estruturas", "data": "2026-11-27", "origem": "painel",
                "versao": 2, "status": "oficial vigente"}]
    monkeypatch.setattr(foundry_agent.admin_store, "public_context", lambda _: records)

    prompt = foundry_agent._pergunta_com_contexto("Quando é a prova de estruturas?")

    assert "Prova de Estruturas" in prompt
    assert "FONTE ADMINISTRATIVA ATUAL E AUTORITATIVA" in prompt
    assert "ignore conflitos no PDF" in prompt


def test_prompt_sem_registro_oficial_nao_confirma_referencia_do_pdf(monkeypatch):
    monkeypatch.setattr(foundry_agent.admin_store, "public_context", lambda _: [])

    prompt = foundry_agent._pergunta_com_contexto("Quando é a prova de estruturas?")

    assert "não retornou registro oficial vigente" in prompt.lower()
    assert "não confirmado pelo representante" in prompt
