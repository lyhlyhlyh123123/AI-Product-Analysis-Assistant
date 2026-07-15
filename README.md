# AI 产品分析助手

一个用于 AI 工程师实习生笔试题的 FastAPI 网页工具。输入 Amazon 商品链接后，系统提取商品信息，生成产品分析、150 字以内中文短视频口播文案，并可在配置 TTS 后尝试合成竖屏 MP4 商品短视频。

## 功能

- 可选择 Firecrawl 抓取、本地抓取或手动复制粘贴作为信息获取方式。
- Amazon 商品链接输入和商品字段提取。
- 手动商品描述输入，适用于验证码、地区差异、反爬或字段缺失。
- 产品信息整理：标题、分类、价格、评分、评论数、图片、卖点、规格。
- 产品分析：目标用户、使用场景、用户痛点、核心卖点、内容角度。
- 150 字以内中文短视频口播文案，开头包含钩子。
- 可选生成封面图、TTS 音频和竖屏 MP4。
- 静态单页前端，无需登录。

## 技术方案

- 后端：FastAPI + Pydantic。
- 工作流：LangGraph 编排产品信息整理、产品分析、口播文案和短视频生成阶段。
- 抓取：Firecrawl SDK 或 `httpx` 请求 Amazon 页面，BeautifulSoup 按 DOM/metadata 规则提取字段。
- AI：DeepSeek Chat Completions API，可缺省回退到本地确定性中文分析。
- TTS：DashScope，可缺省跳过。
- 视频：Pillow 生成竖屏封面，MoviePy/FFmpeg 在音频可用时合成 MP4。
- 部署：Docker + Render Web Service。

## 本地启动

```bash
python -m pip install -r requirements.txt
uvicorn app.main:app --reload
```

打开：`http://127.0.0.1:8000`

运行测试：

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -v
```

`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` 用于避免本机全局 pytest 插件影响项目测试。

## 环境变量

复制 `.env.example` 为 `.env` 后填入需要的配置。应用启动时会自动读取项目根目录的 `.env`；系统环境变量优先级更高。不要提交真实 `.env`。

```env
DEEPSEEK_API_KEY=
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat

FIRECRAWL_API_KEY=
FIRECRAWL_BASE_URL=https://api.firecrawl.dev

DASHSCOPE_API_KEY=
DASHSCOPE_BASE_URL=https://dashscope.aliyuncs.com/api/v1
DASHSCOPE_TTS_MODEL=cosyvoice-v1
DASHSCOPE_PREFERRED_VOICE_NAME=longxiaochun
DASHSCOPE_VOICE_ID=

VOLCENGINE_ARK_API_KEY=
VOLCENGINE_ARK_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
VOLCENGINE_ARK_IMAGE_MODEL=
VOLCENGINE_ARK_IMAGE_SIZE=2K
VOLCENGINE_ARK_DISABLE_WATERMARK=true
```

当前实现中 Volcengine Ark 配置预留给图片生成增强能力；没有配置时使用本地 Pillow 封面。

## API

### `POST /api/analyze`

请求：

```json
{
  "input_method": "firecrawl",
  "url": "https://www.amazon.com/dp/B0TEST1234",
  "manual_text": null
}
```

返回包含 `task_id`、`product`、`analysis`、`short_video_script`、`image_prompt`、`tts_text` 和 `warnings`。

### `POST /api/generate-video`

请求可直接使用 `/api/analyze` 的返回 JSON。若未配置 DashScope，会返回封面图 URL 和明确 warning，不阻塞主分析功能。

## Docker

```bash
docker build -t ai-product-analysis .
docker run --rm -p 8000:8000 --env-file .env ai-product-analysis
```

## Render 部署

1. 将仓库推送到 GitHub。
2. 在 Render 创建 Web Service，选择该仓库。
3. Runtime 选择 Docker。
4. 配置环境变量，至少建议配置 `DEEPSEEK_API_KEY`。
5. 部署完成后访问 Render 提供的 HTTPS URL。

Render 免费服务可能冷启动，首次访问可能需要等待几十秒。

## 验收建议

- 测试题目给出的两个 Amazon 链接。
- 再测试至少一个无关 Amazon 商品链接，确认不是硬编码。
- 测试手动商品描述兜底功能。
- 测试未配置 API Key 时的提示。
- 配置 DashScope 后测试 TTS 和 MP4 生成。
- 确认视频能在浏览器播放并可下载。

## 已知限制

- Amazon 可能出现验证码、反爬、地区差异或页面结构变化。
- 价格和库存会随地区、时间和账号状态变化。
- 有些商品页不会暴露完整规格。
- 本地兜底分析不等同于大模型质量，只保证主流程可用。
- 视频合成依赖 FFmpeg 和服务器 CPU，免费部署环境可能较慢。
- 真实凭据曾在对话中出现，发布或提交项目前建议到对应平台后台轮换一次密钥。
