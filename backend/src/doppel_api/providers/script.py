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

_SYSTEM = (
    "Você é um roteirista de vídeos verticais curtos em PT-BR. A partir do briefing falado "
    "do usuário, gere um roteiro de ~30 segundos. A narração deve ser primeira pessoa, natural, "
    "com cerca de 75 a 85 palavras. Crie de 3 a 5 cenas cobrindo a linha do tempo de 0 a 30s sem "
    "buracos, alternando 'avatar' (o usuário falando) e 'broll'. Cada cena 'broll' precisa de um "
    "'prompt' visual concreto (para gerar uma imagem) e um 'motion' (movimento de câmera para "
    "animar). Responda SOMENTE pela ferramenta emit_script."
)


def _client() -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=get_settings().anthropic_api_key)


def _call(transcript: str) -> dict:
    settings = get_settings()
    resp = _client().messages.create(
        model=settings.anthropic_model,
        max_tokens=2000,
        system=_SYSTEM,
        messages=[{"role": "user", "content": transcript}],
        tools=[{
            "name": "emit_script",
            "description": "Emite o roteiro estruturado do vídeo.",
            "input_schema": _SCHEMA,
        }],
        tool_choice={"type": "tool", "name": "emit_script"},
    )
    return next(b.input for b in resp.content if b.type == "tool_use")


async def build_script(transcript: str) -> dict:
    return await anyio.to_thread.run_sync(_call, transcript)
