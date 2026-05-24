---
title: Screenshot Capture Methods
created: 2026-05-24
updated: 2026-05-24
type: concept
tags: [unity, screenshot, tmp-text, camera, play-mode]
sources: [comfyui_workflow/DEBUG_LESSONS.md]
confidence: high
---

# Screenshot Methods in Unity

## Camera.Render — Limited

`Camera.Render()` + `ReadPixels()` captures Image components but **misses
TMP_Text** in ScreenSpaceCamera mode. The TMP SDF shader doesn't follow
the render target switch.

Play Mode makes it worse — nearly black output (13KB).

## ScreenCapture.CaptureScreenshot — Reliable

The only reliable method. Requires:

1. Enter Play Mode (`EditorApplication.isPlaying = true`)
2. Wait for UI load (3-5 seconds)
3. `ScreenCapture.CaptureScreenshot(path)`
4. Wait 1 frame for file write
5. Exit Play Mode

## PIL Mockup — Environment-Independent

For environments without display access (SSH, CI), use PIL + real font files
to composite a mockup. Matches Unity TMP rendering closely enough for
automated evaluation.

## macOS screencapture — Doesn't Work

`screencapture` CLI requires display access. Fails in sandboxed environments
with "could not create image from display".

See also: [[unity-gotchas]], [[sprite-path-gotcha]]
