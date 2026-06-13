import types

from doppel_api.providers import script


def _fake_response(input_dict: dict):
    block = types.SimpleNamespace(type="tool_use", input=input_dict)
    return types.SimpleNamespace(content=[block])


async def test_build_script_returns_tool_input(monkeypatch):
    captured = {}
    expected = {
        "narration": {"text": "Olá, hoje falamos de seguranca.", "tone": "confiante"},
        "scenes": [
            {"id": "s1", "start": 0.0, "end": 10.0, "type": "avatar"},
            {"id": "s2", "start": 10.0, "end": 20.0, "type": "broll",
             "prompt": "cofre digital", "motion": "camera lenta aproximando"},
            {"id": "s3", "start": 20.0, "end": 30.0, "type": "avatar"},
        ],
        "captions": {"style": "tiktok"},
    }

    class FakeMessages:
        def create(self, **kwargs):
            captured.update(kwargs)
            return _fake_response(expected)

    class FakeClient:
        messages = FakeMessages()

    monkeypatch.setattr(script, "_client", lambda: FakeClient())
    result = await script.build_script("quero um video sobre seguranca digital", 10)
    assert result == expected
    assert captured["model"] == "claude-sonnet-4-6"
    assert captured["tool_choice"] == {"type": "tool", "name": "emit_script"}
    assert "seguranca digital" in captured["messages"][0]["content"]
    assert "10" in captured["system"]
