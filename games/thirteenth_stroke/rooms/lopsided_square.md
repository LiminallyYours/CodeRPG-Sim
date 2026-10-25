---
name: The Lopsided Square
exits:
  north: tock_tower
  east: fizzlewick_shop
  west: leaning_house
  south: crooked_lane
characters:
  - mags
  - pip (if not shadows_freed and not clock_stopped)
  - tibbersnatch (if tibbersnatch_peddling and not tibbersnatch_defeated and not shadows_carted)
expand: southwest
terrain: stone
---
A square that isn't square: its cobbles slope one way and its houses lean the other, so standing in the middle feels like standing on a ship. A dry fountain sits in the centre, shaped like a fish balancing a smaller fish on its nose. The gas lamps are lit, but every window around the square is dark. By the dry fountain stands a tall-wheeled cart heaped with rags and bottles, a sleepy donkey in the shafts, and an old woman in a great many shawls.

To the north, the Tock Tower leans over the rooftops, its great clock face ticking loud enough to hear in your teeth. To the east, candy-striped light glows in the window of Fizzlewick's sweet shop. To the west, the tallest, tipsiest house in town, the Pumbletons', leans so far it seems to be listening. To the south, Crooked Lane winds down the hill into the fog. To the southwest, a gap between two houses opens onto a weedy alley nobody has bothered to name.

## If not shadows_freed and not clock_stopped
Pip Pumbleton sits on the fountain's rim in her nightgown and muddy boots, a cricket bat across her knees, glaring down the hill. She is very obviously not going to sleep.

## If not shadows_freed and not shadows_carted and not clock_stopped
Down the hill, very faintly, something hums a lullaby. It never quite finishes the tune.

## If tibbersnatch_peddling and not tibbersnatch_defeated
A tall, thin man in a striped stovepipe hat is strolling round the fountain with a tray of wind-up toys hung from his neck. The toys hum softly. His grin is wider than a grin ought to be, and it doesn't move when he talks.

## If shadows_freed
Lights are coming on in windows all round the square. Somewhere a child is laughing, and somewhere else a mother is crying the good kind of tears. Every lamp throws shadows again, and the shadows look pleased about it.

## If shadows_carted
The sleeping children have woken and wandered out into the square in their nightclothes, smiling sweetly at nothing. Under the lamps, not one of them has a shadow. Grown-ups lead them gently home, and nobody says anything at all.

## If clock_stopped and not shadows_freed
The clock's hands are frozen a hair before midnight. Sleepy children in nightgowns wander out of doorways, rubbing their eyes and looking for their shadows, which are trotting back up Crooked Lane to find them.

## Details
- The fountain: dry, with a scatter of buttons in the bottom for luck. Taking them is bad manners; anyone watching tuts. A Wits check (`check wits 12`) notices a long, child-sized shadow lying in the basin with nobody to cast it, which slides away down the hill when looked at. On a failure, only buttons and dead leaves.
- The clock face: it says nearly half past ten, or later. Its tick is louder than any clock's should be.
- The cart: rags, bones, bottles, bits. Mags buys things people have had made (see `mags`).
- The alley to the southwest: weeds, a broken cart, and a gap in the map where the town might grow.
