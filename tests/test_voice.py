from app.config import Settings
from app.models import GenerateVoiceRequest
from app.services.voice import generate_voice_audio


class DummyResponse:
    def __init__(self, json_data=None, content=b""):
        self._json_data = json_data or {}
        self.content = content
        self.status_code = 200
        self.text = "ok"

    def json(self):
        return self._json_data

    def raise_for_status(self):
        return None


class DummyDashscopeResult:
    def __init__(self, data):
        self.output = data.get("output", {})

    def __getitem__(self, key):
        return {"output": self.output}[key]


def test_create_and_list_voice_profiles(monkeypatch, tmp_path):
    from app.models import CreateVoiceRequest
    from app.services.voices import create_voice_profile, list_voice_profiles

    post_calls = []

    def fake_post(url, json, headers, timeout):
        post_calls.append(json)
        return DummyResponse({"output": {"voice": "saved_voice_id"}})

    monkeypatch.setattr("app.services.voices.httpx.post", fake_post)
    settings = Settings(
        output_dir=tmp_path,
        dashscope_api_key="dashscope-key",
        dashscope_base_url="https://dashscope.aliyuncs.com/api/v1",
        dashscope_tts_model="qwen3-tts-vd-2026-01-26",
        dashscope_preferred_voice_name="custom_voice",
    )

    response = create_voice_profile(CreateVoiceRequest(name="活泼女声", prompt="年轻活泼的女性声音，语速偏快"), settings)

    assert response.profile.voice_id == "saved_voice_id"
    assert response.profile.name == "活泼女声"
    assert post_calls[0]["input"]["preferred_name"] == "custom_voice"
    assert list_voice_profiles(settings)[0].voice_id == "saved_voice_id"
    assert (tmp_path / "voices.json").exists()


def test_generate_voice_audio_uses_selected_voice_without_creating_new_one(monkeypatch, tmp_path):
    post_calls = []

    def fake_post(url, json, headers, timeout):
        post_calls.append((url, json, headers, timeout))
        return DummyResponse({"output": {"audio": {"url": "https://audio.example/voice.wav"}}})

    def fake_get(url, timeout):
        return DummyResponse(content=b"RIFFvoice")

    monkeypatch.setattr("app.services.voice.httpx.post", fake_post)
    monkeypatch.setattr("app.services.voice.httpx.get", fake_get)
    settings = Settings(output_dir=tmp_path, dashscope_api_key="dashscope-key", dashscope_tts_model="qwen3-tts-vd-2026-01-26")
    request = GenerateVoiceRequest(task_id="voice-test", text="测试文案", voice_id="saved_voice_id")

    response = generate_voice_audio(request, settings)

    assert response.audio_url == "/static/outputs/voice-test.wav"
    url, payload, headers, timeout = post_calls[0]
    assert url == "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"
    assert headers["Authorization"] == "Bearer dashscope-key"
    assert timeout == 60.0
    assert payload == {
        "model": "qwen3-tts-vd-2026-01-26",
        "input": {"text": "测试文案", "voice": "saved_voice_id"},
    }


def test_generate_voice_audio_saves_file_with_returned_audio_extension(monkeypatch, tmp_path):
    def fake_post(url, json, headers, timeout):
        return DummyResponse({"output": {"audio": {"url": "https://audio.example/voice.mp3?Expires=123"}}})

    def fake_get(url, timeout):
        return DummyResponse(content=b"ID3voice")

    monkeypatch.setattr("app.services.voice.httpx.post", fake_post)
    monkeypatch.setattr("app.services.voice.httpx.get", fake_get)
    settings = Settings(output_dir=tmp_path, dashscope_api_key="dashscope-key")
    request = GenerateVoiceRequest(task_id="voice-test", text="测试文案", voice_id="saved_voice_id", audio_format="wav")

    response = generate_voice_audio(request, settings)

    assert response.audio_url == "/static/outputs/voice-test.mp3"
    assert (tmp_path / "voice-test.mp3").read_bytes() == b"ID3voice"
    assert not (tmp_path / "voice-test.wav").exists()


def test_create_voice_profile_returns_warning_on_transport_or_json_failure(monkeypatch, tmp_path):
    from app.models import CreateVoiceRequest
    from app.services.voices import create_voice_profile

    settings = Settings(output_dir=tmp_path, dashscope_api_key="dashscope-key")
    monkeypatch.setattr("app.services.voices.httpx.post", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("network down")))

    transport_response = create_voice_profile(CreateVoiceRequest(name="活泼女声", prompt="年轻活泼的女性声音"), settings)

    assert transport_response.profile is None
    assert any("network down" in warning for warning in transport_response.warnings)

    class BadJsonResponse(DummyResponse):
        def json(self):
            raise ValueError("not json")

    monkeypatch.setattr("app.services.voices.httpx.post", lambda *args, **kwargs: BadJsonResponse())

    json_response = create_voice_profile(CreateVoiceRequest(name="活泼女声", prompt="年轻活泼的女性声音"), settings)

    assert json_response.profile is None
    assert any("not json" in warning for warning in json_response.warnings)


def test_ad_hoc_voice_creation_uses_readable_profile_name(monkeypatch, tmp_path):
    from app.services.voices import create_voice_profile

    captured = {}

    def fake_create_voice_profile(request, settings):
        captured["name"] = request.name
        return create_voice_profile(request, settings)

    def fake_post(url, json, headers, timeout):
        if url.endswith("/services/audio/tts/customization"):
            return DummyResponse({"output": {"voice": "generated_voice_id"}})
        if url.endswith("/services/aigc/multimodal-generation/generation"):
            return DummyResponse({"output": {"audio": {"url": "https://audio.example/voice.wav"}}})
        raise AssertionError(f"unexpected URL: {url}")

    monkeypatch.setattr("app.services.voices.httpx.post", fake_post)
    monkeypatch.setattr("app.services.voice.httpx.post", fake_post)
    monkeypatch.setattr("app.services.voice.create_voice_profile", fake_create_voice_profile)
    monkeypatch.setattr("app.services.voice.httpx.get", lambda *args, **kwargs: DummyResponse(content=b"RIFFvoice"))
    settings = Settings(output_dir=tmp_path, dashscope_api_key="dashscope-key", dashscope_preferred_voice_name="custom_voice")
    request = GenerateVoiceRequest(task_id="voice-test", text="测试文案", voice="年轻活泼女声", voice_instruction="年轻活泼的女性声音")

    generate_voice_audio(request, settings)

    assert captured["name"] == "年轻活泼女声"


def test_generate_voice_audio_creates_designed_voice_and_saves_audio(monkeypatch, tmp_path):
    post_calls = []
    synthesis_calls = []

    def fake_post(url, json, headers, timeout):
        if url.endswith("/services/audio/tts/customization"):
            post_calls.append((url, json, headers, timeout))
            return DummyResponse({"output": {"voice": "generated_voice_id"}})
        if url.endswith("/services/aigc/multimodal-generation/generation"):
            synthesis_calls.append((url, json, headers, timeout))
            return DummyResponse({"output": {"audio": {"url": "https://audio.example/voice.wav"}}})
        raise AssertionError(f"unexpected URL: {url}")

    def fake_get(url, timeout):
        assert url == "https://audio.example/voice.wav"
        assert timeout == 60.0
        return DummyResponse(content=b"RIFFvoice")

    monkeypatch.setattr("app.services.voice.httpx.post", fake_post)
    monkeypatch.setattr("app.services.voice.httpx.get", fake_get)
    settings = Settings(
        output_dir=tmp_path,
        dashscope_api_key="dashscope-key",
        dashscope_base_url="https://dashscope.aliyuncs.com/api/v1",
        dashscope_tts_model="qwen3-tts-vd-2026-01-26",
        dashscope_preferred_voice_name="custom_voice",
    )
    request = GenerateVoiceRequest(
        task_id="voice-test",
        text="这款便携榨汁杯适合通勤和旅行。",
        voice="longanlingxi",
        voice_instruction="年轻活泼的女性声音，语速偏快",
        audio_format="wav",
        sample_rate=24000,
    )

    response = generate_voice_audio(request, settings)

    assert response.audio_url == "/static/outputs/voice-test.wav"
    assert response.remote_audio_url == "https://audio.example/voice.wav"
    assert (tmp_path / "voice-test.wav").read_bytes() == b"RIFFvoice"
    url, payload, headers, timeout = post_calls[0]
    assert url == "https://dashscope.aliyuncs.com/api/v1/services/audio/tts/customization"
    assert headers["Authorization"] == "Bearer dashscope-key"
    assert timeout == 60.0
    assert payload["model"] == "qwen-voice-design"
    assert payload["input"]["action"] == "create"
    assert payload["input"]["target_model"] == "qwen3-tts-vd-2026-01-26"
    assert payload["input"]["preferred_name"] == "custom_voice"
    assert payload["input"]["voice_prompt"] == "年轻活泼的女性声音，语速偏快"
    assert payload["parameters"] == {"sample_rate": 24000, "response_format": "wav"}
    synthesis_url, synthesis_payload, synthesis_headers, synthesis_timeout = synthesis_calls[0]
    assert synthesis_url == "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"
    assert synthesis_headers["Authorization"] == "Bearer dashscope-key"
    assert synthesis_timeout == 60.0
    assert synthesis_payload == {
        "model": "qwen3-tts-vd-2026-01-26",
        "input": {"text": "这款便携榨汁杯适合通勤和旅行。", "voice": "generated_voice_id"},
    }


def test_generate_voice_audio_returns_voice_design_error_body(monkeypatch, tmp_path):
    class ErrorResponse(DummyResponse):
        status_code = 400
        text = '{"code":"InvalidParameter","message":"voice_prompt is invalid"}'

        def __init__(self):
            super().__init__({"code": "InvalidParameter", "message": "voice_prompt is invalid"})
            self.status_code = 400
            self.text = '{"code":"InvalidParameter","message":"voice_prompt is invalid"}'

    monkeypatch.setattr("app.services.voice.httpx.post", lambda *args, **kwargs: ErrorResponse())
    settings = Settings(
        output_dir=tmp_path,
        dashscope_api_key="dashscope-key",
        dashscope_base_url="https://dashscope.aliyuncs.com/api/v1",
        dashscope_tts_model="qwen3-tts-vd-2026-01-26",
    )
    request = GenerateVoiceRequest(task_id="voice-test", text="测试文案", voice_instruction="")

    response = generate_voice_audio(request, settings)

    assert response.audio_url == ""
    assert any("InvalidParameter" in warning for warning in response.warnings)
    assert any("voice_prompt is invalid" in warning for warning in response.warnings)
