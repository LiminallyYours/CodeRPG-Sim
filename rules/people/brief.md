# The fixed words of what a person in the cast reads: their brief each turn (who they are, their memory, the
# status block), the lines describing offers, and the lines the rules put into their memory or the talk going
# around. Everything else they read is the world's content, the referee's stories, or their own words.
#
# One phrase per line: its name, a colon, then the words. Spaces after the colon are ignored. A line starting with
# # is a comment, and blank lines are ignored. Words in {braces} are filled in by rules/rpg.py; a phrase may leave
# one out, but may not name one it doesn't list. `rpg.py validate` checks every phrase is here and every gap is
# known. Which sections appear, and in what order, is decided by the code (rules/rpg.py: cmd_brief, memory_text,
# pane_text); the think-back prompt is rules/people/thinkback.md.
#
# Nothing here may name the machinery (game, rules, dice, player, ...): to them it's a life, not a game.

# ---- who they are, at the top of every brief (their cast entry, in their own first person)
who_i_am:        ## Who I am (a note to myself)
i_am:            I'm {name}. {personality}
how_i_talk:      How I talk: {voice}
drives:          What drives me: {motivations}.

# ---- their first turn only, then their memory
begins:          ## How it begins
remember:        ## What you remember from before
lately:          ## Lately
moment:          ### Moment {n}
did:             What you did
why:             Why
happened:        What happened
told:            What you were told
stood:           How things stood after

# ---- the status block: where they are
where_you_are:   ## Where you are
place:           {place}.
ways_on:         Ways on: {ways}.
way:             {direction} to {place}
with_you:        With you: {people}.
no_one:          no one

# ---- the status block: themselves
you:             ## You
health:          Health {hp} of {max_hp}. {stats}.
money:           Money: {n} {currency}.
carrying:        Carrying: {things} (load {load} of {limit}).
nothing:         nothing
in_hand:         (in hand)
made_for_you:    (made for you)
own_places:      Your own places: {places} (what you leave there stays yours).
being_built:     Being built for you: {name}.
waiting:         Waiting for you to pay: {thing}, from {maker}, for {price} {currency}{in_trade}.
in_trade:        or {things} in trade
or:              or

# ---- the status block: offers between people
offered_to_you:  ## Offered to you
you_offered:     ## You offered
asks_you:        {who} asks you for {things}, offering nothing in return.
offers_you:      {who} offers you {give}, and asks {want} in return.
you_asked:       You asked {who} for {things}, offering nothing in return.
you_offered_to:  To {who}: {give}, asking {want} in return.
nothing_back:    nothing
for_things:      for {things}
and:             and

# ---- the status block: what they're working on, who and what they know
working_on:      ## What you're working on
quest_done:      (done)
quest_failed:    (it's too late)
step_done:       [done]
people_met:      ## People you've met
places_been:     ## Places you've been
talk:            ## Talk going around

# ---- with the dice lines on (brief.dice_lines), and the question at the end
attempts:        ## How your last attempts went
closing:         What do you do now?

# ---- lines the rules put into memory, or into the talk going around
says:            {name} says: "{words}"
finished:        {place} is finished, {direction} of {where}: {builder} built it for you.
finished_rumor:  {place} is finished, {direction} of {where}, and folk are curious to see it.
