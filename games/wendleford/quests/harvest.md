---
name: Dunn's Barley
giver: dunn
completed_by: harvest_in
failed_by: rain_fell and not harvest_in
objectives:
  - Help bring in Farmer Dunn's barley before the rain. (done when harvest_in)
---
## Summary
Farmer Dunn's barley stands ripe on the far bank, and his hired men went home when the bridge went. It needs about eight turns of help, cutting and stooking, before the rain comes on the night of the third day. Nobody is paid, but anyone who helps is fed. If it isn't in, much of it is lost, the mill has nothing to grind, and Bet Lamb's stall has no bread from the fourth day.

## Stages
1. **Get across.** The ford (a check) or, once it's mended, the new bridge.
2. **Help.** `work` in Dunn's fields: every turn counts, and each comes with a meal. Halfway sets `harvest_half`; the last sets `harvest_in`.

## Endings
Tell the ending as soon as `harvest_in` or `rain_fell` decides it: what happens now, nothing later.

### If harvest_in
The last sheaf goes up onto the cart, and Farmer Dunn takes off his hat and stands looking at his stubble field as if he can't quite believe it. The cart creaks off toward the ford with the barley for the tithe barn, and the word goes round Wendleford: Dunn's barley is in.

### If rain_fell and not harvest_in
The rain comes down hard on the uncut barley, beating it flat into the mud. Across the river, Farmer Dunn stands at the edge of his field in the downpour and doesn't go in.
