# Importers/callers: pytest collects this file to verify app.config.Settings behavior.
# Affected API: no runtime API changes; tests cover .env loading and environment override precedence.
# Data schemas: no Pydantic or saved-record schema changes.
# User instruction: "为什么apikey还没有配好 env.example里已经写好了，同时侧边栏无法点击切换查看，不同的产物到不同的侧边拦页面"

from app.config import Settings


def test_settings_reads_dotenv_file(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    (tmp_path / ".env").write_text("DEEPSEEK_API_KEY=from-dotenv\nOUTPUT_DIR=custom-output\n", encoding="utf-8")

    settings = Settings.from_env()

    assert settings.deepseek_api_key == "from-dotenv"
    assert str(settings.output_dir) == "custom-output"


def test_environment_variables_override_dotenv(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "from-env")
    (tmp_path / ".env").write_text("DEEPSEEK_API_KEY=from-dotenv\n", encoding="utf-8")

    settings = Settings.from_env()

    assert settings.deepseek_api_key == "from-env"
