---
name: Gloomer's Meadow
exits:
  north: crooked_lane
  in: snatch_wagon (if tibbersnatch_peddling and not shadows_carted or tibbersnatch_defeated and not shadows_carted or wagon_slipped and not shadows_carted)
characters:
  - tibbersnatch (if not tibbersnatch_peddling and not tibbersnatch_defeated and not shadows_carted)
expand: no
terrain: gloomgrass
---
At the bottom of the hill the town gives up and the meadow begins: long grey grass, fog to the knee, and a ring of mushrooms that seem to lean in to listen. In the middle of it all stands a tall wagon painted in red and white stripes, with a crooked chimney and a door shaped like a keyhole. A lantern hangs over the door. The only way back is north, up Crooked Lane.

## If not shadows_freed and not shadows_carted and not clock_stopped
The lullaby is coming from inside the wagon. Small shadows wait in a patient line at the foot of its steps, and one by one they climb up and slip in through the keyhole door.

## If not tibbersnatch_peddling and not tibbersnatch_defeated and not shadows_carted
Mister Tibbersnatch sits on the wagon steps in his striped stovepipe hat, polishing a wind-up toy with a handkerchief, humming along with the lullaby. He sees you before you see him. He always does.

## If tibbersnatch_peddling and not tibbersnatch_defeated and not shadows_carted
The wagon steps are empty. The peddler has gone up into town with his tray of toys, and the keyhole door stands a little open behind him.

## If tibbersnatch_defeated and not shadows_carted
A heap of striped cloth and one stovepipe hat lie in the grass by the steps, and a little spring sticks out of the heap, quivering. The keyhole door hangs open.

## If shadows_freed
The wagon's door hangs open and the lullaby has stopped. The striped paint is peeling and the wagon looks small and shabby, like a toy left out in the rain.

## If clock_stopped and not shadows_freed and not shadows_carted
The lullaby has jammed on one note. The wagon's wheels have sunk into the turf as if it suddenly weighs a ton, and the shadows are tumbling back out of the keyhole door and scampering away uphill.

## If shadows_carted
There is nothing here but two deep wheel-ruts that run into the fog and stop, as if the wagon simply rolled off the edge of the world.

## Details
- The wagon: tall, striped, smelling of tin and peppermint. The keyhole door is how the shadows go in. While Mister Tibbersnatch sits on the steps, nobody gets in past him without his say (see `tibbersnatch`). While he's out peddling in the square, or if he's been beaten, the door is open: go in.
- The line of shadows: they wait politely. Speaking to them, the smallest one points at the wagon and then at the town clock up the hill, and covers its ears.
- The mushrooms: grey and soft. They lean toward whoever is talking. Nothing more.
