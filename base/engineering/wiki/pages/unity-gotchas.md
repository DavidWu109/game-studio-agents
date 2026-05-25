---
title: Unity/Tuanjie Common Gotchas
created: 2026-05-24
updated: 2026-05-24
type: concept
tags: [build-pipeline, asset-loading, engine-gotcha, compile, unity]
sources: [comfyui_workflow/DEBUG_LESSONS.md]
confidence: high
---

# Unity/Tuanjie Gotchas

## .cs Files Don't Auto-Recompile

Unity Editor does NOT automatically detect .cs file changes.
Must explicitly trigger:

```
ExecMenu("Assets/Refresh")  → triggers recompilation
sleep 10                     → wait for compile
```

**Verify** by checking `Library/ScriptAssemblies/Assembly-CSharp-Editor.dll`
timestamp. If unchanged, code was not recompiled.

## Static Cache Pollution

Static fields persist across domain reloads unless explicitly cleared.
When changing cached values (fonts, prefabs, configs), add explicit nulling:

```csharp
_cachedValue = null;  // force reload
```

## Tuanjie Process Name

Tuanjie's process name is "Tuanjie", not "Unity". CLI tools that search
for "Unity" process will report "not running". MCP server is still reachable
— ignore this warning.

## MCP Skill Compile Errors Block Everything

A compile error in ANY `Assets/Skills/*.cs` file blocks:
- All other skill compilation
- Play Mode entry ("All compiler errors must be fixed")

Fix: delete the broken .cs + .meta files, then Assets/Refresh.

## Sprite Loading

Use `LoadAssetAtPath<Sprite>()` first, fallback to `Texture2D` + `Sprite.Create()`.
Direct `Texture2D` loading fails silently in some import configurations.

## spriteBorder Must Fit

9-slice `spriteBorder` values L+R must be < image width, T+B < height.
Otherwise Unity renders nothing (transparent). Auto-calculation formula:

```csharp
int corner = h / 2;
int safe = max(2, h / 32);
spriteBorder = (corner, safe, corner, safe);
```

See also: [[screenshot-capture]], [[9-slice-rules]]
