# CAIO — Central Acadêmica Inteligente Online

Assistente acadêmico integrado ao agente e ao File Search do Microsoft Foundry. O painel mantém registros administrativos versionados em SQLite e o chatbot consulta a versão oficial vigente diretamente do banco a cada pergunta.

## Arquitetura
```
Site (HTML/CSS/JS) → FastAPI (main.py) → SQLite (data/admin_store.py)
                                      ↘ Agente configurado no Microsoft Foundry + File Search
```
- O site nunca fala diretamente com Foundry nem com o banco: credenciais e autorização permanecem no backend.
- Cada correção cria uma versão no mesmo grupo lógico e mantém a anterior no histórico. Rascunhos só entram em revisão ou se tornam oficiais após ação explícita do representante.
- A cada pergunta, o chatbot lê do SQLite os registros oficiais vigentes correspondentes e os envia como fonte autoritativa ao agente existente. PDF e File Search continuam disponíveis para referência geral, mas não prevalecem sobre dados administrativos atuais.

## Estrutura
```
main.py  config.py  requirements.txt  .env.example
agent/ foundry_agent.py  instructions.md  tools.py
data/  sheets.py  resolver.py
static/ index.html  app.js  style.css  representante.html  (logo.png → [PREENCHER])
scripts/criar_abas.py   tests/test_resolver.py
```

## Planilha `RepresentAIPlanilha` (Google Sheets)
**Aba `Base`** — colunas (nesta ordem): `ID, ID_Item, Versão, Categoria, Disciplina, Professor, Tipo, Nome, Descrição, Data, Data_Fim, Dia_Semana, Horário, Local, Modalidade, Nota, Status, Oficial, Data_Atualização, Observações, Conteúdo_Texto`

Seus 16 campos originais + 5 novos: `ID_Item` e `Versão` (histórico), `Data_Fim` (recesso/férias), `Dia_Semana` (aulas semanais fixas, sem data), `Conteúdo_Texto` (resumos).
- `Categoria`: Disciplinas | Trabalhos e atividades | Calendário acadêmico | Extensão/NAC | Avisos | Conteúdos
- `Status`: Vigente | Substituído | Cancelado — `Oficial`: Sim | Não — datas em dd/mm/aaaa
- **Atualizar uma informação:** não edite a linha antiga. Mude o Status dela para `Substituído` e crie nova linha com o **mesmo ID_Item**, `Versão` +1, nova data de atualização e `Oficial = Sim`.
- Aula semanal: deixe `Data` vazia e preencha `Dia_Semana` (segunda…sábado).

**Aba `Duvidas_Sem_Resposta`**: `Data_Hora, Pergunta, Categoria, Disciplina, Motivo, Status, Resposta_Representante` (o agente grava como `Pendente`; você muda para `Resolvida` depois de cadastrar a informação na Base).
**Aba `Log_Consultas`**: `Data_Hora, Pergunta, Categoria, Disciplina, Respondida, Ferramentas` (alimenta o painel).

## Como executar
1. **Foundry:** crie um projeto/recurso, implante um modelo de chat com suporte a ferramentas e copie endpoint e nome do deployment para `.env` (copie de `.env.example`). Sem chave: rode `az login` (a conta precisa do papel *Cognitive Services OpenAI User*).
2. **Google:** no Google Cloud, ative a Sheets API, crie uma conta de serviço, baixe o JSON como `credenciais.json` e **compartilhe a planilha** com o e-mail da conta de serviço (Editor).
3. `pip install -r requirements.txt`
4. `python scripts/criar_abas.py` (cria abas e cabeçalhos, sem dados)
5. Preencha a aba `Base` com os dados reais da turma.
6. `uvicorn main:app --reload` → http://localhost:8000 (aluno) e /representante (painel).
7. Coloque a logo em `static/logo.png` e ajuste as cores no topo de `static/style.css`.

No painel, edições podem ser salvas como rascunho, enviadas para revisão ou, para uma correção de informação já publicada, submetidas a prévia e confirmação explícita como `Publicar atualização`. Os campos de data são armazenados como datas ISO (`AAAA-MM-DD`), sem conversão de fuso horário.

O arquivo `.env` é carregado da pasta do projeto, independentemente do diretório de onde o servidor é iniciado. Para `REPRESENTANTE_TOKEN`, uma variável de ambiente não vazia tem precedência; se estiver vazia, o valor do `.env` é usado. Reinicie o servidor após alterar configurações. Para diagnosticar a autenticação sem expor a credencial, consulte `GET /api/admin/config-status`, que retorna somente se foi encontrada, seu comprimento e se atende ao mínimo de 32 caracteres.

**Publicar:** Azure App Service (Python), com comando de inicialização `uvicorn main:app --host 0.0.0.0 --port 8000`; variáveis do `.env` em *Configuração*; em vez de arquivo, guarde o JSON do Google em um segredo e aponte `GOOGLE_CREDENTIALS_FILE`.

## Como cada requisito é atendido
- **Atual vs. antigo / oficial:** `resolver.vigentes()` — descarta Substituído/Cancelado e prioriza Oficial > maior Versão > atualização mais recente. Itens não oficiais chegam ao modelo com `aviso`.
- **Sem inventar:** instruções rígidas + dados só via ferramentas + temperatura 0,2 + `encontrado:false` quando não há dado.
- **Human-in-the-loop:** pergunta não respondida → `Duvidas_Sem_Resposta` (também por código, se o modelo esquecer) → você cadastra na Base → marca Resolvida.
- **Limite acadêmico:** regra no prompt (não faz trabalhos/provas).

## Testes
`pytest -q` (regras de versão/oficial/período, sem internet). Casos manuais (use dados que você cadastrou):

| # | Pergunta | Esperado |
|---|---|---|
| 1 | "O que tenho para entregar?" | Lista trabalhos futuros: nome, disciplina, professor, data, nota, modalidade |
| 2 | "Quando é a prova de [PREENCHER disciplina]?" | Data da Base, com aviso se não oficial |
| 3 | "Amanhã tem aula?" | Usa `agenda_periodo(amanha)`; menciona feriado se houver |
| 4 | "Tem aula sexta?" | `agenda_periodo(dia_semana=sexta)` |
| 5 | "Quando começa o recesso?" | Usa `Data`/`Data_Fim` do recesso |
| 6 | Pergunta sobre algo não cadastrado | Diz que não encontrou + linha `Pendente` na aba de dúvidas |
| 7 | Alterar data (nova versão) e repetir pergunta | Responde a data nova, sem citar a antiga como atual |
| 8 | "Resolve o exercício X pra mim" | Recusa e oferece informar requisitos |
| 9 | "Me explica o que é [tema cadastrado]" | Resumo curto só do `Conteúdo_Texto` |
| 10 | "Me explica [tema não cadastrado]" | Não encontrado → dúvida registrada |
| 11 | Pedir uma nota/sala que o campo não tem | Diz que o dado não está cadastrado |

Exemplo de resposta esperada (ilustrativo): "Sim! A entrega de [trabalho] está marcada para [data]. Vale [nota] e é [individual/grupo]."

## Melhorias futuras
Login por e-mail institucional; notificações (WhatsApp/Teams) de prazos; botão "resolver" no painel gravando na planilha; fila de revisão por similaridade de dúvidas; busca semântica com Azure AI Search se a base crescer; avaliação automática com perguntas de teste no Foundry; limite de uso por aluno.
