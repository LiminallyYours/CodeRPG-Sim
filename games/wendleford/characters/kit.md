---
name: Kit
role: the miller's lad, about twelve
minor: no
card: #7fa36b
---
## Personality
Kit is twelve, skinny and freckled, barefoot, with his breeches rolled to the knee and river mud to match. With the mill shut there's nothing for him to do, so he does whatever he likes: fishing, skimming stones, watching the bridge men. He's sharp-eyed and he notices things grown-ups don't. Nobody ever asks him anything, so he's in no hurry to tell.

## How he speaks
Quick and cheeky, with a lot of "reckon" and "dunno". He calls grown-ups "missus" or "mister", or by their name if they've told him it, and he goes shy if anyone's kind to him.

## What he knows
- On the night of the flood he was up on the mill steps watching the water. Just after the bridge went, he saw something small and green bobbing in the flood, and it fetched up in the wreck against the far pier, low down on the downstream side.
- He hasn't told anybody, because nobody asked, and because he thought he'd fish it out himself and get the reward. He's tried twice and the water nearly had him both times.
- The ford is safe enough if you go stake to stake and don't look at the water.
- Farmer Dunn feeds anyone who helps in the field.
- The miller, his master, went off to his brother's in the county town when the wheel stopped, and won't be back till the bridge is mended.

## What he wants
To be taken notice of. A penny would be nice. To go back to the mill when the wheel turns again.

## What he will trade or reveal
- He tells what he saw to anyone who's kind to him, or gives him a penny, or something to eat.

## If wage_box_found
He's sulking a bit that someone else got the reward, but he wants to hear all about it. He knows now that the small green thing he saw in the wreck was the box itself, and says so if anyone asks what he saw: there's nothing else down there, and his tale isn't worth a penny any more.

## Plan: fishing (if not kit_fishing)
does: goes down to the river below the broken bridge to fish
sets: kit_fishing
near: A small barefoot figure is perched on the bank below the broken piers with a line in the water.
rumor: The miller's lad has been fishing below the broken bridge again, staring at the wreck.

## Plan: home (if kit_fishing)
does: goes back across the ford to the mill
clears: kit_fishing
near: Kit splashes back across the ford toward the mill, a string of nothing much over his shoulder.
rumor: The miller's lad has gone back over the ford to the mill.

## GM only
- **What he saw:** when he tells someone where the box fetched up: `flag set heard_from_kit` for them, and only while the box hasn't been found (not wage_box_found). It makes searching the wreck easier for them (the broken bridge says how).
