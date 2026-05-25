---
name: ui-mockup
description: "Build pixel-perfect UI mockups with self-review."
version: 1.0.0
created_by: agent
tags: [mockup, ui, ux, layout, PIL, design]
---

# UI Mockup Skill

Build pixel-perfect panel mockups using PIL + real game assets.
Mockups serve as design targets for Engineering and comparison
baselines for QA.

## When to Use

- Before Engineering builds a new panel
- When redesigning an existing panel
- When adding a new game state to an existing panel

## Procedure

### Step 1: Define States

Every panel has multiple states. List them before drawing anything:

```yaml
# Example: GamePanel states
states:
  - name: your_turn
    description: "Player's turn, can pick opponent or draw from toilet"
    visible: [hand_cards, toilet, poo_button, turn_prompt, opponents, player_info]
    
  - name: opponent_turn
    description: "Waiting for opponent to act"
    visible: [hand_cards, toilet, opponents, player_info, waiting_indicator]
    hidden: [poo_button, turn_prompt]
    
  - name: choose_category
    description: "Category picker overlay after asking opponent"
    visible: [category_picker_overlay, hand_cards_dimmed]
    
  - name: diarrhea_response
    description: "Opponent asked, must give card or sneak diarrhea"
    visible: [diarrhea_bar, hand_cards, timer]
    
  - name: poo_story
    description: "Poo Story popup with story text"
    visible: [poo_story_overlay, dimmed_background]
```

Generate a mockup for EACH state, not just the default.

### Step 2: Layout Grid

Before placing elements, define the layout grid:

```
┌────────────────────────────────────────────────┐
│ Settings                        Opponent (top)  │  90-100%
│                                                 │
│ Opponent    ┌──────────────┐                   │  30-75%
│ (left)      │   TOILET     │     POO!          │
│             │   Cards: 53  │                   │
│             └──────────────┘                   │
│                                                 │
│ ─────────── YOUR TURN! ──────────              │  ~22%
│ ─────────── table edge ─────────               │  ~21.5%
│ Player  [card][card][card][card][card]  PooZone │  0-21.5%
└────────────────────────────────────────────────┘
```

### Step 3: Self-Review Checklist

Before delivering mockup, check EVERY item:

**Visual Hierarchy:**
- [ ] Most important element (turn action) is most prominent
- [ ] Player can instantly tell "what should I do next?"
- [ ] Score/count numbers are readable at mobile scale
- [ ] Opponents are visible but don't dominate the player's action area

**Layout:**
- [ ] Background texture visible (not too dark, not too busy)
- [ ] Table surface feels like a real table (not a flat color)
- [ ] Hand cards feel "held" (fan shape, overlapping slightly, not scattered)
- [ ] Safe area margins on all edges (notch/rounded corners)
- [ ] No large empty areas with no purpose

**Scale:**
- [ ] Avatars large enough to show emotion (≥100px at 1920 width)
- [ ] Card text readable (name, score visible at phone size)
- [ ] Buttons meet 48pt minimum touch target
- [ ] Toilet/card pile is the visual anchor of the table

**Consistency:**
- [ ] All text uses game font with outlines
- [ ] Colors match style-anchor palette
- [ ] Element style consistent (all CotL cartoon, no mixed styles)

**States:**
- [ ] Each state has its own mockup
- [ ] Transitions between states are clear (what appears/disappears)
- [ ] Overlay states dim the background properly

### Step 4: Build with PIL

Use real assets from the game project:

```python
# Asset sources
CLIENT = Path("~/Projects/go-poo-client")
bg = load(CLIENT / "Assets/Resources/Backgrounds/clean.png")
toilet = load(CLIENT / "Assets/Art/UI/toilet_draw.png")
btn = load(CLIENT / "Assets/Art/UI/btn_primary.png")
avatar = load(CLIENT / "Assets/Resources/UI/emotions/default_alpha.png")
font = ImageFont.truetype(CLIENT / "Assets/Art/Fonts/LuckiestGuy.ttf", 32)
```

### Step 5: Deliver

1. Save mockup(s) to `projects/<game>/design/mockups/<panel>_<state>.png`
2. Send `mockup_ready` message to Engineering + QA
3. Feishu notification with mockup image

## Pitfalls

- Don't make mockup with placeholder boxes — use REAL assets or it's not a useful target
- Don't dim background too much (>35%) — kills the atmosphere
- Don't forget hand card overlap — scattered cards don't feel "held"
- Don't just mockup the happy path — error/waiting/overlay states matter
- Mockup at 1920×1080 (game resolution), not arbitrary size
