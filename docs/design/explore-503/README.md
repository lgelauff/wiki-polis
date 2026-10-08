# Explore card redesign for #503 (round 4, 2026-10-08)

Static mockups for #503 ("Move on" as the main action after voting). This is not app code. `concept-4.html` shows all frames; `concept-4.html?f=<id>` shows one. The PNGs are rendered from it at 1440, 375 and 320 px wide. `v4-sheet-<width>.png` puts every frame on one sheet.

## The design

- **Before voting:** the card shows only Agree / Pass / Disagree.
- **After a vote:**
  - The response line ("Your response: Agree · change") takes the place of the vote buttons.
  - One row appears below the card: **Reword | Move on → | Propose**.
  - Move on sits in the middle, is filled, and gets focus, so Enter continues.
  - None of the next actions sits where a vote button was. A double click can't land on one.
- **Short labels:** the buttons show only "Reword", "Move on →" and "Propose". The full name is in the button as screen-reader text.
- **Before Propose unlocks:** its place shows plain text with a lock, "Unlocks after N more responses".
- **Walkthrough:** one tip bubble at a time, each when its option first becomes usable:
  1. Move on, at the first vote;
  2. Reword, at the next vote;
  3. Propose, at the vote that unlocks it.
- **Bubbles:**
  - Each one points at its button.
  - It closes with ×, Esc, or any button in the row.
  - "Don't show tips again" turns the automatic bubbles off in this browser.
  - The `?` in the progress row replays them one at a time.
  - Which bubbles were seen is remembered in localStorage.
- **Size** (later card, no bubble): 313 px tall on a 320 px phone against 738 px today, and 316 px at 1440 against 358 px.

## Frames

| id | what it shows |
|---|---|
| `before` | before the first vote |
| `first` | first vote: bubble 1, Move on |
| `second` | second vote: bubble 2, Reword |
| `later` | a later card, no bubble |
| `unlock` | the vote that unlocks Propose: bubble 3 |
| `off` | the same vote with tips turned off: no bubble |
| `replay` | `?` pressed: tips replayed one at a time |

## Open questions (parked)

1. Is Propose as plain status text with a lock, before it unlocks, acceptable?
2. Should the quota ("3 of 3 remaining") show only in bubble 3 and the composer, not on the row?
3. Bubble 3: keep the long existing helper text, or add one short new message (about 50 px less on phones)?

Made by Claude on Lodewijk's behalf.
