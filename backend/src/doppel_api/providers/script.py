"""Anthropic Claude: turn a briefing transcript into the structured video script JSON."""
import base64

import anyio
import anthropic

from doppel_api.config import get_settings
from doppel_api.providers.identity import ATTRIBUTE_KEYS

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
    return anthropic.Anthropic(api_key=get_settings().anthropic_api_key, timeout=120.0)


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


# --- Avatar identity: extract facial attributes from the reference first frame ---

_FACE_SCHEMA = {
    "type": "object",
    "properties": {
        **{k: {"type": "string"} for k in ATTRIBUTE_KEYS},
        "identity_specific_negatives": {
            "type": "array",
            "items": {"type": "string"},
            "description": (
                "1-3 wrong alterations to AVOID, phrased as avoidances "
                "(e.g. 'do not tint the beard ginger/red', 'do not change eye color')."
            ),
        },
    },
    "required": [*ATTRIBUTE_KEYS, "identity_specific_negatives"],
}

_FACE_SYSTEM = (
    "You are a facial-attribute extractor for an image-to-image avatar pipeline. "
    "The reference photo is fed to the generator as the source image, so it already "
    "carries the true colors — your job is precise, conservative text that won't fight "
    "the pixels. Emit ONLY the emit_face_attributes tool. Rules:\n"
    "- Describe only what is visibly verifiable. Be specific, neutral, literal.\n"
    "- Use concise descriptive phrases, not full sentences.\n"
    "- COLOR DISCIPLINE: name hair color only in 'hair_color' and beard color only in "
    "'facial_hair'. Never restate a color anywhere else.\n"
    "- Be conservative with warm tones. Generators over-saturate warm color words. Do "
    "NOT call hair or a beard 'reddish', 'auburn', 'ginger', or 'copper' unless red is "
    "unmistakable and dominant. If there is only slight warmth, say e.g. 'dark brown' "
    "(optionally 'with faint warm tones'), not 'reddish-brown'.\n"
    "- Compare beard to hair by lightness, not hue: e.g. 'dark brown, slightly darker "
    "than the hair' — do not invent a hue difference.\n"
    "- 'distinguishing_features' must describe SHAPE, proportion, contrast, and permanent "
    "marks (moles, scars, freckles, asymmetry, distinctive hairline) — never color.\n"
    "- 'identity_specific_negatives' are WRONG changes to AVOID, phrased as avoidances "
    "(e.g. 'do not tint the beard ginger/red', 'do not change eye color', 'do not lower "
    "or thicken the hairline') — NOT a restatement of the features.\n"
    "- If a feature is absent (e.g. no facial hair), state that explicitly "
    "(e.g. 'clean-shaven, no facial hair').\n"
    "- Do NOT guess name, identity, or anything not visible."
)


def _face_call(image_b64: str, media_type: str) -> dict:
    settings = get_settings()
    resp = _client().messages.create(
        model=settings.anthropic_prompt_model,
        max_tokens=1500,
        system=_FACE_SYSTEM,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {"type": "base64", "media_type": media_type, "data": image_b64},
                },
                {"type": "text", "text": "Extract the facial attributes from this photo."},
            ],
        }],
        tools=[{
            "name": "emit_face_attributes",
            "description": "Emit the visibly-verifiable facial attributes of the subject.",
            "input_schema": _FACE_SCHEMA,
        }],
        tool_choice={"type": "tool", "name": "emit_face_attributes"},
    )
    return next(b.input for b in resp.content if b.type == "tool_use")


async def extract_face_attributes(image_bytes: bytes, *, media_type: str = "image/png") -> dict:
    """Vision call: extract neutral, verifiable facial attributes for the identity lock."""
    b64 = base64.b64encode(image_bytes).decode("ascii")
    return await anyio.to_thread.run_sync(_face_call, b64, media_type)


_ENV_SYSTEM = (
    "You describe the physical SETTING/ENVIRONMENT visible behind a person in a photo, "
    "for an image generator that will recreate the same kind of space. Reply with ONE "
    "concise phrase (max ~25 words): the room/location type, key background elements, "
    "furniture, lighting mood, and color palette. Describe ONLY the environment — never "
    "the person, their face, clothing, or body. No preamble, no quotes, just the phrase."
)


def _env_call(image_b64: str, media_type: str) -> str:
    resp = _client().messages.create(
        model=get_settings().anthropic_prompt_model,
        max_tokens=200,
        system=_ENV_SYSTEM,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {"type": "base64", "media_type": media_type, "data": image_b64},
                },
                {"type": "text", "text": "Describe the environment/setting behind the person."},
            ],
        }],
    )
    return " ".join(b.text for b in resp.content if b.type == "text").strip()


async def extract_environment(image_bytes: bytes, *, media_type: str = "image/png") -> str:
    """Vision call: a short description of the setting behind the subject (for looks)."""
    b64 = base64.b64encode(image_bytes).decode("ascii")
    return await anyio.to_thread.run_sync(_env_call, b64, media_type)
