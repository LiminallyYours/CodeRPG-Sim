---
title: The Thirteenth Stroke
start_room: lopsided_square
stats:
  max_hp: 10
  might: 1
  agility: 1
  wits: 1
# rolled fresh each new game; these replace the fixed stats above
rolls:
  max_hp: 2d3+8
  might: 1d2
  agility: 1d3-1
  wits: 1d3-1
coins: 3
inventory:
  - bent_umbrella
  - ginger_snaps
equipped: bent_umbrella
# each line picks one of its flags at random when a new game starts
variants:
  craving: craves_giggle, craves_whistle
  poker_spot: poker_in_house, poker_in_lane
# counts down one per move; when it runs out the flag is set
clock:
  name: The town clock strikes thirteen
  moves: 2d6+14
  flag: thirteenth_stroke
  also_if: not shadows_freed and not clock_stopped
  also_flag: shadows_carted
weather:
  - a fat orange moon hanging crooked over the chimney pots
  - a thin grey fog curling up out of the drains
  - a wind that whistles through the rooftops in almost-tunes
  - a still, listening hush, as if the whole town were holding its breath
times:
  - half past ten
  - eleven o'clock
  - a quarter to twelve
  - a minute to midnight
generation:
  extras: yes
  rooms: anywhere
  items: yes
  characters: yes
  side_quests: yes
---
# The Thirteenth Stroke

## Who the player is
A travelling umbrella-mender who came over the hill into Wumbleby at dusk, looking for a bed and a little work. They carry a big black umbrella with a bent rib and a heavy brass tip, a twist of ginger snaps, and three buttons, which is what passes for money in Wumbleby.

## Opening
Wumbleby is a crooked little town where every house leans on its neighbour and every chimney curls like a question mark. Tonight the gas lamps are lit but the windows are dark, and the only sound in the Lopsided Square is the town clock ticking, slow and loud, up in its tilted tower.

A girl in a nightgown and muddy boots is sitting on the fountain's rim with a cricket bat across her knees, wide awake and glaring at the dark. Somewhere down the hill, very faintly, something is humming a lullaby. When you step under the nearest lamp, you notice the girl has a shadow. Then you notice how strange it is to notice that.

## Tone
A storybook town gone wrong: crooked houses, striped hats, rhyming peddlers, wind-up toys and gumdrop colours, with something cold and patient underneath. Think of a picture book read aloud after midnight: silly words, long shadows, a brave kid who won't go to sleep, grown-ups who pretend not to see. Dread comes from small wrong details (a smile that's too wide, a toy that hums by itself, a drain that answers), never from gore or cruelty. Nobody dies; what's at stake is the sleeping children's shadows. The peddler and the drain speak in rhyme; ordinary folk don't. Nothing modern and nothing grand. New people are ordinary townsfolk with odd names; new places are small, crooked and close by.

## Public knowledge
- Three days ago a peddler called Mister Tibbersnatch rolled into town with a striped wagon full of humming wind-up toys, and camped in Gloomer's Meadow at the bottom of Crooked Lane.
- Every child who wound one of his toys fell asleep smiling, and nobody can wake them.
- The sleeping children have no shadows, not even under a lamp.
- The town clock in the Tock Tower is very old, and old Ambrose Tock has kept it for fifty years.
- Grown-ups in Wumbleby don't talk about the drain on Crooked Lane, and they cross the street to avoid it.
- Nell Fizzlewick's sweet shop is open late, the way it always is.
