"""Compatibilidade do CAIO com o Microsoft Foundry.
As ferramentas locais de planilha foram desativadas; o conhecimento da turma agora é fornecido pelo PDF e pelos recursos do agente no Foundry."""


def executar(nome, args=None):
    return {
        "encontrado": False,
        "total": 0,
        "itens": [],
        "mensagem": "A base acadêmica está no conhecimento do Microsoft Foundry e não em planilhas locais.",
    }


SCHEMAS = []
