---
name: Market Square
exits:
  north: tithe_barn
  east: wheatsheaf
  west: smithy
  northeast: fenns
  northwest: lark_lane
  south: broken_bridge
  southwest: wayside_shrine
board: yes
notices:
  - LOST the night of the flood: the bridge wages box, iron-bound, painted green, the size of a loaf. SIX PENNIES REWARD. A. Pollard, reeve. (if not wage_box_found)
  - HANDS WANTED at the bridge, wages paid in hand by the spell. At the bridge by day, at the tithe barn after. A. Pollard, reeve. (if not bridge_mended)
  - COTTAGE TO LET on Lark Lane. Ask Widow Mabry. (if not let_mabry_cottage)
  - Plain sewing wanted, a penny or two a spell, hemming and seaming at the window. Ida Fenn, at Fenn's.
  - Sheds and lean-tos built to order, a fair price for a fair job. Jory Crane, carpenter, Lark Lane.
characters:
  - bet (if not after_day_3 or harvest_in)
  - ned (if day_1 or day_4 or day_7)
sleep: rough
terrain: stone
---
A cobbled square, uneven and still damp in the low corners where the flood reached up from the river. In the middle stands the town pump with its iron handle and a stone trough, and beside it a notice board under a little slate roof. Bet Lamb's bread stall stands against the wall of the Wheatsheaf, with its striped awning and its baskets.

The Wheatsheaf's door is on the east side of the square, and Sam Tolley's smithy, loud with hammering, on the west. Fenn's, the draper's, has its bow window on the northeast corner, and Lark Lane runs off to the northwest between garden walls. The great dark bulk of the tithe barn closes the north side. To the south the road runs down to the river, where the bridge was.

## If day_1 or day_4 or day_7
It's market day. Carts are drawn up along one side, with trestles of cheeses, eggs and onions, and Ned Pike has his stall of seconds out by the pump: cracked crocks, odd buttons, a lantern with a dent in it, a length of ribbon, all of it laid out on a horse blanket.

## If after_day_3 and not harvest_in
Bet Lamb's stall stands bare under its awning, with a chalked board propped on it: NO FLOUR FROM THE MILL THIS WEEK.

## Details
- The square: anyone may lie down under the market cross or in a doorway for the night (`sleep`, from evening). It's hard and cold, and nobody sleeps well out here.
- The notice board: anyone may pin up a notice of their own, or take their own down; `look` shows what's on it.
- The pump: cold, clean water for anyone. It fills a belly for an hour, no longer.
- Ned's stall (on market days): what he has and what it costs, he says when asked. He's always ready to look at anything someone wants to sell.
- The farm carts (on market days): country folk selling to the town's households by the basket, ordered ahead; Ned's stall is the one for passers-by.
- The pump: where the town's gossip gathers of a morning.
