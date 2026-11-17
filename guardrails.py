from pydantic import BaseModel
import re
import unicodedata
import logging

IGNORAR_INSTRUCOES = ("ignore as instrucoes", "ignore previous instructions", "voce agora e", "agora voce eh")
PADROES_SEGREDOS = [
    r"eyJ[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}",
    r"Bearer\s+[a-zA-Z0-9\-\._~\+\/]+=*",
    r"\b(?:sk-|sdk-|ghp_|gho_|AKIA|AIza|xox[baprs]-)[a-zA-Z0-9_\-]{16,}\b",
    r"(?i)\b(?:password|senha|secret|api_key|apikey|token|access_token)\b\s*[:=]\s*['\"]?[^\s'\"]{8,}['\"]?"
]
TAMANHO_MAXIMO_MENSAGEM=500
REGEX_SEGREDOS = re.compile("|".join(PADROES_SEGREDOS))

logger = logging.getLogger(__name__)

class TopicValidate(BaseModel):
    mensagem_aprovada: bool
    motivo_bloqueio: str = ""

def normalizar_texto(texto: str) -> str:
    texto = texto.strip().lower()
    texto_sem_acento = "".join(
        char
        for char in unicodedata.normalize("NFD", texto)
        if unicodedata.category(char) != "Mn"
    )
    
    return re.sub(r"\s+"," ", texto_sem_acento)


def validar_entrada(menssagem: str) -> TopicValidate:
    tamanho = len(menssagem.strip())
    if tamanho == 0:
        return TopicValidate(
            mensagem_aprovada=False, motivo_bloqueio="A mensagem está vazia."
        )
    
    if tamanho > TAMANHO_MAXIMO_MENSAGEM:
        return TopicValidate(
                    mensagem_aprovada=False, motivo_bloqueio="A mensagem está grande demais."
                )
        
    mensagem_limpa = normalizar_texto(menssagem)
    if not mensagem_limpa:
        return TopicValidate(
            mensagem_aprovada=False, motivo_bloqueio="A mensagem está vazia"
        )
    
    padrao = "|".join(re.escape(frase) for frase in IGNORAR_INSTRUCOES)
    
    if re.search(padrao, mensagem_limpa):
        return TopicValidate(
            mensagem_aprovada=False,
            motivo_bloqueio="Tentativa de burlar instruções detectada."
        )
    
    return TopicValidate(mensagem_aprovada=True)

def validar_saida(resposta: str) -> TopicValidate:
    if REGEX_SEGREDOS.search(resposta):
        return TopicValidate(
            mensagem_aprovada=False,
            motivo_bloqueio="Tentativa de expor segredos ou credenciais."
        )
    return TopicValidate(mensagem_aprovada=True)
    