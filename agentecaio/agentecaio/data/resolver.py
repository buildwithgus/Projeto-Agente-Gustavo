"""Regras de negócio: qual versão é a ATUAL, o que é OFICIAL e como filtrar.
Fica em Python (e não no LLM) para ser determinístico e testável."""
import unicodedata
from datetime import date, datetime, timedelta

DIAS = ["segunda", "terca", "quarta", "quinta", "sexta", "sabado", "domingo"]

def norm(s):
    s = unicodedata.normalize("NFD", str(s or ""))
    return "".join(c for c in s if unicodedata.category(c) != "Mn").lower().strip()

def parse_data(s):
    s = str(s or "").strip()
    for f in ("%d/%m/%Y", "%Y-%m-%d", "%d/%m/%Y %H:%M", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(s, f).date()
        except ValueError:
            pass
    return None

def _num(x):
    try:
        return int(float(x))
    except (TypeError, ValueError):
        return 0

def eh_oficial(l):
    return norm(l.get("Oficial")) in ("sim", "s", "true", "1")

def vigentes(linhas):
    """Uma linha por ID_Item: ignora 'Substituído'; prioriza oficial > maior versão > atualização mais recente;
    descarta o item se a escolhida estiver 'Cancelado'."""
    grupos = {}
    for l in linhas:
        chave = str(l.get("ID_Item") or l.get("ID") or "").strip()
        if chave:
            grupos.setdefault(chave, []).append(l)
    saida = []
    for ls in grupos.values():
        cand = [l for l in ls if norm(l.get("Status")) != "substituido"]
        if not cand:
            continue
        melhor = max(cand, key=lambda l: (eh_oficial(l), _num(l.get("Versão")),
                                          parse_data(l.get("Data_Atualização")) or date.min))
        if norm(melhor.get("Status")) != "cancelado":
            saida.append(melhor)
    return saida

def _casa(a, b):
    a, b = norm(a), norm(b)
    return bool(a) and (a in b or b in a)

def _recorrente_no_periodo(l, inicio, fim):
    dia = norm(l.get("Dia_Semana"))
    if dia not in DIAS:
        return False
    d = inicio
    while d <= fim:
        if DIAS[d.weekday()] == dia:
            return True
        d += timedelta(days=1)
    return False

def filtrar(itens, categoria="", disciplina="", tipo="", palavra_chave="",
            inicio=None, fim=None, a_partir_de=None):
    out = []
    for l in itens:
        if categoria and not _casa(categoria, l.get("Categoria")):
            continue
        if disciplina and not _casa(disciplina, l.get("Disciplina")):
            continue
        if tipo and not _casa(tipo, l.get("Tipo")):
            continue
        if palavra_chave:
            texto = norm(" ".join(str(l.get(k, "")) for k in
                         ("Nome", "Descrição", "Observações", "Tipo", "Disciplina", "Conteúdo_Texto")))
            if not all(t in texto for t in norm(palavra_chave).split() if len(t) > 2):
                continue
        d = parse_data(l.get("Data"))
        if a_partir_de and d and d < a_partir_de:
            continue
        if inicio and fim:
            if d:
                d_fim = parse_data(l.get("Data_Fim")) or d
                if not (d <= fim and d_fim >= inicio):
                    continue
            elif not _recorrente_no_periodo(l, inicio, fim):
                continue
        out.append(l)
    return out

def publico(l):
    """Só os campos que o LLM precisa ver."""
    ofi = eh_oficial(l)
    return {
        "id": l.get("ID_Item") or l.get("ID"), "categoria": l.get("Categoria"),
        "disciplina": l.get("Disciplina"), "professor": l.get("Professor"),
        "tipo": l.get("Tipo"), "nome": l.get("Nome"), "descricao": l.get("Descrição"),
        "data": str(l.get("Data") or ""), "data_fim": str(l.get("Data_Fim") or ""),
        "dia_semana": l.get("Dia_Semana"), "horario": str(l.get("Horário") or ""),
        "local": l.get("Local"), "modalidade": l.get("Modalidade"), "nota": l.get("Nota"),
        "observacoes": l.get("Observações"), "atualizado_em": str(l.get("Data_Atualização") or ""),
        "oficial": ofi,
        "aviso": "" if ofi else "INFORMAÇÃO NÃO CONFIRMADA pelo representante",
    }
