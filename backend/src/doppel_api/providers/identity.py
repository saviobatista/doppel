"""Avatar identity-lock prompt orchestration.

Pure functions (no network). The flow is:

  1. extract_face_attributes(first_frame)   -> dict (in providers/script.py)
  2. build_identity_prompt(attrs)           -> identity-lock base prompt with a
                                               single swappable {{scene_block}}
  3. apply_scene(base, scene_block)         -> final per-scene prompt

The identity-lock base is persisted on the avatar and reused for every scene
generation (look options now, scenario videos later) so the same person stays
recognizable across all outputs.
"""

# Scalar attribute keys the extractor must return (filled into the template).
ATTRIBUTE_KEYS: list[str] = [
    "age_range",
    "gender_presentation",
    "ethnicity_appearance",
    "skin_tone",
    "skin_undertone",
    "body_frame",
    "shoulders",
    "face_shape",
    "hair_length",
    "hair_color",
    "hair_style",
    "hairline",
    "facial_hair",
    "eye_color",
    "eye_shape",
    "eye_set",
    "eyebrow_description",
    "nose_description",
    "mouth_description",
    "distinguishing_features",
    "expression",
]

# `identity_specific_negatives` is a list (1-3 items), handled separately.

# NOTE: the target edit models (seedream/v4.5/edit, nano-banana-2/edit) accept ONLY a
# positive `prompt` — there is no negative_prompt field. So this template is positive-only:
# a stray "=== NEGATIVE / AVOID ===" block would be read as things TO render. Identity
# preservation is therefore phrased positively, and color is deferred to the source pixels.
IDENTITY_TEMPLATE = """=== SUBJECT IDENTITY LOCK — KEEP THE PERSON FROM THE SOURCE IMAGE ===
This is an image edit of a real, specific individual. Keep the exact same person from the \
source image: same facial identity, bone structure, proportions, age, and body weight; the \
likeness must stay recognizable and consistent across every output. Preserve the colors \
exactly as they appear in the source — especially hair color, beard color, eyebrow color, \
and eye color — do not shift their hue, saturation, or warmth.
Subject: {{age_range}} {{gender_presentation}}, {{ethnicity_appearance}}, {{skin_tone}} \
skin with a {{skin_undertone}} undertone and natural skin texture (visible pores, subtle \
imperfections — not airbrushed).
Build: {{body_frame}} frame with {{shoulders}}, and a {{face_shape}} face.
Hair: {{hair_length}} {{hair_color}} hair, {{hair_style}}, {{hairline}}. Keep the natural \
hairline — do not lower, thicken, raise, or restyle it.
Facial hair: {{facial_hair}}.
Eyes: {{eye_color}}, {{eye_shape}}, {{eye_set}}, natural gaze.
Eyebrows: {{eyebrow_description}}.
Nose: {{nose_description}}.
Mouth: {{mouth_description}}.
Distinguishing features: {{distinguishing_features}}.
Expression baseline: {{expression}} — adjustable per scene, but the underlying facial \
structure must not change.
Avoid drifting from the source: {{identity_specific_negatives}}.
=== SCENE / STYLE (the only part you swap) ===
{{scene_block}}
Photorealistic result with natural skin; no beauty-filter or airbrushing, no warping of \
facial features, no added text, logos, or watermark."""

SCENE_TOKEN = "{{scene_block}}"


def build_identity_prompt(attrs: dict) -> str:
    """Fill the identity-lock template from extracted attributes.

    Every {{var}} except {{scene_block}} is replaced, so the returned string is a
    reusable base: swap {{scene_block}} per scene with `apply_scene`.
    """
    out = IDENTITY_TEMPLATE
    for key in ATTRIBUTE_KEYS:
        value = str(attrs.get(key) or "unspecified").strip()
        out = out.replace(f"{{{{{key}}}}}", value)

    negatives = attrs.get("identity_specific_negatives") or []
    if isinstance(negatives, str):
        negatives = [negatives]
    neg_text = ", ".join(n.strip() for n in negatives if str(n).strip()) or "none notable"
    out = out.replace("{{identity_specific_negatives}}", neg_text)
    return out


def apply_scene(base_prompt: str, scene_block: str) -> str:
    """Swap the scene/style block into a persisted identity-lock base prompt."""
    return base_prompt.replace(SCENE_TOKEN, scene_block.strip())


def look_scenes_for_environment(environment: str) -> list[dict]:
    """Two look scene blocks anchored to the first frame's own environment, so the
    avatar-card looks feel like the same person in their real space — one bright and
    one cinematic. Fed into the identity-lock prompt, then a first-frame image edit.
    """
    env = (environment or "a clean, softly lit modern interior").strip().rstrip(".")
    return [
        {
            "label": "Ambiente",
            "scene_block": (
                f"Half-body vertical 9:16 portrait of the same person in {env}. "
                "Bright, clean key lighting with soft shadows, looking at the camera, "
                "shallow depth of field, polished short-form video framing with space "
                "for captions, photorealistic."
            ),
        },
        {
            "label": "Cinematográfico",
            "scene_block": (
                f"Half-body vertical 9:16 portrait of the same person in {env}. "
                "Cinematic moody lighting with a subtle colored accent and soft backlight, "
                "slight three-quarter angle, bold and eye-catching short-form video look, "
                "shallow depth of field, photorealistic."
            ),
        },
    ]


# Default scene blocks for the 3 look options shown right after avatar creation.
LOOK_SCENES: list[dict] = [
    {
        "label": "Estúdio",
        "scene_block": (
            "Professional studio portrait on a smooth neutral charcoal backdrop, soft key "
            "light with a gentle rim light, shallow depth of field, half-body vertical 9:16 "
            "framing with space for captions, premium modern look, photorealistic."
        ),
    },
    {
        "label": "Escritório",
        "scene_block": (
            "Seated in a modern executive office with a softly blurred glass-wall city view, "
            "warm premium lighting, confident and approachable, half-body vertical 9:16 framing "
            "with space for captions, photorealistic."
        ),
    },
    {
        "label": "Cinematográfico",
        "scene_block": (
            "Cinematic lifestyle scene in a stylish dark studio with subtle blue LED accent "
            "lighting and strong backlight, shallow depth of field, bold and eye-catching, "
            "half-body vertical 9:16 framing with space for captions, photorealistic."
        ),
    },
]
