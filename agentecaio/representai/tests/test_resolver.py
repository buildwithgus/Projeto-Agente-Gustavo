from datetime import date
from data import resolver as r

def L(**k):
    base = {"ID_Item": "T1", "Versão": 1, "Status": "Vigente", "Oficial": "Não", "Categoria": "Trabalhos e atividades",
            "Disciplina": "Disciplina X", "Data": "20/10/2026", "Data_Atualização": "01/10/2026"}
    base.update(k); return base

def test_versao_nova_substitui_antiga():
    v = r.vigentes([L(Status="Substituído"), L(Versão=2, Data="25/10/2026")])
    assert len(v) == 1 and v[0]["Data"] == "25/10/2026"

def test_oficial_vence_nao_oficial_mais_nova():
    v = r.vigentes([L(Oficial="Sim"), L(Versão=2, Data="30/10/2026")])
    assert v[0]["Oficial"] == "Sim"

def test_cancelado_some():
    assert r.vigentes([L(Status="Cancelado")]) == []

def test_aviso_nao_oficial():
    assert r.publico(L())["aviso"] != "" and r.publico(L(Oficial="Sim"))["aviso"] == ""

def test_disciplina_sem_acento():
    itens = r.vigentes([L(Disciplina="Programação")])
    assert r.filtrar(itens, disciplina="programacao")

def test_periodo_com_data_e_recorrente():
    itens = r.vigentes([L(Data="21/10/2026"), L(ID_Item="A1", Data="", Dia_Semana="sexta", Categoria="Disciplinas")])
    assert len(r.filtrar(itens, inicio=date(2026, 10, 19), fim=date(2026, 10, 25))) == 2
    assert len(r.filtrar(itens, inicio=date(2026, 10, 26), fim=date(2026, 11, 1))) == 1  # só a aula semanal

def test_a_partir_de():
    itens = r.vigentes([L(Data="01/01/2020")])
    assert r.filtrar(itens, a_partir_de=date(2026, 10, 7)) == []
