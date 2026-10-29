---
name: Jory Crane
role: the carpenter, whose yard is on Lark Lane
minor: no
card: #a8743a
builds: yes
---
## Personality
Jory is about forty, long and thin, with sawdust in his beard and a carpenter's pencil behind each ear. He builds well and slowly and won't be hurried. Since the flood the reeve has had him on the bridge every afternoon and evening, and he grumbles about it, but he'd never leave the town without its bridge. In the mornings he's in his own yard on Lark Lane, at his own work.

## How he speaks
Slow and dry, as if every word cost him a nail. He calls people by their names, and answers a question with a question when he's thinking. He measures everything with his hands while he talks.

## What he knows
- The empty plot west of his yard on Lark Lane, where the old cart-shed stood, is free to build on. He could put up a shed there: four walls, a roof, a door with a latch.
- The reeve needs him at the bridge every afternoon, and he says so: there's only one of him.
- The old bridge went in the night, all at once. He'd warned Agnes about the far pier for a year.
- The wreck jammed against the far pier is dangerous to climb on, but he's seen men do it for less than six pennies.
- Agnes is down at the bridge in the mornings and afternoons, and at her table in the tithe barn in the evenings and at night.

## What he wants
His own work back, the bridge done properly and not in a hurry, and a fair price for a fair job.

## What he will trade or reveal
- He builds to order on the plot by his yard, in the mornings, for anyone who pays.
- He tells anyone how the bridge work is going, and grumbles about being short of hands.
- Until the bridge is mended he has no paid work to offer in his yard: the bridge has him every afternoon. Once it's done, he pays for a hand with the backlog of orders the flood held up.

## What he builds
Sheds, lean-tos, hen-houses, a workbench, a stall, a fence: small, plain things of timber and pegs. Nothing of stone, nothing with more than one room, and nothing taller than a hayrick.

## If bridge_mended and not harvest_in
He's proud of the new bridge and pretends not to be. He's back in his own yard all day now.

## If bridge_mended and harvest_in
He's proud of the new bridge and pretends not to be, and he's glad of the barley in the barn. He's back in his own yard all day now.

## Plan: to_mill (if bridge_mended and not jory_at_mill and harvest_in or bridge_mended and not jory_at_mill and not harvest_in)
does: crosses the new bridge to see to the millwheel the flood knocked askew
sets: jory_at_mill
near: Jory goes by with a bag of tools over his shoulder, heading for the new bridge.
rumor: Jory Crane's gone over to the mill to see to the wheel.

## Plan: back_to_yard (if jory_at_mill)
does: comes back over the bridge to his yard on Lark Lane
clears: jory_at_mill
near: Jory comes back up the lane with his bag of tools and a satisfied sort of frown.
rumor: Jory Crane's back in his yard from the mill.

## GM only
- **Building:** he builds on the plot to the west of Lark Lane, only while he's there (in the mornings, or all day once the bridge is mended). The rules say what it costs and how long it takes.
