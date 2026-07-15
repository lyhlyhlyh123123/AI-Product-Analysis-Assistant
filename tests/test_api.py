from fastapi.testclient import TestClient

from app.config import Settings
from app.main import app
from app.services import storage


client = TestClient(app)


def use_temp_settings(monkeypatch, tmp_path):
    settings = Settings(output_dir=tmp_path)
    monkeypatch.setattr("app.services.ai.Settings.from_env", lambda: settings)
    monkeypatch.setattr("app.services.media.Settings.from_env", lambda: settings)
    monkeypatch.setattr("app.services.storage.Settings.from_env", lambda: settings)
    monkeypatch.setattr("app.services.voice.Settings.from_env", lambda: settings)
    monkeypatch.setattr("app.services.voices.Settings.from_env", lambda: settings)
    return settings


def test_health():
    assert client.get("/health").json()["status"] == "ok"


def test_analyze_accepts_manual_text_without_network(monkeypatch, tmp_path):
    settings = use_temp_settings(monkeypatch, tmp_path)
    response = client.post(
        "/api/analyze",
        json={"input_method": "manual", "manual_text": "Portable Blender USB rechargeable 500ml"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["task_id"]
    assert data["short_video_script"]["word_count"] <= 150

    record = storage.load_result_record(data["task_id"], settings.output_dir)
    assert record["source_url"] == "manual://input"
    assert record["analysis_response"]["task_id"] == data["task_id"]
    assert record["video_response"] is None

    saved_response = client.get(f"/api/results/{data['task_id']}")
    assert saved_response.status_code == 200
    assert saved_response.json()["analysis_response"]["product"]["title"]["value"]


def test_generate_video_updates_saved_record(monkeypatch, tmp_path):
    settings = use_temp_settings(monkeypatch, tmp_path)
    analyze_response = client.post(
        "/api/analyze",
        json={"input_method": "manual", "manual_text": "Portable Blender USB rechargeable 500ml"},
    )
    data = analyze_response.json()

    response = client.post("/api/generate-video", json=data)

    assert response.status_code == 200
    video_data = response.json()
    assert video_data["warnings"]
    record = storage.load_result_record(data["task_id"], settings.output_dir)
    assert record["video_response"]["image_url"].endswith(".png")


def test_staged_workflow_saves_each_result(monkeypatch, tmp_path):
    settings = use_temp_settings(monkeypatch, tmp_path)
    extract_response = client.post(
        "/api/extract-product",
        json={"input_method": "manual", "manual_text": "Portable Blender\nUSB rechargeable\n500ml"},
    )
    assert extract_response.status_code == 200
    product_data = extract_response.json()
    assert product_data["product"]["title"]["value"] == "Portable Blender"
    assert product_data["extraction_method"] == "manual"
    assert product_data["localized_product"]["title"]

    analysis_response = client.post("/api/analyze-product", json=product_data)
    assert analysis_response.status_code == 200
    analysis_data = analysis_response.json()
    assert analysis_data["product_qa"]["passed"] is True
    assert analysis_data["analysis"]["selling_points"]
    assert analysis_data["evidence"]

    script_response = client.post("/api/generate-script", json=analysis_data)
    assert script_response.status_code == 200
    script_data = script_response.json()
    assert script_data["analysis_qa"]["passed"] is True
    assert script_data["short_video_script"]["script"]
    assert script_data["short_video_script"]["word_count"] <= 150

    voice_response = client.post("/api/generate-voice", json={"task_id": script_data["task_id"], "text": script_data["tts_text"] or script_data["short_video_script"]["script"]})
    assert voice_response.status_code == 200

    record = storage.load_result_record(product_data["task_id"], settings.output_dir)
    assert record["product_response"]["task_id"] == product_data["task_id"]
    assert record["product_response"]["localized_product"]["title"]
    assert record["product_qa_response"]["passed"] is True
    assert record["stage_analysis_response"]["task_id"] == product_data["task_id"]
    assert record["analysis_qa_response"]["passed"] is True
    assert record["script_response"]["task_id"] == product_data["task_id"]
    assert record["voice_response"] is not None

    records_response = client.get("/api/results")
    assert records_response.status_code == 200
    records = records_response.json()["records"]
    assert any(item["task_id"] == product_data["task_id"] for item in records)

    delete_response = client.delete(f"/api/results/{product_data['task_id']}")
    assert delete_response.status_code == 200
    assert storage.load_result_record(product_data["task_id"], settings.output_dir) is None
    assert client.get(f"/api/results/{product_data['task_id']}").status_code == 404


def test_voice_profile_api_creates_and_lists_profiles(monkeypatch, tmp_path):
    settings = Settings(output_dir=tmp_path, dashscope_api_key="dashscope-key")
    monkeypatch.setattr("app.services.voices.Settings.from_env", lambda: settings)

    class DummyResponse:
        status_code = 200
        text = "ok"

        def json(self):
            return {"output": {"voice": "api_voice_id"}}

    monkeypatch.setattr("app.services.voices.httpx.post", lambda *args, **kwargs: DummyResponse())

    create_response = client.post("/api/voices", json={"name": "活泼女声", "prompt": "年轻活泼的女性声音，语速偏快"})
    list_response = client.get("/api/voices")

    assert create_response.status_code == 200
    assert create_response.json()["profile"]["voice_id"] == "api_voice_id"
    assert list_response.status_code == 200
    assert list_response.json()[0]["voice_id"] == "api_voice_id"


def test_generate_video_returns_warning_when_tts_unconfigured(monkeypatch, tmp_path):
    use_temp_settings(monkeypatch, tmp_path)
    response = client.post(
        "/api/generate-video",
        json={"task_id": "abc", "product": {}, "analysis": {}, "short_video_script": {"script": "测试文案"}},
    )
    assert response.status_code == 200
    assert response.json()["warnings"]


def test_record_summary_treats_legacy_video_audio_as_voice(monkeypatch, tmp_path):
    settings = use_temp_settings(monkeypatch, tmp_path)
    storage._update_record("legacy-audio", settings, source_url="https://www.amazon.com/dp/B0TEST1234", video_response={"audio_url": "/static/outputs/legacy-audio.mp3"})

    records = storage.list_result_records(settings.output_dir)

    legacy = next(item for item in records if item["task_id"] == "legacy-audio")
    assert legacy["has_voice"] is True


def test_saved_result_rejects_invalid_task_id():
    response = client.get("/api/results/../secret")
    assert response.status_code in {400, 404}
