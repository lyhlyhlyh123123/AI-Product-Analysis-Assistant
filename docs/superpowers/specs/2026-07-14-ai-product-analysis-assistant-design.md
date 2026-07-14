# AI 产品分析助手设计文档

## 目标

构建一个可公网访问的 FastAPI 网页小工具，用于完成 AI 工程师实习生笔试题。用户输入 Amazon 商品链接后，系统自动提取商品信息，生成产品分析、中文短视频口播文案，并可合成一个竖屏 MP4 商品短视频。

最终交付需要包含：

- 公网部署链接，任何人可直接访问，不需要登录。
- GitHub 仓库链接。
- README，说明项目功能、启动方式、部署方式、环境变量和已知限制。

## 产品范围

### 必须完成

- 支持输入 Amazon 商品链接。
- 从商品页面提取商品信息。
- 生成产品信息整理结果。
- 生成产品分析，包括目标用户、使用场景、用户痛点、核心卖点和内容角度。
- 生成 150 字以内中文短视频口播文案。
- 文案前 5 秒必须有吸引用户继续观看的钩子。
- 页面能正常展示分析结果。
- 项目能部署成公网 HTTPS 服务。

### 加分功能

- 根据口播文案生成中文 TTS 音频。
- 根据商品图或图片生成接口生成短视频视觉图。
- 将商品图/生成图、TTS 音频、字幕、卖点卡片合成为 15-30 秒竖屏 MP4 短视频。

### 失败边界

- 商品分析和口播文案是主流程，必须尽量保证可用。
- TTS、图片生成、视频合成属于增强能力，失败时不能影响主分析结果展示。
- 如果 Amazon 页面因为验证码、地区差异、反爬或字段缺失导致抓取失败，页面提供“手动粘贴商品描述”的兜底输入，仍然可以生成分析和文案。

## 总体架构

```text
浏览器页面
  -> FastAPI 后端
      -> Crawlee/Playwright 抓取 Amazon 页面
      -> HTML 解析与字段归一化
      -> DeepSeek 生成产品分析和口播文案
      -> 阿里 DashScope 生成 TTS 音频
      -> 火山 Ark 生成图片或封面图
      -> MoviePy/FFmpeg 合成 MP4 视频
      -> 静态目录提供输出文件访问
```

推荐技术栈：

- 后端：Python 3.11、FastAPI、Uvicorn。
- 抓取：Crawlee for Python + Playwright + Chromium。
- HTML 解析：BeautifulSoup 或 selectolax。
- AI 分析：DeepSeek API。
- TTS：阿里 DashScope TTS。
- 图片生成：火山 Ark 图片模型。
- 视频合成：MoviePy + FFmpeg + Pillow。
- 部署：Docker + Render Web Service。

## 后端接口设计

```text
GET  /                         # 前端页面
GET  /health                   # 健康检查
POST /api/analyze              # 抓取 + 解析 + AI 分析 + 口播文案
POST /api/generate-video       # TTS + 图片选择/生成 + MP4 合成
GET  /static/outputs/<file>    # 访问生成的音频、图片、视频文件
```

### `POST /api/analyze`

请求示例：

```json
{
  "url": "https://www.amazon.com/dp/...",
  "manual_text": "可选，抓取失败时手动粘贴的商品描述"
}
```

响应示例：

```json
{
  "task_id": "uuid",
  "product": {
    "title": {"value": "", "source": "dom|metadata|ai|manual|unknown", "confidence": "high|medium|low"},
    "category": {"value": "", "source": "dom|metadata|ai|manual|unknown", "confidence": "high|medium|low"},
    "price": {"value": "", "source": "dom|metadata|ai|manual|unknown", "confidence": "high|medium|low"},
    "rating": {"value": "", "source": "dom|metadata|ai|manual|unknown", "confidence": "high|medium|low"},
    "review_count": {"value": "", "source": "dom|metadata|ai|manual|unknown", "confidence": "high|medium|low"},
    "main_image_url": "",
    "image_candidates": [],
    "core_features": [],
    "specifications": {}
  },
  "analysis": {
    "target_users": [],
    "use_scenarios": [],
    "pain_points": [],
    "selling_points": [],
    "content_angles": []
  },
  "short_video_script": {
    "hook": "",
    "script": "",
    "word_count": 0
  },
  "image_prompt": "",
  "tts_text": "",
  "warnings": []
}
```

### `POST /api/generate-video`

请求示例：

```json
{
  "task_id": "uuid",
  "product": {},
  "analysis": {},
  "short_video_script": {},
  "image_prompt": "",
  "tts_text": ""
}
```

响应示例：

```json
{
  "video_url": "/static/outputs/<task_id>.mp4",
  "audio_url": "/static/outputs/<task_id>.mp3",
  "image_url": "/static/outputs/<task_id>.png",
  "warnings": []
}
```

## 抓取与字段提取设计

使用 Crawlee/Playwright 作为开源抓取底座。不要把某个 Amazon 专用 GitHub 爬虫库作为核心依赖，因为很多这类项目只是封装固定选择器，维护不稳定，Amazon 页面结构变化后容易失效。

抓取流程：

1. 校验输入 URL 是否属于支持的 Amazon 域名。
2. 使用 Crawlee 调用 Playwright/Chromium 打开页面。
3. 设置常见浏览器请求头、英文语言偏好和超时时间。
4. 等待页面加载完成，获取渲染后的 HTML。
5. 提取页面可见文本，作为兜底信息。
6. 从 HTML 和 metadata 中解析结构化字段。

字段提取策略：

1. 先做确定性规则提取：
   - 标题：`#productTitle`、`og:title`。
   - 主图：`#landingImage`、`data-a-dynamic-image`、`og:image`。
   - 价格：`.a-price`、`priceblock` 相关区域。
   - 卖点：`#feature-bullets`。
   - 评分和评论数：`#acrPopover`、页面中的 rating 文本。
   - 规格：商品详情表、detail bullets、product information 区域。
2. 如果字段不完整，清洗页面可见文本。
3. 将已提取字段和页面文本交给 DeepSeek 做结构化补全。
4. 无法确认的事实字段写 `unknown`，不编造。
5. 关键字段保留来源和置信度，方便前端提示。

图片提取优先级：

1. 解析 `data-a-dynamic-image` 中的多尺寸图片候选。
2. 读取 `#landingImage` 的 `src` 或 `data-old-hires`。
3. 读取 `og:image`。
4. 从页面结构化数据或脚本中兜底提取图片。

## AI 分析设计

DeepSeek 用于结构化分析和文案生成，不负责直接抓网页。后端先整理出紧凑的商品证据对象，再提示模型输出严格 JSON。

生成约束：

- 事实字段只能基于抓取到的商品证据。
- 页面没有的信息写 `unknown`。
- 产品分析可以合理推断目标用户、场景、痛点和内容角度，但必须围绕商品信息展开。
- 中文口播文案不超过 150 字。
- 文案开头必须有吸引用户继续看的钩子。
- 文案应该像短视频口播，不是普通商品说明书。

DeepSeek 返回内容按 JSON 解析。如果解析失败，后端尝试修复一次。如果仍失败，返回清晰错误信息；开发环境可以保留原始模型输出用于排查，生产页面不展示长调试文本。

## TTS、图片和视频合成设计

### TTS

配置阿里 DashScope TTS 后，系统用 `tts_text` 或最终口播文案生成音频文件，并保存到 `static/outputs/`。

如果 DashScope 环境变量缺失，隐藏或禁用依赖 TTS 的视频生成能力，或者返回明确的配置错误。

### 图片

商品主图是最可靠的视觉来源。若火山 Ark 图片生成配置完整且调用成功，可使用生成图作为封面或背景；如果图片生成失败，自动回退到商品主图。

### 视频合成

使用 MoviePy 和 FFmpeg 生成竖屏 MP4。

视频格式：

- 分辨率：1080x1920。
- 目标时长：根据 TTS 音频长度自动决定，控制在 15-30 秒左右。
- 视频结构：
  1. 钩子场景：商品图 + 钩子字幕。
  2. 卖点场景：2-3 个核心卖点卡片。
  3. 场景/收尾：使用场景或购买理由。
- 字幕：按中文标点切分口播文案，并根据音频时长均匀分配出现时间。
- 动效：简单缩放、平移和淡入淡出。
- 输出：`/static/outputs/<task_id>.mp4`。

这是确定性视频合成，不是 AI 视频生成。这样更稳定，部署和测试风险更低。

## 前端页面设计

前端做成单页工具，不做营销落地页，也不做复杂后台。

页面区域：

- 输入区：Amazon 商品链接 + 可选手动商品描述。
- 状态区：抓取中、分析中、生成音频中、生成视频中。
- 商品卡片：主图、标题、价格、评分、规格。
- 产品分析：目标用户、使用场景、用户痛点、核心卖点、内容角度。
- 口播文案：钩子 + 完整 150 字以内中文文案。
- 视频结果：MP4 播放器 + 下载按钮。
- 质量提示：缺失字段、字段来源、置信度、警告信息。

交互流程：

1. 用户点击“分析商品”。
2. 页面展示商品信息、产品分析和口播文案。
3. 用户点击“生成短视频”。
4. 视频生成完成后，页面展示播放器和下载链接。

采用两步式流程，是为了让用户先看到核心分析结果，不必一开始就等待视频合成完成。

## 安全与配置

真实 API Key 不能提交到 GitHub。

只通过环境变量读取配置：

```env
DEEPSEEK_API_KEY=
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=

DASHSCOPE_API_KEY=
DASHSCOPE_BASE_URL=https://dashscope.aliyuncs.com/api/v1
DASHSCOPE_TTS_MODEL=
DASHSCOPE_PREFERRED_VOICE_NAME=
DASHSCOPE_VOICE_ID=

VOLCENGINE_ARK_API_KEY=
VOLCENGINE_ARK_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
VOLCENGINE_ARK_IMAGE_MODEL=
VOLCENGINE_ARK_IMAGE_SIZE=2K
VOLCENGINE_ARK_DISABLE_WATERMARK=true
```

仓库中只提交 `.env.example`，里面放占位值，不放真实密钥。

由于真实凭据曾在对话中出现，发布或提交项目前建议到对应平台后台轮换一次密钥。

## 部署设计

使用 Docker 部署到 Render Web Service，生成公开 HTTPS 链接。

Docker 需要安装：

- Python 依赖。
- Playwright Chromium 和系统依赖。
- FFmpeg。

预期部署结果：

```text
https://<service-name>.onrender.com
```

README 需要说明 Render 免费服务可能冷启动，首次访问可能需要等待几十秒。

## 测试与验收

手动验收：

- 测试题目给出的两个 Amazon 链接。
- 再测试至少一个无关 Amazon 商品链接，证明不是硬编码。
- 测试手动商品描述兜底功能。
- 测试可选 API 配置缺失时的提示。
- 测试 TTS 和 MP4 生成。
- 确认视频能在浏览器播放，并能下载。

自动化测试建议覆盖：

- Amazon URL 校验。
- 商品字段归一化。
- `data-a-dynamic-image` 图片候选提取。
- AI JSON 解析和修复兜底。
- 口播文案长度校验。
- 视频合成辅助函数。

## 已知限制

- Amazon 可能出现验证码、反爬、地区差异或页面结构变化。
- 价格和库存会随地区、时间和账号状态变化。
- 有些商品页可能不会暴露完整规格。
- AI 可以推断用户、场景和痛点，但不能编造事实性商品参数。
- 视频合成依赖 FFmpeg 和服务器 CPU，免费部署环境可能较慢。
- Render 免费服务可能冷启动，首次访问速度较慢。

## GitHub 提交范围建议

应该提交：

- 源代码。
- `README.md`。
- `requirements.txt`、`Dockerfile` 等部署文件。
- `.env.example`。
- `docs/superpowers/specs/2026-07-14-ai-product-analysis-assistant-design.md`。

不建议提交：

- 原始笔试 PDF：`AI工程师实习生笔试题.pdf`。
- 从 PDF 渲染出来的临时图片：`ai_exam_page-*.png`。
- 真实 `.env` 或任何包含 API Key 的文件。
- 生成的视频、音频、图片：`static/outputs/`。
- Python 缓存、虚拟环境、浏览器缓存、日志文件。

## 提交前检查清单

- 公网部署链接无需登录即可访问。
- GitHub 仓库可供评审访问。
- README 包含启动方式、部署方式、环境变量、技术方案、已知限制和演示步骤。
- `.env.example` 存在且不含真实密钥。
- 没有提交真实 API Key。
- 可选录屏展示：输入 Amazon 链接、生成分析结果、生成 MP4 视频。
