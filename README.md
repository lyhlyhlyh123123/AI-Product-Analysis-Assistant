# AI 产品分析助手

一个面向 Amazon 商品内容分析的网页工具。输入商品链接或粘贴商品描述后，系统会整理产品信息，生成中文产品分析和 150 字以内的口播文案，并可在配置 TTS 后生成口播音频。

## 功能

- 可选择 Firecrawl 抓取、本地抓取或手动复制粘贴作为信息获取方式。
- Amazon 商品链接输入和商品字段提取。
- 手动商品描述输入，适用于验证码、地区差异、反爬或字段缺失。
- 产品信息整理：标题、分类、价格、评分、评论数、图片、卖点、规格。
- 产品分析：目标用户、使用场景、用户痛点、核心卖点、内容角度。
- 150 字以内中文口播文案，开头包含钩子。
- 可选生成 TTS 口播音频。
- 静态单页前端，无需登录。

## 技术方案

- 后端：FastAPI + Pydantic。
- 工作流：LangGraph 编排产品信息整理、产品分析、口播文案和口播语音阶段。
- 抓取：Firecrawl SDK 或 `httpx` 请求 Amazon 页面，BeautifulSoup 按 DOM/metadata 规则提取字段。
- AI：DeepSeek Chat Completions API，可缺省回退到本地确定性中文分析。
- 语音：DashScope TTS 生成口播音频，未配置时跳过语音生成。
- 部署：Docker + Render Web Service。

## 本地启动

```bash
python -m pip install -r requirements.txt
uvicorn app.main:app --reload
```

打开：`http://127.0.0.1:8000`

开发检查：

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -v
```

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
```

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

返回包含 `task_id`、`product`、`analysis`、`short_video_script`、`tts_text` 和 `warnings`。

### `POST /api/generate-voice`

根据任务 ID、口播文本和已创建的音色生成口播音频。若未配置 DashScope，会返回明确 warning，不阻塞产品分析和文案生成。

## Docker

```bash
docker build -t ai-product-analysis .
docker run --rm -p 8000:8000 --env-file .env ai-product-analysis
``

## 使用检查

- 使用 Firecrawl 抓取一个 Amazon 商品链接，确认产品信息可以整理。
- 使用本地抓取模式检查 Amazon 页面可访问时的提取效果。
- 使用手动复制粘贴模式检查商品描述输入流程。
- 未配置 API Key 时，确认页面会显示明确提示，不阻塞基础流程。
- 配置 DashScope 后，确认口播音频可以生成并播放。

## 已知限制

- Amazon 可能出现验证码、反爬、地区差异或页面结构变化。
- 价格和库存会随地区、时间和账号状态变化。
- 有些商品页不会暴露完整规格。
- 本地兜底分析不等同于大模型质量，只保证主流程可用。
- 口播语音生成依赖 DashScope 配置和接口可用性。
- 真实凭据曾在对话中出现，发布或提交项目前建议到对应平台后台轮换一次密钥。
