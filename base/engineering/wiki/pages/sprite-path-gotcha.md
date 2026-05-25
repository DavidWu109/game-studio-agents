---
title: Sprite Loading Path — Assets/ vs Resources/
created: 2026-05-25
updated: 2026-05-25
type: concept
tags: [asset-loading, engine-gotcha, sprite, unity]
sources: [GamePanel iteration 2026-05-25]
confidence: high
---

# Sprite Path Gotcha

## Problem

`AssetDatabase.LoadAssetAtPath<Sprite>("Assets/Art/CardFrames/card_frame_person.png")`
returns null even when the file exists and textureType=8 (Sprite) in meta.

`AssetDatabase.LoadAssetAtPath<Texture2D>()` succeeds for the same path.

## Root Cause

In Tuanjie (Unity fork), some textures imported as Sprite type in
`Assets/Art/` fail to load as `<Sprite>` but succeed as `<Texture2D>`.
The same files in `Assets/Resources/Art/` load correctly as `<Sprite>`.

Likely cause: Tuanjie's importer may not regenerate the Sprite sub-asset
for textures outside the Resources folder unless explicitly reimported
with specific settings.

## Fix

Use `Assets/Resources/` path for sprite loading:

```csharp
// BAD: returns Sprite=null in Tuanjie
AssetDatabase.LoadAssetAtPath<Sprite>("Assets/Art/CardFrames/card_frame_person.png");

// GOOD: returns Sprite correctly
AssetDatabase.LoadAssetAtPath<Sprite>("Assets/Resources/Art/CardFrames/card_frame_person.png");
```

## Impact

This bug consumed 3 rounds of GamePanel iteration (R1-R3) debugging
why dummy hand cards rendered as white rectangles instead of showing
card frames.

See also: [[unity-gotchas]], [[screenshot-capture]]
