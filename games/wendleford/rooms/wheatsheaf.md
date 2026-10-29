---
name: The Wheatsheaf
exits:
  west: market_square
characters:
  - tom
  - agnes (if agnes_at_inn and time_evening or agnes_at_inn and time_night)
sleep: bed
bed_price: 2
work:
  stat: wits
  pay: 2-4
  dc: easy
terrain: indoors
---
The town's inn: a long, low taproom with a sagging beamed ceiling, a fire at one end and a smell of ale, woodsmoke and stew. Settles and tables line the walls, and a few carters and farmhands sit over their mugs, talking about the flood, the barley and the weather. A stair at the back goes up to the rooms where travellers sleep, and a door behind the bar opens on a steamy scullery stacked high with dirty pots.

The door to the west lets out onto the Market Square.

## Details
- The beds upstairs: Tom Harrow lets a bed for the night; the price is paid when someone turns in (`sleep`, from evening).
- Supper: a bowl of stew and a heel of bread, which Tom sells across the bar (`buy stew`).
- The scullery: Tom is short-handed and pays for the pots to be washed (`work`, a Wits check). On a success he also gives them their supper for nothing: `meet food`.
- The talk: whoever sits here a while hears what the town is saying.
