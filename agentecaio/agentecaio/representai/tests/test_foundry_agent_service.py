from types import SimpleNamespace

from agent import foundry_agent


def test_responder_usa_agente_do_foundry_quando_configurado(monkeypatch):
    calls = {}

    class FakeThread:
        id = "thread-123"

    class FakeRun:
        status = "completed"
        id = "run-123"

    class FakeMessage:
        role = "assistant"
        content = [{"text": {"value": "Resposta do agente do PDF."}}]

    class FakeMessages:
        def __init__(self):
            self.data = [FakeMessage()]

    class FakeAgents:
        def create_thread(self):
            calls["thread"] = True
            return FakeThread()

        def create_message(self, **kwargs):
            calls["message"] = kwargs

        def create_run(self, **kwargs):
            calls["run"] = kwargs
            return FakeRun()

        def get_run(self, **kwargs):
            return FakeRun()

        def list_messages(self, **kwargs):
            return FakeMessages()

    monkeypatch.setattr(foundry_agent, "_get_agent_client", lambda: FakeAgents())
    monkeypatch.setattr(foundry_agent.config, "FOUNDRY_PROJECT_ENDPOINT", "https://proj.services.ai.azure.com/api/projects/proj")
    monkeypatch.setattr(foundry_agent.config, "FOUNDRY_AGENT_ID", "agent-123")

    resultado = foundry_agent.responder("Qual é a resposta do PDF?", historico=[{"role": "user", "content": "Pergunta anterior"}])

    assert resultado["resposta"] == "Resposta do agente do PDF."
    assert resultado["respondida"] is True
    assert calls["run"]["assistant_id"] == "agent-123"
