from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import json
import os
import redis
from dotenv import load_dotenv
from openai import OpenAI
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import logging
from guardrails import validar_entrada, validar_saida

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - [%(name)s] - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(
            "cliente.log", encoding="utf-8"
        ),
    ],
)

app = FastAPI()
load_dotenv()
client = OpenAI()

redis_client = redis.Redis(host="localhost", port=6379, db=0, decode_responses=True)

SERVER_ENV_PYTHON = os.path.expanduser(os.getenv("SERVER_ENV_PYTHON"))
SERVER_PATH = os.path.expanduser(os.getenv("SERVER_PATH"))
LIMITE_VOLTAS_FERRAMENTAS = 5 #Limite de voltas que o cliente pode dar para encontrar a resposta

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"], 
    allow_headers=["*"],
)

class ChatRequest(BaseModel):
    message: str
    session_id: str

def obter_ou_criar_historico(session_id: str) -> list:
    chave_redis = f"chat_session:{session_id}"
    dados_salvos = redis_client.get(chave_redis)
    if dados_salvos:
        return json.loads(dados_salvos)
    return [
        {
            "role": "system",
            "content": (
                "Você é um assistente de atendimento escolar inteligente integrado a um backend. "
                "Siga rigorosamente as regras das ferramentas e trate os erros de forma clara para o utilizador."
            )
        }
    ]

def salvar_historico(session_id: str, messages: list):
    chave_redis = f"chat_session:{session_id}"
    redis_client.setex(chave_redis, 7200, json.dumps(messages))

@app.post("/chat")
async def run_chat_agent(payload: ChatRequest):
    contador_sequence = 0
    server_params = StdioServerParameters(
        command=SERVER_ENV_PYTHON,
        args=[SERVER_PATH]
    )

    try:
        entrada = validar_entrada(payload.message)
        if not entrada.mensagem_aprovada:
            logging.warning(
                "Requisição barrada: sessão:%s motivo=%s tamanho=%d",
                payload.session_id, entrada.motivo_bloqueio, len(payload)
            )
            
            return {
                "session_id": payload.session_id,
                "response": entrada.motivo_bloqueio
            }
            
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()

                tools_response = await session.list_tools()
                logging.info(tools_response)
                openai_tools = []
                for tool in tools_response.tools:
                    openai_tools.append({
                        "type": "function",
                        "function": {
                            "name": tool.name,
                            "description": tool.description,
                            "parameters": tool.input_schema
                        }
                    })

                messages = obter_ou_criar_historico(payload.session_id)
                messages.append({
                    "role": "user",
                    "content": payload.message
                })

                response = client.chat.completions.create(
                    model="gpt-4o",
                    messages=messages,
                    tools=openai_tools,
                    tool_choice="auto"
                )

                response_message = response.choices[0].message
                assistant_msg_dict = {
                    "role": "assistant",
                    "content": response_message.content
                }
                if response_message.tool_calls:
                    assistant_msg_dict["tool_calls"] = [
                        {
                            "id": tc.id,
                            "type": tc.type,
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments
                            }
                        } for tc in response_message.tool_calls
                    ]
                messages.append(assistant_msg_dict)

                # 5. Loop seguro de execução de ferramentas
                while response_message.tool_calls and contador_sequence < LIMITE_VOLTAS_FERRAMENTAS:
                    for tool_call in response_message.tool_calls:
                        tool_name = tool_call.function.name
                        try:
                            tool_args = json.loads(tool_call.function.arguments)
                        except json.JSONDecodeError:
                            tool_args = {}

                        print(f"⚙️ [GPT a executar ferramenta]: '{tool_name}' com args: {tool_args}")

                        try:
                            result = await session.call_tool(tool_name, arguments=tool_args)
                            tool_output = result.content[0].text if result.content else "{}"
                        except Exception as e:
                            tool_output = json.dumps({"error": str(e)})

                        # Adiciona o resultado da ferramenta ao histórico
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": tool_output
                        })

                    # Pede nova conclusão à OpenAI após processar todas as tool_calls do turno
                    response = client.chat.completions.create(
                        model="gpt-4o",
                        messages=messages,
                        tools=openai_tools,
                        tool_choice="auto"
                    )
                    response_message = response.choices[0].message

                    # Serializa novamente a resposta da assistente
                    assistant_msg_dict = {
                        "role": "assistant",
                        "content": response_message.content,
                    }
                    if response_message.tool_calls:    
                        assistant_msg_dict["tool_calls"] = [
                            {
                                "id": tc.id,
                                "type": tc.type,
                                "function": {
                                    "name": tc.function.name,
                                    "arguments": tc.function.arguments
                                }
                            } for tc in response_message.tool_calls
                        ]
                        
                    messages.append(assistant_msg_dict)
                    contador_sequence += 1
                    
                if response_message.tool_calls:
                    for tc in response_message.tool_calls:
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": json.dumps({"error": "Execução interrompida: limite de etapas atingido."})
                        })
                        
                    resposta = "Não consegui concluir sua solicitação agora. Pode tentar novamente mais tarde?"
                    messages.append({"role": "assistant", "content": resposta})
                                        
                    logging.warning(
                        "limite de voltas atingido: session:%s voltas=%d",
                        payload.session_id, contador_sequence
                    )
                else:
                    resposta = response_message.content
            
            saida  = validar_saida(resposta)
            if not saida.mensagem_aprovada:
                logging.warning(
                    "Resposta barrada: sessão:%s motivo=%s",
                    payload.session_id, entrada.motivo_bloqueio
                )
                
                return {
                    "session_id": payload.session_id,
                    "response": "Não consegui gerar uma resposta adequada agora. Pode reformular a pergunta?"
                }
                
            
            salvar_historico(payload.session_id, messages)                        
            return {
                "session_id": payload.session_id,
                "response": resposta
            }

    except Exception as e:
        print(f"🔥 Erro bruto capturado: {repr(e)}")
        if hasattr(e, 'exceptions'):
            for sub in e.exceptions:
                print(f"🔥 Sub-exceção detalhada: {repr(sub)}")
        raise HTTPException(status_code=500, detail=f"Erro interno no agente: Não foi possível processar sua mensagem agora. Tente novamente em instantes")