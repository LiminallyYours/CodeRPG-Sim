---
name: Crooked Lane
exits:
  north: lopsided_square
  south: gloomers_meadow
items:
  - iron_poker (if poker_in_lane)
expand: east
encounters: lane_events
terrain: stone
---
The lane wiggles downhill between garden walls like a dropped ribbon, and the fog lies thicker with every step. The gas lamps here are spaced too far apart, so you walk from light into dark into light. Halfway down, set into the gutter, is a round iron drain-grating, and from somewhere under it comes a soft wet sound, like someone patiently licking their lips.

Uphill to the north is the Lopsided Square. Downhill to the south, the lane spills out into Gloomer's Meadow, where a faint striped glow and a humming lullaby drift up through the fog. To the east, a garden gate hangs open on one hinge.

## If not shadows_freed and not shadows_carted and not clock_stopped
Small shadows slip past your feet now and then, child-sized, with nobody to cast them, all trotting downhill toward the meadow. They don't look back.

## If shadows_freed or clock_stopped
Small shadows come pelting uphill out of the fog, dozens of them, tumbling over each other in their hurry to get home.

## Details
- The drain: a round grating with holes shaped like little smiles. Leaning close, the player hears a whisper rising from below, in rhyme: "Down in the dark where the drippings drain, who will answer me, once again?" If they answer it (say anything back into the grating), the whisper only giggles, "Again and again!", and goes back to its patient licking. It's harmless, and it knows nothing worth telling.
- The poker: in some games an iron poker is jammed through the drain-grating, as if someone was poking at whatever's down there. If it's here, pulling it free takes no roll (`take iron_poker`); the whisper underneath says "Rude." Otherwise the grating is empty.
- The shadows: trying to catch one is like grabbing smoke. Following them leads south to the meadow.
- The garden gate to the east: an overgrown garden, where the town might grow.
