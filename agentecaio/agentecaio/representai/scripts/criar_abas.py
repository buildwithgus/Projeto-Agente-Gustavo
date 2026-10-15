"""Cria as abas e cabeçalhos na planilha RepresentAIPlanilha (execute uma vez). Não insere dados."""
import sys; sys.path.insert(0, ".")
import config
from data import sheets

p = sheets._abrir()
for chave, cols in (("base", config.COLUNAS_BASE), ("duvidas", config.COLUNAS_DUVIDAS), ("log", config.COLUNAS_LOG)):
    try:
        ws = p.worksheet(config.ABAS[chave])
    except Exception:
        ws = p.add_worksheet(config.ABAS[chave], rows=500, cols=len(cols))
    ws.update([cols], "A1")
    print("OK:", config.ABAS[chave])
