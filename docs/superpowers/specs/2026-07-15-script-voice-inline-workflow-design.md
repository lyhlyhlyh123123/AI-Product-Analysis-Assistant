# Script Voice Inline Workflow Design

## Goal

The video script page should be the single place where users review the hook, review the口播正文, choose or create a voice, generate口播语音, and download the audio. The generated speech must include both the hook and the body text.

## Current Problem

The app currently has a separate sidebar/page for `口播语音`. The script page displays `short_video_script.hook` and `short_video_script.script`, but the voice generation request uses `tts_text || short_video_script.script`, which can omit the visible hook. Users can also attempt voice generation without first selecting a saved voice.

## Approved Approach

Use a combined frontend/backend contract.

1. Frontend: merge the voice controls and audio result panel into the `视频口播文案` page.
2. Frontend: remove the independent `口播语音` navigation item and page.
3. Frontend: disable voice generation until a script exists and a saved voice is selected. Creating a voice selects it automatically.
4. Frontend: generate voice from `hook + "\n" + script` so the visible hook is always spoken.
5. Backend: make generated `tts_text` include both `short_video_script.hook` and `short_video_script.script` so non-frontend callers get the same speech text.
6. History: when loading a saved record with voice audio, render the player inside the script page.

## UI Behavior

The `视频口播文案` page contains:

- Hook display.
- Body script display.
- Saved voice selector.
- Voice name and voice description fields for creating a new voice.
- Audio format and sample rate fields used for voice creation and synthesis request preferences.
- `创建音色` button.
- `制作口播语音` button.
- Audio player and download links.
- Empty state when no audio exists yet.

The `制作口播语音` button stays disabled until both conditions are true:

- `stageState.script` exists.
- `#voice-select` has a non-empty `voice_id`.

If a user reaches the script page without a selected voice, the UI should make the next action clear through the existing status text and disabled button state.

## Data Flow

1. `/api/generate-script` returns `short_video_script.hook`, `short_video_script.script`, and `tts_text`.
2. Backend sets `tts_text` to the combined speech text: hook followed by body script, with blank parts removed.
3. Frontend renders hook and script separately for readability.
4. Frontend computes the voice request text from the rendered script object, using the same combined hook-plus-body rule.
5. `/api/generate-voice` receives `text`, selected `voice_id`, audio format, and sample rate.
6. Generated audio is saved in the record as `voice_response` and displayed on the script page.

## Error Handling

- If no voice is selected, the frontend does not call `/api/generate-voice` and sets status to `请先创建或选择音色`.
- If voice creation fails, existing warning rendering remains responsible for showing DashScope errors.
- If voice generation succeeds without local save, the existing remote audio fallback remains in place.

## Tests

Update focused tests to cover:

- No independent `口播语音` sidebar/page remains.
- Voice controls are present on the `视频口播文案` page.
- Generate voice text combines hook and body.
- No `/api/generate-voice` request is made without selected voice.
- Backend `tts_text` contains both hook and script body.

## Out of Scope

- Redesigning the whole application navigation.
- Adding multi-voice timelines or per-sentence voice switching.
- Changing DashScope voice creation or synthesis endpoints beyond existing behavior.
