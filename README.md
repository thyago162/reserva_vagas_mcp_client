# reserva_vagas_mcp_client

Orquestrador em FastAPI que atua como **cliente MCP** no sistema de reserva de vagas escolares. É a ponte entre o frontend e o servidor MCP: recebe a mensagem do usuário, consulta no servidor MCP quais ferramentas estão disponíveis e envia o contexto para o LLM decidir quais ações executar.

Faz parte do projeto [reserva_vagas](https://github.com/thyago162/reserva_vagas/blob/main/docs/arquitetura%20.png). Veja a arquitetura completa lá.

## Como funciona

1. O frontend envia a mensagem do usuário para este serviço.
2. O cliente busca as ferramentas disponíveis no [servidor MCP](https://github.com/thyago162/reserva_vagas_mcp_server).
3. O contexto da conversa (guardado no Redis) e as ferramentas são enviados ao LLM.
4. O LLM escolhe a ferramenta, o cliente a executa no servidor MCP e devolve a resposta ao usuário.

## Tecnologias

Python 3.10, FastAPI, <SDK de MCP usado>, Redis, <provedor do LLM>

## Como rodar

```bash
git clone https://github.com/thyago162/reserva_vagas_mcp_client
cd reserva_vagas_mcp_client
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # preencha as variáveis
uvicorn <modulo>:app --reload
```

## Sessão
As conversas ficam no Redis, identificadas pelo id da sessão enviado pelo front, e expiram após 2 horas sem atividade.

## Variáveis de ambiente

| Variável | Descrição |
|---|---|
| `<CHAVE_DO_LLM>` | Chave de acesso ao provedor do LLM |
| `<URL_DO_SERVIDOR_MCP>` | Endereço do servidor MCP |
| `<URL_DO_REDIS>` | Conexão com o Redis |

## Status
    Projeto em desenvolvimento.