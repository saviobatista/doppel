"""Anthropic Claude: turn a briefing transcript into the structured video script JSON."""
import anyio
import anthropic

from doppel_api.config import get_settings

_SCHEMA = {
    "type": "object",
    "properties": {
        "narration": {
            "type": "object",
            "properties": {"text": {"type": "string"}, "tone": {"type": "string"}},
            "required": ["text"],
        },
        "scenes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "start": {"type": "number"},
                    "end": {"type": "number"},
                    "type": {"type": "string", "enum": ["avatar", "broll"]},
                    "prompt": {"type": "string"},
                    "motion": {"type": "string"},
                },
                "required": ["id", "start", "end", "type"],
            },
        },
        "captions": {
            "type": "object",
            "properties": {"style": {"type": "string"}},
        },
    },
    "required": ["narration", "scenes"],
}

def _client() -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=get_settings().anthropic_api_key)


def _system(target_seconds: int) -> str:
    words = round(target_seconds * 2.5)
    return (
        "Você é um roteirista de vídeos verticais curtos em PT-BR. A partir do briefing "
        f"falado do usuário, gere um roteiro de ~{target_seconds} segundos. A narração deve ser "
        f"primeira pessoa, natural, com cerca de {words} palavras. Crie de 2 a 4 cenas cobrindo "
        f"a linha do tempo de 0 a {target_seconds}s sem buracos, alternando 'avatar' (o usuário "
        "falando) e 'broll', com cortes curtos (janelas de 2 a 4s). Cada cena 'broll' precisa de "
        "um 'prompt' visual concreto (para gerar uma imagem) e um 'motion' (movimento de câmera "
        "para animar). Responda SOMENTE pela ferramenta emit_script."
    )


def _call(transcript: str, target_seconds: int) -> dict:
    settings = get_settings()
    resp = _client().messages.create(
        model=settings.anthropic_model,
        max_tokens=2000,
        system=_system(target_seconds),
        messages=[{"role": "user", "content": transcript}],
        tools=[{
            "name": "emit_script",
            "description": "Emite o roteiro estruturado do vídeo.",
            "input_schema": _SCHEMA,
        }],
        tool_choice={"type": "tool", "name": "emit_script"},
    )
    return next(b.input for b in resp.content if b.type == "tool_use")


async def build_script(transcript: str, target_seconds: int) -> dict:
    return await anyio.to_thread.run_sync(_call, transcript, target_seconds)
