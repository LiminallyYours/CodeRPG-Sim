---
name: Before the Thirteenth Stroke
giver: pip
started_by: heard_of_shadows
completed_by: shadows_freed and not shadows_carted or clock_stopped and not shadows_carted
failed_by: shadows_carted
objectives:
  - Find out why Wumbleby's children won't wake. (done when heard_of_shadows or shadows_freed or clock_stopped)
  - Find where the shadows have gone. (done when met_tibbersnatch or shadows_freed or clock_stopped)
  - Free the shadows from the peddler's jar, or stop the clock before it strikes thirteen. (done when shadows_freed or clock_stopped)
---
## Summary
A peddler called Mister Tibbersnatch has put Wumbleby's children to sleep with his humming wind-up toys, and their shadows have walked down to his striped wagon, where he keeps them in a jar. At midnight the town clock will strike thirteen, a road out of the world will open, and the wagon will roll away down it with the jar. The children will wake smiling and empty, with no shadows, forever.

## Stages
1. **Hear the problem.** Pip Pumbleton in the Lopsided Square tells it, or old Ambrose Tock in the Tock Tower tells the legend. Either sets `heard_of_shadows`. The player can do everything else before this, and the quest still completes.
2. **Find the shadows.** Clues lead south: Pip watched the shadows walk down Crooked Lane; shadows slip past underfoot on the lane; the wagon stands in Gloomer's Meadow with the jar inside. Meeting Tibbersnatch (in the meadow or, while he's peddling, in the square) completes the second objective.
3. **Choose a way.** Any one of these wins:
   - **Strike a bargain** (see `tibbersnatch`). He never breaks a bargain and will trade the jar for the one thing he hasn't got, which differs each game. If `craves_giggle`, it's the bottled giggle Nell sells in her sweet shop (see `nell`). If `craves_whistle`, it's Ambrose's old tin whistle from the Tock Tower (see `ambrose`). He hints at it in rhyme; Pip overheard it too. Sets `shadows_freed`.
   - **Steal the jar.** Go into the wagon while he's out peddling in the square (his plan), or sneak past him on the steps with an Agility check, or beat him in a fight (he's tough). Then take the jar and uncork or smash it anywhere (see the wagon). Sets `shadows_freed`.
   - **Stop the clock.** Ambrose explains that iron jammed in the Great Gear stops the thirteenth stroke. Get the iron poker (in the Pumbletons' house or stuck in the drain on Crooked Lane, depending on the game), climb to the Gearloft and wedge it in with a Might check (see the Gearloft). Sets `clock_stopped`.

## The clock
The town clock strikes thirteen after a number of moves rolled at the start of each game; the times of day run toward a minute to midnight. When it does, `thirteenth_stroke` is set, and if neither `shadows_freed` nor `clock_stopped` holds, `shadows_carted` is set too: the wagon rolls away down the road out of the world with the jar, and the quest has failed. If the player was carrying the jar, it wrenches out of their hands and rolls after the wagon: `lose shadow_jar`.

## Endings
Narrate whichever single ending matches the flags, as soon as `shadows_freed`, `clock_stopped` or `shadows_carted` is set.

### If shadows_carted
Thirteen strokes boom out over Wumbleby, the last one wrong and hollow. Down in the meadow, the striped wagon rolls away into the fog along a road that wasn't there a moment ago, and the lullaby goes with it. All over town the children wake up, and smile, and say please and thank you, and cast no shadows under any lamp. Pip Pumbleton holds her brother's hand very tightly and doesn't let go. Somewhere, a hundred years from now, a clock will start to run fast.

### If shadows_freed and tibbersnatch_defeated and not shadows_carted
The cork pops and the shadows pour out like smoke from a chimney, racing each other up Crooked Lane. In every crooked house a light comes on and a child sits up, grumpy and yawning, with a shadow behind them yawning too. Down in the meadow a heap of striped cloth stirs, gathers itself into a tall thin shape, and limps off into the fog without a single rhyme. At midnight the clock strikes twelve, just twelve, and the wagon is gone by morning. Pip makes you an honorary Pumbleton.

### If shadows_freed and not tibbersnatch_defeated and not shadows_carted
The shadows pour out like smoke from a chimney and race each other up Crooked Lane, and all over Wumbleby children wake up grumpy, yawning and entirely themselves. Mister Tibbersnatch tips his tall striped hat to you, his grin a little thinner than before. "Well played, my dear, by hook or by crook; I'll be leaving your town right out of my book." At midnight the clock strikes twelve, just twelve, and when the town wakes the meadow is empty but for two wheel-ruts and a smell of peppermint. Pip makes you an honorary Pumbleton.

### If clock_stopped and not shadows_freed and not shadows_carted
The poker shrieks in the gear's teeth and holds. The hands stop a whisker before midnight, and the thirteenth stroke never comes. The lullaby in the meadow jams on one note; the jar's cork creaks out, and the shadows come tumbling back up Crooked Lane to their children. Mister Tibbersnatch waits on his steps all night, tapping one long foot and glaring up at the frozen clock, and at the first grey light of dawn his wagon simply folds up like a pop-up book and is gone. Ambrose Tock dances a jig on his workbench. He'll set the clock going again tomorrow, he says. Probably.

## After the ending
The adventure is over. Tell the player that they finished *The Thirteenth Stroke* and that they can explore Wumbleby freely or type `/newgame` to play again and try another way: a bargain, a theft, a fight, or the clock.
