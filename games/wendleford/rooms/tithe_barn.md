---
name: The Tithe Barn
exits:
  south: market_square
characters:
  - agnes (if time_evening and not agnes_at_inn or time_night and not agnes_at_inn)
sleep: rough
terrain: indoors
---
A huge old barn of grey stone with a roof like an upturned boat, where the town's share of every harvest is stored. Just inside the doors, a table and a stool and a tin lamp make the reeve's office, with a ledger and a cash tin on the table. Most of the floor is empty, swept and waiting for the barley. A ladder climbs to the hayloft, where last year's hay is heaped soft and dusty under the rafters.

The great doors open south onto the Market Square.

## If harvest_in and day_3 and time_evening
The barn is full of light and noise for the harvest supper: trestles end to end, lanterns on the beams, a pot of stew the size of a cartwheel, new bread, cider. Half the town is here, and Farmer Dunn is going round shaking hands.

## If harvest_in and day_3 and time_evening and most_harvest
When the cider goes round, Agnes Pollard stands up on a bench, calls your name over the noise, and raises her cup to you as the one who did most to bring the barley in. The whole barn drinks to you.

## Details
- The hayloft: anyone may sleep up there, by the reeve's leave (`sleep`, from evening). It's free, and dry, but it's straw and dust and mice, and nobody sleeps well on it.
- The harvest supper (on the evening of day 3, if the barley is in): everyone who comes is fed: `meet food`.
- The reeve's office: Agnes keeps the town's accounts here in the evenings, and pays the bridge wages from the cash tin.
