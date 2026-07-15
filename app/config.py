from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


@dataclass(frozen=True)
class Settings:
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"
    firecrawl_api_key: str = ""
    firecrawl_base_url: str = "https://api.firecrawl.dev"
    dashscope_api_key: str = ""
    dashscope_base_url: str = "https://dashscope.aliyuncs.com/api/v1"
    dashscope_tts_model: str = "qwen3-tts-vd-2026-01-26"
    dashscope_preferred_voice_name: str = "custom_voice"
    dashscope_voice_id: str = ""
    volcengine_ark_api_key: str = ""
    volcengine_ark_base_url: str = "https://ark.cn-beijing.volces.com/api/v3"
    volcengine_ark_image_model: str = ""
    volcengine_ark_image_size: str = "2K"
    volcengine_ark_disable_watermark: bool = True
    output_dir: Path = Path("app/static/outputs")

    @classmethod
    def from_env(cls) -> "Settings":
        env_file = _load_dotenv(Path(".env"))

        def value(name: str, default: str = "") -> str:
            return os.getenv(name) or env_file.get(name) or default

        return cls(
            deepseek_api_key=value("DEEPSEEK_API_KEY"),
            deepseek_base_url=value("DEEPSEEK_BASE_URL", cls.deepseek_base_url),
            deepseek_model=value("DEEPSEEK_MODEL", cls.deepseek_model),
            firecrawl_api_key=value("FIRECRAWL_API_KEY"),
            firecrawl_base_url=value("FIRECRAWL_BASE_URL", cls.firecrawl_base_url),
            dashscope_api_key=value("DASHSCOPE_API_KEY"),
            dashscope_base_url=value("DASHSCOPE_BASE_URL", cls.dashscope_base_url),
            dashscope_tts_model=value("DASHSCOPE_TTS_MODEL", cls.dashscope_tts_model),
            dashscope_preferred_voice_name=value("DASHSCOPE_PREFERRED_VOICE_NAME", cls.dashscope_preferred_voice_name),
            dashscope_voice_id=value("DASHSCOPE_VOICE_ID"),
            volcengine_ark_api_key=value("VOLCENGINE_ARK_API_KEY"),
            volcengine_ark_base_url=value("VOLCENGINE_ARK_BASE_URL", cls.volcengine_ark_base_url),
            volcengine_ark_image_model=value("VOLCENGINE_ARK_IMAGE_MODEL"),
            volcengine_ark_image_size=value("VOLCENGINE_ARK_IMAGE_SIZE", cls.volcengine_ark_image_size),
            volcengine_ark_disable_watermark=value("VOLCENGINE_ARK_DISABLE_WATERMARK", "true").lower() != "false",
            output_dir=Path(value("OUTPUT_DIR", str(cls.output_dir))),
        )

    @property
    def has_deepseek(self) -> bool:
        return bool(self.deepseek_api_key)

    @property
    def has_dashscope_tts(self) -> bool:
        return bool(self.dashscope_api_key)

    @property
    def has_ark_image(self) -> bool:
        return bool(self.volcengine_ark_api_key and self.volcengine_ark_image_model)


def _load_dotenv(path: Path) -> Mapping[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, raw_value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        values[key] = raw_value.strip().strip('"').strip("'")
    return values
