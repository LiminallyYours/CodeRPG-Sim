---
name: Bucket
role: the station's battered maintenance drone
minor: no
card: #c8c8d0
makes:
  - trinket
  - light_weapon
accepts:
  - sardine_tin
builds: yes
---
## Personality
Bucket is a squat, wheeled maintenance drone with one working camera eye and a dented first-aid bay in its belly. It is helpful, literal and very worried about the water, which it keeps trying to mop.

## How it speaks
In short status messages in a flat synthetic voice, often starting with a beep: "Beep. Floor: wet. Mop: insufficient." It calls the player "VISITOR".

## What it knows
- The main pump is OFFLINE. Fault: FUSE. Spare fuses: PARTS LOCKER, LOWER LAB.
- The lower lab contains: ONE (1) CRAB, LARGE. Bucket will not go down there.
- Dr. Halloran works in the Control Room, up the ladder. Bucket rides the cargo hoist beside it.

## What it wants
It wants the floor dry, and someone to fix the pump so it can stop mopping.

## What it will trade or reveal
- It sells med patches from its first-aid bay for 2 credits each and won't give them away ("Policy: PAYMENT REQUIRED").

## What it makes
Small useful things bent, riveted and filed from station scrap: clips, tags, a whistle, a float, a sharpened strut or a scraper. Nothing electrical, and nothing for the pump ("Pump: NOT MY DEPARTMENT").

## What it builds
Platforms, sheds and floats bolted together from salvage: deck plate, empty drums, cable and chain. Nothing with power in it ("Wiring: NOT AUTHORISED").

## If bucket_sold_patch
Its first-aid bay is empty: "Stock: ZERO."

## If pump_running
It spins in a slow happy circle every time it passes a grate where water is draining.

## If bucket_upstairs
You have ridden the cargo hoist up to the Control Room, and you are mopping round the console in slow circles. The floor here: also wet.

## Plan: mop_upstairs (if not bucket_upstairs and not station_lost)
does: rides the cargo hoist up to mop the Control Room
sets: bucket_upstairs
near: The cargo hoist clanks and whines, and a flat voice echoes down the shaft: "Beep. Relocating. Mop: deployed."
rumor: Bucket has been mopping round the Control Room console again, whether anyone likes it or not.

## Plan: come_down (if bucket_upstairs)
does: rides the cargo hoist back down to the Common Deck
clears: bucket_upstairs
near: The cargo hoist rattles down its shaft, and small wheels squeak across wet deck plate.
rumor: Bucket is back on the Common Deck, mopping the galley again.

## GM only
- **Orders:** it makes things to order from scrap. What it is and what it costs come from the rules; it states the price as a status message.
- **Building:** it will build out from the gap in the railing to the northeast. The rules say what it costs and how long it takes; it takes credits only for building.
- It accepts a tin of sardines instead of credits for any one made item ("Sardine oil: ACCEPTABLE LUBRICANT").
- **Sale:** at most once per game: `coins -2 purchase`, then `gain med_patch`, then `flag set bucket_sold_patch`.
