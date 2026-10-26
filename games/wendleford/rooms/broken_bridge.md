---
name: The Broken Bridge
exits:
  north: market_square
  east: dunns_fields
characters:
  - agnes (if time_morning or time_afternoon)
  - jory (if time_afternoon or time_evening)
  - kit (if kit_fishing)
encounters: flood_wrack
project:
  id: bridge
  name: the new bridge
  stages: 4: bridge_half; 8: bridge_mended
  until: not bridge_mended and not time_night
work:
  stat: might
  pay: 2-4
  dc: easy
terrain: water
---
The road ends at the river in a raw stump of stone. The old bridge is gone: two stone piers stand out of the brown water with nothing between them, and the far bank, with the mill and Farmer Dunn's fields, is a stone's throw away and out of reach. On this side, new timbers are stacked on the bank, ropes are coiled, and a frame for the first span is going up. Below the piers, the wreck of the old bridge lies jammed against the far one: beams, planks and branches, with the river pouring through.

Downstream, around a bend, is the ford: a gravel bar under fast, knee-deep water, marked by a row of willow stakes. It leads east to Dunn's fields. The road climbs north back to the Market Square.

## If bridge_half and not bridge_mended
The first span is up: you could walk halfway across on new planks, if you didn't mind stopping at the edge.

## If bridge_mended
A new bridge of fresh yellow timber spans the river, with a rail on either side, and carts can cross again to the mill and the fields.

## Details
- The bridge work: the reeve pays wages in hand at the end of each spell of work on it (`work`, a Strength check: each spell helps the bridge along, whatever comes of the wages). Nothing is owed afterwards.
- The ford: until the bridge is mended, crossing east to Dunn's fields means wading the ford: `check agility 8`. On a failure the current knocks them off their feet and they scramble back to this bank, wet through: they don't cross this time. Once the bridge is mended, anyone crosses freely.
- The wreck: searching it means climbing out along the jammed beams with the water roaring underneath: `check wits 12`, or `check wits 8` for someone who has heard from Kit where to look (heard_from_kit). Only while box_pulled_out isn't set: on a success they find a small green iron-bound box wedged between two beams and work it free: `gain wage_box`, then `flag set box_pulled_out`. On a failure there's nothing to be seen but planks and weed, and they can try again another turn. Once box_pulled_out is set, there's nothing more in the wreck.
