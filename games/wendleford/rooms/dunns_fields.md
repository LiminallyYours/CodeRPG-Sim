---
name: Dunn's Fields and the Mill
exits:
  west: broken_bridge
characters:
  - dunn
  - kit (if not kit_fishing)
  - jory (if bridge_mended and jory_at_mill)
  - amos (if miller_home)
project:
  id: harvest
  name: Dunn's harvest
  stages: 6: harvest_half; 12: harvest_in
  until: not harvest_in and not rain_fell and not time_night
  meal: yes
sleep: rough
terrain: grass
---
On the far bank the land opens out into wide fields of barley, ripe and pale gold, whispering in the wind. One corner has been cut and stooked; the rest stands waiting. Scythes and sickles lean against a cart. Beside the river the mill sits with its wheel still, a tide-mark of mud halfway up its wall.

To the west, the way back to the town is the ford, or the bridge once it's mended.

## If harvest_half and not harvest_in
Half the field is cut now, the stooks standing in long rows like little tents.

## If harvest_in
The field is stubble, and the last of the sheaves are stacked on the cart for the tithe barn.

## If rain_fell and not harvest_in
The uncut barley lies flattened and sodden, beaten into the mud by the rain.

## If jory_at_mill
Jory Crane is up a ladder at the millwheel, with a mallet and a mouthful of pegs.

## Details
- The stooks: anyone may lie down among the barley for the night (`sleep`, from evening). It's dry enough, but cold, and nobody sleeps well out here.
- The harvest: Farmer Dunn pays no wages, now or later, and says so, but anyone who lends a hand with the cutting and stooking is fed at noon from his wife's basket (`work`: every turn of help counts, and comes with a meal). There's no work after dark.
- The mill: shut while the bridge is down. The miller's lad, Kit, is about the place.
- The scythes and sickles: Dunn's, for anyone helping with the cutting; they stay in the field.
