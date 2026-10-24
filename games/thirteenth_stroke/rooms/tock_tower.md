---
name: The Tock Tower
exits:
  south: lopsided_square
  up: gearloft
characters:
  - ambrose
expand: no
build:
  east: a patch of nettles beside the tower where the old bell-shed fell down, its four stone corner-posts still standing
  west: the coal yard behind the tower, a cinder-black square of ground between sooty walls, with room for something small
terrain: indoors
---
The bottom of the clock tower is one round room full of ropes, weights and the smell of oil. Long chains run up through a hole in the ceiling, and every few seconds they twitch as the clock ticks above. A cot, a kettle and a workbench covered in tiny cogs crowd one wall; this is where old Ambrose Tock lives, eats and worries.

A narrow ladder climbs up through the ceiling into the gearloft. The door to the south lets out onto the Lopsided Square. A small window to the east looks out on the nettle patch where the old bell-shed stood, four stone corner-posts still poking out of the weeds. To the west, a low door opens onto the coal yard behind the tower.

## If clock_stopped
The chains hang still. The tick has stopped, and the silence is so big it hums. Ambrose keeps looking up at the ceiling and chuckling.

## If thirteenth_stroke and not clock_stopped
The chains have stopped swinging. The thirteenth stroke still shivers in the stones.

## Details
- The workbench: cogs, springs and a little tin oil can. A drawing pinned above it shows the clock's insides: in the gearloft one enormous wheel, labelled in faded ink "THE GREAT GEAR: strikes the hours. Keep clear of the teeth."
- The ladder: steep and creaky, but anyone can climb it. Ambrose can't any more; his knees won't let him.
- The chains: touching them, you feel the clock's tick in your bones. A Wits check (`check wits 12`) notices that the chains are pulling slightly faster than they should, as if the clock is hurrying toward something. On a failure, they just feel cold.
- The nettle patch: Ambrose says something could be built there again, for a price.
- The coal yard: through the low door to the west, a square of cinders between sooty walls, with a heap of coal sacks in one corner. Ambrose says he could put something up there too, for a price.
