---
name: Lark Lane
exits:
  southeast: market_square
  north: mabry_cottage
characters:
  - jory (if time_morning and not bridge_mended or time_night and not bridge_mended or bridge_mended and not jory_at_mill)
  - mabry
build:
  west: an empty plot between two garden walls, nettled and level, where an old cart-shed once stood
sleep: rough
terrain: grass
---
A quiet lane of cottages behind garden walls, with hollyhocks leaning over them and a smell of woodsmoke. Jory Crane's yard is here, stacked with planks and posts under a lean-to roof, with a sawhorse and a heap of shavings. Widow Mabry sits shelling beans on the step of the cottage next to his yard.

To the north, behind a green gate, is the little cottage that stood empty after her sister died, with its curtains drawn. To the west is an empty plot between two garden walls. The lane runs back southeast to the Market Square.

## Details
- The lane: anyone may lie down against a garden wall for the night (`sleep`, from evening). It's cold, and nobody sleeps well out here.
- The empty cottage: it's Widow Mabry's to let. What she asks for it, she says when asked.
- The empty plot: nettles and level ground, where an old cart-shed stood. Jory says he could put something up there, for a price.
- Jory's yard: in the mornings he's here at his sawhorse; the rest of the day he's down at the bridge, until the bridge is mended; after that he's here all day.
- Jory's timber: his own, for what he builds; he sells none of it loose.
