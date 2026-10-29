---
name: Abel Tash
role: a carter stranded at the Wheatsheaf by the broken bridge
minor: yes
card: #7a5a48
hp: 6
defense: 9
attack: 0
damage: 1d2
---
## Personality
Abel is a thick-necked carter of forty-odd, with a whip-scar on one cheek and a coat that smells of horse. The flood stranded him on this side of the river with a load he can't deliver, and his cart's wheel has a cracked iron tyre. Sam Tolley will mend it for two pennies, and Abel has drunk the two pennies. He's sour and loud, he resents strangers taking the bridge wages that he reckons should go to men he knows, and he jeers at anyone who looks soft.

## How he speaks
Loud and sneering, thick with ale by the evening. He calls people "my lady" or "my lord" when he means the opposite.

## What he knows
- His wheel's tyre is cracked, and Sam wants two pennies to mend it.
- The bridge wages ought to go to proper working men, not to whoever wanders in.
- Every carter's story from here to the coast, most of them about fights he won.

## What he wants
His wheel mended, the bridge back so he can get his load on the road, and somebody to blame in the meantime.

## What he will trade or reveal
- He'll take two pennies for the wheel from anyone soft enough to give them, and grumbles a thank-you.

## If abel_wheel_mended
His wheel's mended, and he's a shade less sour.

## If abel_owes
He's gruffly civil to the one talking to him, who paid for his wheel, and picks no quarrel with them.

## If abel_defeated
He's nursing a split lip and his pride, and keeps to his corner.

## GM only
- **Quarrels:** if someone answers his jeering sharply, he gives them a shove: `hurt 1`. If they shove back or swing at him, it's a fight: `attack abel`.
- **The wheel:** if someone gives him two pennies for it: `coins -2 gift`, `flag set abel_wheel_mended`, and `flag set abel_owes` for the one who paid.
