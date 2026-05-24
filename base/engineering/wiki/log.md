# Engineering Wiki Log (Base)

> Chronological record of all wiki actions. Append-only.

## [2026-05-24] create | Wiki initialized
- Migrated universal knowledge from comfyui_workflow/DEBUG_LESSONS.md
- Created: unity-gotchas, screenshot-capture

## [2026-05-25] ingest | sprite-path-gotcha
- Source: GamePanel iteration — card frame sprites rendered as white rectangles
- Created: sprite-path-gotcha.md
- Root cause: AssetDatabase.LoadAssetAtPath<Sprite> fails in Assets/Art/, works in Assets/Resources/
