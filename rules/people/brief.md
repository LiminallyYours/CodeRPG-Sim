# The fixed words of what a person in the cast reads: their brief each turn (who they are, their memory, the
# status block), the lines describing offers, and the lines the rules put into their memory or the talk going
# around. Everything else they read is the world's content, the referee's stories, or their own words.
#
# One phrase per line: its name, a colon, then the words. Spaces after the colon are ignored. A line starting with
# # is a comment, and blank lines are ignored. Words in {braces} are filled in by rules/rpg.py; a phrase may leave
# one out, but may not name one it doesn't list. `rpg.py validate` checks every phrase is here and every gap is
# known. Which sections appear, and in what order, is decided by the code (rules/rpg.py: cmd_brief, memory_text,
# pane_text); the think-back prompt is rules/people/thinkback.md, and the last lines here fill its gaps.
#
# Nothing here may name the machinery (game, rules, dice, player, ...): to them it's a life, not a game.

# ---- who they are, at the top of every brief (their cast entry, in their own first person)
who_i_am:        ## Who I am (a note to myself)
i_am:            I'm {name} ({pronouns}). {personality}
how_i_talk:      How I talk: {voice}
drives:          What drives me: {motivations}.
# ---- (a cast entry made from an archetype, tools/cast.py, has these in place of What drives me)
what_i_want:     What I want: {wants}.
steer_clear:     What I steer clear of: {avoids}.
wont_do:         What I won't do: {wont}.
comes_first:     What comes first: {priorities}.
then:            then
people_i_know:   People I know: {people}.
person_i_know:   {who}: {how}

# ---- what they know: their own starting facts and what this run has settled (never fading), then what everyone
# ---- around here knows (rules/people/universe.md, then the world's public knowledge)
i_know:          ## What I know
everyone_knows:  ## What everyone around here knows

# ---- their first turn only, then their memory
begins:          ## How it begins
remember:        ## What you remember from before
lately:          ## Lately
moment:          ### Moment {n}
did:             What you did
why:             Why
happened:        What happened
told:            What you were told
changed:         What changed
stood:           How things stood after

# ---- a moment's what-changed line, its parts joined by "; " (rules/rpg.py: changed_line). "How things stood after"
# ---- (stood) is only for moments kept before the line existed, each with a whole copy of the status block
change_went:     you went from {before} to {after}
change_money:    {currency} {before} to {after}
change_health:   health {before} to {after}
change_got:      you got {things}
change_lost:     you no longer had {things}
change_in_hand:  you took {things} in hand
change_put_away: you put {things} away
change_waiting:  {things} waiting for you to pay
change_building: work began on {things} for you
change_own:      {things} became yours
change_met:      you met {people}

# ---- the status block: where they are
where_you_are:   ## Where you are
place:           {place}.
time_on_day:     {time} on day {n}
since_last:      Since you last acted: it was {then}; now it's {now}.
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
rented:          {place} (yours to the end of day {n})
paid_bed:        A bed is paid for at {place}, {nights}.
tonight:         for tonight
nights:          for {n} more nights
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
# ---- under it, side by side: their needs (a world with needs), their wants (brief.wants: their own words, from
# ---- What drives me), and what they've taken on; with neither needs nor wants, what they've taken on alone, as before
you_need:        What you need: {needs}
you_want:        What you want: {wants}.
taken_on:        What you've taken on:
food_fed:        You've eaten today.
food_due:        You haven't eaten yet today.
food_hungry:     You're hungry: you went all yesterday without food.
food_weak:       You're weak with hunger: it's days since you ate.
sleep_time:      It's the time for sleep, if you mean to.
sleep_slept:     You've settled down to sleep for the night.
sleep_rested:    You slept well last night.
sleep_tired:     You're tired: you didn't sleep properly last night.
sleep_exhausted: You're worn out: night after night without sleep.
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
let_ended:       Your time at {place} has run out: it isn't yours any more.

# ---- the think-back (rules/people/thinkback.md): who they are, as memory.thinkback_sees says (the whole Who I am
# ---- note follows thinkback_note), and their list of what they've learned when it's empty
thinkback_voice: How you speak, in your own words: {voice}
thinkback_note:  This is the note you keep about yourself:
learned_none:    Nothing yet.
