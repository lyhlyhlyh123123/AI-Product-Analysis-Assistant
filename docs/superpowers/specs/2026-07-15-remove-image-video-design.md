# Remove Image And Video Design

## Goal

Remove stale image and video generation surfaces so the app only presents product extraction, product analysis, oral script generation, and oral voice generation.

## Scope

- Remove `image_prompt` from AI prompts, response models, storage payloads, and frontend assumptions.
- Remove `/api/generate-video` and its request/response models.
- Remove unused media/video generation service code from the active app surface.
- Remove frontend video/cover controls and state while preserving voice generation.
- Update tests and docs to reflect voice-only output.

## Out Of Scope

- Do not add script QA.
- Do not change product extraction, analysis QA, or voice generation behavior.
- Do not remove product image extraction fields such as `main_image_url`; they are product evidence, not generated image/video output.

## Acceptance

- No UI text promises generated images, covers, MP4, or videos.
- No DeepSeek prompt asks for an image or video prompt.
- API responses no longer expose `image_prompt` for script/analysis output.
- Full test suite passes.
