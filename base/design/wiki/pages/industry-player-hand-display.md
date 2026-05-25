---
title: Industry Patterns — Player Hand/Inventory Display
created: 2026-05-25
updated: 2026-05-25
type: concept
tags: [layout, inventory, touch-zone, mobile, industry-standard]
sources: [web research 2026-05-25]
confidence: high
---

# Player Hand Display — Industry Patterns

Universal patterns for displaying "items the player currently holds"
in mobile games. Applies to: card hands, tower defense build bars,
RPG equipment slots, etc.

## Position: Always Bottom

Every major mobile card game puts the player's hand at the bottom:
- Hearthstone: bottom tray
- Exploding Kittens: bottom row (scroll for 5+)
- Slay the Spire: bottom fan (top 1/3 visible on mobile)
- UNO: bottom arc

**Why**: thumb reachable zone. Players hold phone with thumbs at bottom.
Top of screen = opponent territory. Bottom = player's space.

## Layout Shape: Fan or Arc

| Game | Shape | Overflow Handling |
|---|---|---|
| Hearthstone | slight arc | shrink cards (up to 10) |
| Slay the Spire | fan with rotation | shrink + show top 1/3 only |
| Exploding Kittens | flat row | scroll horizontally (5+ cards hidden off-screen) |
| UNO | arc | shrink cards |

**Pattern**: 70% use fan/arc, 30% use flat row. Fan feels more natural
("holding cards in hand"). Flat row is easier to implement but less immersive.

## Boundary Between Table and Hand: NO HARD LINE

This is the key finding for our GamePanel problem.

| Game | Table-to-Hand Boundary |
|---|---|
| Hearthstone | shadow gradient — table darkens toward bottom, no visible line |
| Slay the Spire | cards float over game area, no separate "hand zone" |
| Exploding Kittens | cards sit at bottom edge, table extends behind them |
| UNO | radial gradient — center brightens, edges darken |

**Pattern**: **ZERO major card games use a hard-colored divider line.**
The transition from game table to hand area is always:
- Shadow/gradient (most common)
- Cards simply overlap the table (no boundary at all)
- Vignette effect (darkening at edges)

## Card Visibility in Hand

Critical information must be visible when cards overlap:

- Power/score values: always visible (top-left corner)
- Card name: may be hidden when fanned, visible on hover/tap
- Card type/category: color-coded edge or banner (visible even when overlapping)
- Card art: partially visible, full on hover

**Rule**: "Important values should be visible while cards are fanned out."

## Interaction

| Action | Pattern |
|---|---|
| View card details | Tap card → enlarges with full info |
| Play a card | Drag to center/target |
| Deselect | Tap elsewhere or swipe back down |

## Lessons for Our System

1. **Kill the yellow divider line** — no successful card game uses one
2. **Use shadow gradient or no boundary** — table naturally darkens at bottom
3. **Hand cards fan with slight rotation** — not flat row, not scattered
4. **Critical info in top-left corner** — score/power visible when fanned
5. **5-card minimum visible** — overflow: shrink first, scroll as last resort
6. **One-handed play consideration** — all actions reachable with thumb

See also: [[knowledge-scaling]], [[page-review-checklist]]

## Sources

- [5 UX/UI Lessons from Designing a Card Game](https://medium.com/@acbassettone/5-ux-ui-lessons-from-designing-a-card-game-b689d3f3187)
- [Game UI Database](https://www.gameuidatabase.com/)
- [Card Game Development Guide](https://games.themindstudios.com/post/card-game-development/)
- [Slay the Spire fan layout discussion](https://discussions.unity.com/t/any-tutorials-on-how-to-make-the-fan-shape-and-hovers-of-slay-the-spire-hand/946558)
- [Exploding Kittens Review](https://toucharcade.com/2016/03/31/exploding-kittens-review/)
- [Hearthstone UI Database](https://www.gameuidatabase.com/gameData.php?id=628)
