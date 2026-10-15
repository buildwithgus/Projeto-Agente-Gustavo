from agent import tools


def test_consultar_base_sem_credenciais_nao_explode_e_retorna_sem_dados():
    res = tools.executar('consultar_base', {'categoria': 'Trabalhos e atividades'})

    assert res['encontrado'] is False
    assert res['total'] == 0
    assert res['itens'] == []
    assert 'erro' not in res
