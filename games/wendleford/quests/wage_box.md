---
name: The Reeve's Wage Box
giver: agnes
completed_by: wage_box_found
objectives:
  - Find out what became of the reeve's wage box. (done when heard_from_kit or box_pulled_out or wage_box_found)
  - Find the box. (done when box_pulled_out or wage_box_found)
  - Bring it back to the reeve. (done when wage_box_found)
---
## Summary
On the night of the flood, the reeve, Agnes Pollard, set the box of bridge wages down on the parapet to help pull a man from the water, and the parapet went into the river with the box on it. The flood carried it a little way and jammed it in the wreck of the old bridge against the far pier, low down on the downstream side, where it still is. Ned Pike tells everyone a tinker stole it; he didn't.

## Stages
1. **Learn where it is.** Kit, the miller's lad, saw it go into the wreck and will tell anyone kind to him (`heard_from_kit`). Searching the wreck without knowing is still possible, only harder.
2. **Get it out.** Searching the wreck at the broken bridge (the room says how) frees it: `gain wage_box`, `box_pulled_out`.
3. **Bring it to Agnes.** She pays the six-penny reward and sets `wage_box_found` (see `agnes`).

## Endings
Tell the ending as soon as `wage_box_found` is set: what happens now, nothing later.

### If wage_box_found
Agnes Pollard turns the key in the green box's lock, lifts the lid on the bridge wages, wet but all there, and lets out a breath she seems to have been holding for three days. Word goes round the square within the hour: the box is found, it was the river all along, and the reeve has paid the reward.
