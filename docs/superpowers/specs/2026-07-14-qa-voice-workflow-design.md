# QA and Voice Workflow Design

## Goal

Add two quality-assurance checkpoints to the staged Amazon product-analysis workflow so generated content is less likely to contain factual errors, unsupported claims, or exaggerated descriptions. Replace the video-generation stage with a voiceover-audio stage using DashScope/Qwen TTS.

## Workflow

The dashboard workflow becomes:

1. Product input
2. Product information extraction
3. Product information QA
4. Product analysis
5. Product analysis QA
6. Short-video voiceover script
7. Voiceover audio
8. History records

QA checkpoints run automatically in the backend before the next generation stage proceeds.

## QA Rules

Both QA checkpoints check the generated content against available product evidence.

Product information QA checks:

- Product facts such as title, category, price, rating, review count, features, and specifications must come from extracted page data or manual text.
- Chinese localized product information must not introduce features that are absent from the original evidence.
- Missing facts must stay `unknown` instead of being inferred.
- Unsupported superlatives and absolute claims are rejected.

Product analysis QA checks:

- Target users, scenarios, pain points, selling points, and content angles must be grounded in product facts or visible page text.
- Claims with no evidence are flagged.
- Exaggerated wording such as guaranteed results, best-in-class claims, medical/safety promises, or certainty beyond the source material is rejected.
- Analysis entries should carry evidence text or product-field references so the user can trace why the analysis is credible.

## Retry Behavior

Each QA checkpoint can retry the previous generation step automatically up to three times.

- Attempt 1: run QA normally.
- Attempt 2: regenerate with QA issues as correction guidance.
- Attempt 3: regenerate with stricter instruction to remove unsupported or exaggerated claims.
- After three failed attempts: stop the workflow stage and return `manual_review` with QA issues and rewrite guidance.

Manual review does not discard saved records. The record stores the latest generated content, QA report, and warnings so the user can inspect or retry later.

## Data Model

Add `QAResult`:

- `stage`: `product_info` or `analysis`
- `status`: `passed`, `retrying`, or `manual_review`
- `passed`: boolean
- `attempts`: number
- `issues`: list of issue strings
- `unsupported_claims`: list of strings
- `exaggerated_claims`: list of strings
- `missing_evidence`: list of strings
- `rewrite_guidance`: string

Add `EvidenceItem` for traceability in product analysis:

- `claim`: generated analysis item
- `evidence`: source phrase, product field, or visible text excerpt
- `source`: `product`, `localized_product`, `visible_text`, `manual`, or `qa`

Keep existing product and script response contracts where possible, and add optional QA/evidence fields so existing calls remain compatible.

## API Changes

Add two staged endpoints:

- `POST /api/qa-product-info`
- `POST /api/qa-analysis`

Existing endpoints remain:

- `POST /api/extract-product`
- `POST /api/analyze-product`
- `POST /api/generate-script`

Replace video with voiceover audio:

- Keep `/api/generate-video` only as a backward-compatible wrapper if needed.
- Add `POST /api/generate-voice` for the new dashboard stage.

## Voiceover Audio

The former video stage becomes a voiceover-audio stage. It sends the generated script text to DashScope/Qwen TTS:

- model: default `qwen-audio-3.0-tts-flash`
- endpoint: `https://{WorkspaceId}.cn-beijing.maas.aliyuncs.com/api/v1/services/audio/tts/SpeechSynthesizer`
- default voice: `longanlingxi`
- default format: `wav`
- default sample rate: `24000`

The UI lets the user configure:

- voice id
- voice instruction/description
- audio format
- sample rate

DashScope non-streaming responses contain an audio URL valid for 24 hours. To preserve artifacts in history records, the backend downloads the audio URL into local `outputs` and stores the local URL in the record. If downloading fails, the response keeps the remote URL with a warning about expiration.

## Frontend

Sidebar changes:

- Rename `带货短视频` to `口播语音`.
- Add QA state display between product info and product analysis, and between product analysis and script.
- If QA passes, show a pass summary.
- If QA retries, show attempts and latest issues.
- If QA reaches manual review, show issues and rewrite guidance, plus a retry button.

The analysis page should show traceability by rendering evidence text under analysis items where available.

## Persistence

Saved records store:

- product response
- product QA response
- analysis response with evidence
- analysis QA response
- script response
- voice response

History records show whether QA passed, needs manual review, and whether voice audio exists.

## Testing

Add tests for:

- QA rejects unsupported or exaggerated claims.
- QA retry stops after three failed attempts and marks manual review.
- Product analysis includes evidence references.
- Voice generation calls DashScope/Qwen TTS endpoint with user-configurable voice settings.
- Voice artifacts are saved locally when the remote URL is returned.
- Frontend sidebar uses `口播语音` and no longer exposes video generation as the main stage.
