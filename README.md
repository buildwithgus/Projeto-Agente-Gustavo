# C.A.I.O — Central Acadêmica Inteligente Online

Assistente acadêmico para a **representação de turma** da Universidade Metodista de São Paulo (Análise e Desenvolvimento de Sistemas). O aluno pergunta em linguagem natural (avisos, provas, trabalhos, aulas, calendário) e o C.A.I.O responde com base nas informações **cadastradas e aprovadas pelo representante**, sem inventar dados.

## Funcionalidades

**Para o aluno** (`/`)
- Chat com o agente C.A.I.O, com atalhos rápidos: *Avisos, Calendário, Esta semana, Provas, Trabalhos, Aulas, Extensão Universitária e Resumo*.
- Painel visual com o "cérebro" animado, que muda de estado conforme a interação (repouso, pensando, respondendo).
- Histórico da conversa enviado a cada pergunta, para manter o contexto.

**Para o representante** (`/representante`)
- Login administrativo protegido por token, com sessão assinada e limite de tentativas.
- Painel com visão geral e lista de registros acadêmicos, com busca e filtros.
- Fluxo de publicação controlado: **rascunho → em revisão → oficial**, com opção de **arquivar** ou **retirar**.
- **Versionamento:** corrigir um registro cria uma nova versão e preserva a anterior.
- **Histórico de alterações** (auditoria) de cada registro e prévia antes de publicar.

**Regra de ouro do agente:** só registros *oficiais vigentes* são tratados como fonte de verdade. Quando não há registro correspondente, o C.A.I.O avisa que não encontrou confirmação oficial em vez de inventar uma resposta.

## Arquitetura

```
Navegador (HTML/CSS/JS)
        │
        ▼
   FastAPI (main.py) ──► SQLite (data/admin_store.py)
        │                  registros, versões e auditoria
        ▼
Agente no Microsoft Foundry (+ File Search)
```

A cada pergunta, o backend lê do SQLite os registros oficiais vigentes relacionados e os envia ao agente como fonte prioritária, junto com o histórico da conversa. O navegador **nunca** fala direto com o Foundry nem com o banco: credenciais e autorização ficam no backend.

## Tecnologias

- Python 3 e [FastAPI](https://fastapi.tiangolo.com/) + Uvicorn
- SQLite (banco local do painel)
- Microsoft Foundry (`azure-ai-projects`) e `azure-identity`
- Front-end em HTML, CSS e JavaScript puros
- Pytest para os testes

## Estrutura do projeto

```
.
├── main.py                  # API FastAPI e rotas das páginas
├── config.py                # Leitura do .env e configurações da turma
├── requirements.txt
├── .env.example             # Modelo das variáveis de ambiente
├── agent/
│   ├── foundry_agent.py     # Integração com o agente do Foundry
│   ├── instructions.md      # Instruções (prompt) do C.A.I.O
│   └── tools.py             # Compatibilidade (ferramentas locais desativadas)
├── data/
│   ├── admin_store.py       # Banco SQLite: registros, versões, auditoria
│   ├── resolver.py          # Seleção dos registros relevantes à pergunta
│   └── sheets.py            # Legado (Google Sheets), desativado
├── static/
│   ├── index.html           # Tela do aluno
│   ├── representante.html   # Painel do representante
│   ├── app.js / admin.js
│   └── style.css / admin.css
├── scripts/                 # Scripts auxiliares (legado)
└── tests/                   # Testes automatizados
```

## Pré-requisitos

- Python 3.10 ou superior
- Um projeto no **Microsoft Foundry** com um agente configurado (e File Search, se desejar usar documentos de referência)
- [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli) para autenticar localmente

## Como executar

1. **Clone o repositório e entre na pasta do projeto**

   ```bash
   git clone <url-do-repositorio>
   cd <pasta-do-projeto>
   ```

2. **Crie e ative um ambiente virtual**

   ```bash
   python -m venv .venv
   # Windows
   .venv\Scripts\activate
   # Linux / macOS
   source .venv/bin/activate
   ```

3. **Instale as dependências**

   ```bash
   pip install -r requirements.txt
   ```

4. **Configure as variáveis de ambiente**

   ```bash
   cp .env.example .env      # no Windows: copy .env.example .env
   ```

   Preencha o `.env` (veja a tabela abaixo).

5. **Entre na sua conta do Azure** (o agente usa `DefaultAzureCredential`)

   ```bash
   az login
   ```

6. **Inicie o servidor**

   ```bash
   uvicorn main:app --reload
   ```

7. **Acesse**
   - Aluno: <http://localhost:8000>
   - Representante: <http://localhost:8000/representante>

> Execute o comando **dentro da pasta que contém o `main.py`**, pois as páginas são carregadas por caminho relativo. O banco SQLite é criado automaticamente na primeira execução.

## Variáveis de ambiente

| Variável | Obrigatória | Descrição |
|---|---|---|
| `FOUNDRY_PROJECT_ENDPOINT` | Sim | Endpoint do projeto no Microsoft Foundry |
| `FOUNDRY_AGENT_NAME` | Sim | Nome do agente configurado no projeto |
| `FOUNDRY_AGENT_ID` | Não | ID do agente, se aplicável |
| `FOUNDRY_ENDPOINT` | Não | Endpoint do recurso (modo direto) |
| `FOUNDRY_DEPLOYMENT` | Não | Nome do deployment do modelo (modo direto) |
| `FOUNDRY_API_KEY` | Não | Chave de API, caso não use login do Azure |
| `FOUNDRY_API_VERSION` | Não | Versão da API (padrão `2024-10-21`) |
| `REPRESENTANTE_TOKEN` | Sim | Senha de acesso ao painel. Use um segredo aleatório com **32+ caracteres** |

As variáveis `GOOGLE_CREDENTIALS_FILE` e `PLANILHA_NOME` são de compatibilidade com uma versão antiga (Google Sheets) e podem ficar em branco.

## Rotas principais da API

| Método | Rota | Descrição |
|---|---|---|
| `POST` | `/api/perguntar` | Envia uma pergunta (e o histórico) ao C.A.I.O |
| `POST` | `/api/admin/login` | Login do representante |
| `POST` | `/api/admin/logout` | Encerra a sessão |
| `GET` | `/api/admin/session` | Verifica a sessão atual |
| `GET` | `/api/admin/dashboard` | Indicadores do painel |
| `GET` | `/api/admin/categories` | Categorias disponíveis |
| `GET` `POST` | `/api/admin/records` | Lista e cria registros |
| `GET` `PUT` | `/api/admin/records/{id}` | Consulta e edita um registro |
| `GET` | `/api/admin/records/{id}/history` | Histórico de alterações |
| `POST` | `/api/admin/records/{id}/review` | Envia para revisão |
| `POST` | `/api/admin/records/{id}/publish` | Publica como oficial |
| `POST` | `/api/admin/records/{id}/archive` | Arquiva |
| `POST` | `/api/admin/records/{id}/withdraw` | Retira |

Com o servidor rodando, a documentação interativa gerada pelo FastAPI fica em <http://localhost:8000/docs>.

## Testes

```bash
pytest
```

## Solução de problemas

- **O chat responde "Agente indisponível":** confira o `.env` e se você executou `az login` no mesmo terminal em que o servidor roda.
- **`uvicorn` não é reconhecido:** use `python -m uvicorn main:app --reload`.
- **Erro ao abrir a página inicial:** verifique se o comando foi executado na pasta que contém `main.py` e `static/`.
- **Logo da Metodista não aparece (Linux/macOS):** o nome do arquivo em `static/` tem acento; se o nome for corrompido na extração, renomeie o arquivo e ajuste a referência no `index.html`.

## Segurança

- **Nunca** faça commit do `.env`. Ele já está no `.gitignore`, junto com `credenciais.json` e os arquivos `*.sqlite3`.
- Se alguma chave ou token já foi exposto (em commit, zip ou print), **gere novas credenciais** no Azure e troque o `REPRESENTANTE_TOKEN`.
- Em produção, use HTTPS e guarde os segredos nas configurações do serviço de hospedagem.

## Publicação

O projeto pode ser publicado, por exemplo, no **Azure App Service (Python)** com o comando de inicialização:

```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

Configure as variáveis do `.env` na seção de configurações do serviço.

## Aviso

As informações exibidas são cadastradas pelo representante de turma. O C.A.I.O **não substitui** professores, coordenação ou os canais oficiais da Metodista.

## Licença

MIgitT.

**
