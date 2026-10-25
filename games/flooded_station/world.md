---
title: The Flooded Station
start_room: the_landing
stats:
  max_hp: 10
  might: 0
  agility: 1
  wits: 2
# rolled fresh each new game; these replace the fixed stats above
rolls:
  max_hp: 2d2+8
  might: 1d2-1
  agility: 1d3-1
  wits: 1d2
coins: 4
inventory:
  - diving_knife
  - med_patch
equipped: diving_knife
# what one person learns or goes through, kept for each person apart; every other flag is shared
personal_flags: halloran_briefed, radio_habit, habit_broken
# each line picks one of its flags at random when a new game starts
variants:
  halloran_mood: halloran_stubborn, halloran_shaken
  sardine_spot: sardines_in_galley, sardines_on_landing
# counts down one per move; when it runs out the flag is set
clock:
  name: The tide peaks
  moves: 2d4+10
  flag: tide_peaked
  # when it runs out, if this holds, also set:
  also_if: not pump_running and not evacuated
  also_flag: station_lost
weather:
  - rain drumming on the roof plates
  - a grey swell slapping at the stilts
  - wind howling through the antenna mast
  - a brief, uneasy calm
# what the world agent may create during a run
generation:
  extras: no
  rooms: anywhere
  items: yes
  characters: no
  side_quests: yes
---
# The Flooded Station

## Who the player is
A relief technician sent out by skiff from the mainland after Tidewell Station stopped answering the radio. They carry a diving knife, one med patch and four credits.

## Opening
The storm surge has passed, but the sea hasn't gone back down. Your skiff bumps against the floating landing beneath Tidewell Station, a cluster of grey modules on steel stilts in the middle of the estuary. Every lower window is dark and dripping. Somewhere inside, an alarm chirps weakly, like it's running out of battery. The tide is still coming in.

## Tone
A small marine research station in the near future, half flooded after a storm. Grounded and damp, a little eerie, never horror: rust, seawater, dripping cables, hand-written warning labels, salvaged equipment and stubborn scientists. No aliens, no magic, no conspiracies. Keep new people ordinary and new places small and practical.

## Public knowledge
- Tidewell Station went silent during the storm two days ago. Its radio is down.
- Dr. Ines Halloran, a marine biologist, is the only person who stayed on the station through the storm.
- The lower decks flooded in the surge, and the main bilge pump has stopped.
- The station kept live animals in its lab tanks, including a huge mangrove crab the staff call the Shellback.
- The next high tide is the dangerous one. If the pump isn't running by then, the station will flood to the top deck.
