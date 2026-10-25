---
name: The Pumbletons' Leaning House
exits:
  east: lopsided_square
items:
  - iron_poker (if poker_in_house)
characters:
  - pip (if shadows_freed or clock_stopped)
expand: no
terrain: indoors
---
The Pumbletons' house leans so far to the left that the furniture has all slid into one corner, and the pictures hang at a slant. A fire has burned down to orange coals in the crooked hearth. Everything ticks: three clocks on the mantel, all a little out of step.

In a bed under the window lies a small boy in striped pyjamas, fast asleep, smiling a wide, sweet, unchanging smile. The firelight falls across him, and the wall behind him is bare: he has no shadow at all. On the floor beside the bed, a tin wind-up rabbit hums to itself, though nobody has wound it. The front door, to the east, lets out onto the Lopsided Square.

## If shadows_freed or clock_stopped
Tod is sitting up in bed, yawning and grumpy, and his shadow is on the wall behind him, yawning too. Pip is perched on the end of the bed, pretending she wasn't worried. The tin rabbit lies on its side, silent, its key snapped off.

## If shadows_carted
Tod is awake, and smiling, and very polite. He doesn't cast a shadow, and he doesn't seem to mind. Pip won't look at him.

## Details
- Tod: Pip's little brother. Shaking him, shouting, even tickling: nothing wakes him. His smile doesn't change. Up close he is humming the same unfinished lullaby that drifts up from Gloomer's Meadow.
- The tin rabbit: one of Mister Tibbersnatch's toys. Its key turns by itself, slowly. If the player picks it up or winds it, a sweet, heavy drowsiness pours over them; they stagger back and slap themselves awake (`hurt 1d4`). Putting it down is wise.
- The wall behind the bed: if the player holds a light up to it, a faint grey smudge shows where a shadow used to be, like a mark left by a picture taken down.
- The hearth: ash and coals. If the iron poker is lying here (it is in some games), it leans against the hearth, black and heavy, and the player can simply `take iron_poker`. Otherwise the poker-hook is empty; Pip thinks Tod dragged it out to the lane to poke at the drain, days ago.
