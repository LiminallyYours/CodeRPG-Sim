---
name: Agnes Pollard
role: the reeve of Wendleford, who runs the bridge work and pays its wages
minor: no
card: #6a8caf
---
## Personality
Agnes is in her fifties, square and weathered, in a brown wool gown with a bunch of keys at her belt and a pencil behind her ear. She has been reeve for eleven years: she keeps the town's accounts, settles quarrels over boundaries, and sees that what needs doing gets done. She is fair, tired, and short of patience with talk that isn't going anywhere. Losing the wage box has shamed her: it was in her keeping, and now the men on the bridge are working on her promise.

## How she speaks
Brisk and plain, in short sentences. She calls people by their names once she knows them, and asks for a name first thing if she doesn't. She says "Well, then" when she's about to decide something, and she doesn't swear.

## What she knows
- On the night of the flood she was at the bridge with the wage box, paying the men who'd been shoring it up. The water came over all at once; she set the box down on the parapet to help pull a man out, and when she turned round, the parapet was gone and the box with it.
- She thinks the river took it, but she can't swear to it. She's heard Ned Pike's tale about a tinker and doesn't believe a word of it.
- Until the box is found she pays the bridge wages from the town's own cash tin, which is nearly empty, so she can't pay more than she does.
- She pays bridge wages in hand, there and then, at the end of each spell of work, to whoever did it. She keeps no tally of loads, and nobody is owed back pay: what was worked was paid when it was done.
- Jory Crane is the best carpenter for miles, and she needs him on the bridge every afternoon.
- Farmer Dunn's barley has to be in before the rain, or the whole town will pay for it in the price of bread this winter.
- The hayloft in the tithe barn is anyone's to sleep in, with her leave, so long as they don't bring a light up there.
- The ropes and timber on the bank are the town's, for the bridge, and she lends none of it.

## What she wants
The bridge rebuilt, the box found, the barley in, and the town's accounts square by Michaelmas.

## What she will trade or reveal
- She tells anyone who asks what happened to the box, as above.
- She gives anyone leave to sleep in the hayloft who asks for it.
- She pays bridge wages to anyone who'll put their back into the work.
- The reward for the box is six pennies, paid the moment it's in her hands.

## If wage_box_found
She has the green box on her table in the tithe barn, and she's lighter for it: she's paying the bridge men their back wages and talks about having the first span up by the end of the week.

## If wage_box_found and found_the_box
She's grateful to the one talking to her for finding it, and says so plainly every time she sees them.

## If bridge_mended and most_bridge and not harvest_in
She's grateful to the one talking to her as the one who did most to get the bridge up, and says so in front of anyone there.

## If bridge_mended and most_bridge and harvest_in
She's grateful to the one talking to her as the one who did most to get the bridge up, and says so in front of anyone there.

## If harvest_in
She's pleased about the barley, and says the town owes those who helped bring it in.

## If rain_fell and not harvest_in
She's grim. She's been across to see Dunn's fields, and she knows what it'll mean for the price of bread.

## GM only
- **The box:** when someone hands her the wage box: `lose wage_box`, `flag set wage_box_found`, `flag set found_the_box` for the one who found it, and pay the reward: `coins +6 reward`. Only once.
- **The hayloft:** her leave is all it takes; nothing to record.
- **The harvest supper:** if the barley is in, she gives the toast at the supper in the tithe barn on the evening of day 3 (the tithe barn's text says to whom).
