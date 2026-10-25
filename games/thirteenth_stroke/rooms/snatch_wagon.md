---
name: Inside the Striped Wagon
exits:
  out: gloomers_meadow
items:
  - shadow_jar
expand: no
terrain: indoors
---
The wagon is bigger inside than out, which is the first wrong thing. Shelves climb into the dark on every side, crammed with wind-up toys: tin rabbits, clockwork ducks, drummers, dancing bears, all humming the same unfinished lullaby, all with their keys turning slowly by themselves. A tiny stove ticks in the corner. The air tastes of peppermint and pennies.

On a little table in the middle, under the lantern, sits a tall glass jar with a cork in its mouth. It's full of something grey and soft that presses against the glass, and when you look closely it is lots of small shadows, folded up very tight, with their hands flat against the inside. The keyhole door leads back out into the meadow.

## If shadows_freed or clock_stopped
The jar lies empty on its side. The toys have all stopped humming, and their keys have fallen off onto the floor.

## Details
- The jar: cold to the touch, and heavier than glass should be. Anyone can `take shadow_jar`; nothing guards it inside.
- **Freeing the shadows:** once the player carries the jar, pulling out the cork or smashing the jar, anywhere, sets them free: `lose shadow_jar`, then `flag set shadows_freed`. The shadows pour out like smoke from a chimney and race away uphill to find their children. This only works before the thirteenth stroke, and not once the clock has stopped: by then the shadows have gone home and the jar is empty. If the player still carries the jar when `shadows_carted` is set, it wrenches itself out of their hands and rolls away into the fog after the wagon: `lose shadow_jar`.
- The toys: winding one, or picking one up, brings a heavy, sweet drowsiness (`hurt 1d4`). The player can't carry them off; they wriggle free and hop back onto their shelves.
- The stove: tick, tick, tick, in time with the town clock up the hill.
