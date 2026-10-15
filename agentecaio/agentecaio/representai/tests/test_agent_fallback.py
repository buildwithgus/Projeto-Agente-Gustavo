from agent.foundry_agent import formata_resposta_sem_dado


def test_formata_resposta_sem_dado_nao_menciona_erro_de_sistema():
    texto = formata_resposta_sem_dado()

    assert "erro no sistema" not in texto.lower()
    assert "base" in texto.lower()
    assert "representante" in texto.lower()
