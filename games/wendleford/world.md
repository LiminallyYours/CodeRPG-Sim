---
title: Wendleford
start_room: market_square
stats:
  max_hp: 10
  might: 1
  agility: 1
  wits: 1
coins: 5
# what one person learns or goes through, kept for each person apart; every other flag is shared
personal_flags: heard_from_kit, found_the_box
# a round is a quarter of a day (settings.json: rounds.time_every 1); the times go round and the days are counted
times:
  - morning
  - afternoon
  - evening
  - night
days: yes
needs: food, sleep
sleep_at: night
weather:
  - a clear, blowing sky, with the barley rippling gold across the river
  - high thin cloud and a warm, still air that smells of cut stalks
  - a grey, close sky that never quite brightens
  - a fresh wind off the water, smelling of river mud
generation:
  extras: yes
  rooms: no
  items: no
  characters: yes
  side_quests: yes
---
# Wendleford

## Opening
Wendleford is a small market town on the River Wend, in the middle of harvest. Two nights ago the river rose in the dark and tore away the mill bridge, and the town woke to find the mill and Farmer Dunn's fields cut off on the far bank, reachable only by the ford downstream. The water has gone down since, brown and quick. Across it the barley stands ripe and uncut, and the old folk keep looking at the sky.

## Tone
A plain country market town at harvest time, in no particular year: carts and cobbles, a pump in the square, an inn, a smithy, a tithe barn, fields across the river. There is no magic here and nothing uncanny. Trouble is weather, money, work and neighbours: a flood, a lost box of wages, a crop that might be lost, a cottage standing empty. People are practical and a little nosy, careful with their pennies, kind when it costs them little and sometimes when it costs a good deal. Speech is plain country talk. Prices are in pennies and everyone knows what bread costs. New people are ordinary townsfolk, farmhands, carters and passing traders; new places are small and close by.

## Public knowledge
- Two nights ago the River Wend flooded and swept away the mill bridge. The mill and Farmer Dunn's fields are on the far bank now, reachable only by the ford downstream, which runs strong since the flood but can be waded with care, stake to stake.
- Farmer Dunn's barley stands ripe across the river, and the old folk say rain is coming within a few days. If it isn't cut and in before then, much of it will be lost.
- The reeve, Agnes Pollard, had the box of wages for the bridge work with her at the bridge the night of the flood, and it hasn't been seen since. She's posted a reward for it on the notice board in the square.
- Jory Crane, the carpenter on Lark Lane, builds sheds, lean-tos and the like for anyone who pays. Ida Fenn, the draper, makes clothes and finery to order. Sam Tolley, the smith, makes tools and small things to order.
- The Wheatsheaf has beds and suppers. Bet Lamb sells bread from her stall in the square.
- Widow Mabry's cottage on Lark Lane has stood empty since her sister died.
- There's a market in the square every third day, when Ned Pike sets up his stall of cheap seconds.

## For the referee
- Wages (the bridge, the scullery, the bellows) are paid in hand, there and then, at the end of each spell of work: `work` pays them. Nobody keeps a tally of loads, and no back pay is owed to anyone; if someone asks for wages for work already done, the one who pays says it was settled at the time.
- The ford is waded, never swum or rowed: a check as the broken bridge says, and turned back on a failure. There's no ferry and no boat.
- The townspeople are the ten in this world and those the world agent adds; nobody else (no clerk, no constable, no second baker) unless generated.

## At: false_lead
when: day 1, afternoon
if: not wage_box_found
rumor: Ned Pike swears a tinker with a handcart crossed the bridge the night of the flood, just before it went, and that the reeve's box went off with him.

## At: clouds
when: day 3, morning
seen: Long grey clouds are banking up in the west, and folk keep glancing at the sky and then across the river at Dunn's fields.

## At: harvest_supper
when: day 3, evening
if: harvest_in
seen: Lanterns are lit in the tithe barn for the harvest supper, and the smell of stew and new bread drifts across the square.

## At: rain
when: day 3, night
sets: rain_fell
seen: Rain comes down hard over Wendleford, drumming on every roof, and the river runs high and brown again.

## At: market_day
when: day 4, morning
seen: It's market day again: carts rattle into the square and the stalls go up.

## At: bread_short
when: day 4, morning
if: not harvest_in
seen: Bet Lamb's bread stall stands empty in the square, with a chalked board saying there's no flour to be had from the mill this week.
