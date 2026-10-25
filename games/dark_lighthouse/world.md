---
title: The Dark Lighthouse
start_room: harbor_square
stats:
  max_hp: 12
  might: 1
  agility: 1
  wits: 1
# rolled fresh each new game; these replace the fixed stats above
rolls:
  max_hp: 2d3+8
  might: 1d2
  agility: 1d3-1
  wits: 1d3-1
coins: 3
inventory:
  - worn_dagger
  - healing_tonic
equipped: worn_dagger
# what one person learns or goes through, kept for each person apart; every other flag is shared
personal_flags: lamp_quest_started, mirror_cursed, tongue_salted
# each line picks one of its flags at random when a new game starts
variants:
  craving: craves_honey, craves_fish
  cutlass_spot: cutlass_in_nets, cutlass_in_tavern
  tonic_spot: tonic_in_hollow, tonic_on_road
# counts down one per move; when it runs out the flag is set
clock:
  name: The fleet comes home
  moves: 2d6+12
  flag: fleet_arrived
  # when it runs out, if this holds, also set:
  also_if: not lamp_lit
  also_flag: fleet_lost
weather:
  - a cold wind off the sea
  - a thin, needling drizzle
  - sea fog rolling in over the quay
  - a clear, starry sky
times:
  - dusk
  - nightfall
  - deep night
  - the small hours
# what the world agent may create during a run
generation:
  extras: yes
  rooms: anywhere
  items: yes
  characters: yes
  side_quests: yes
---
# The Dark Lighthouse

## Who the player is
A traveller who has just stepped off a small trading boat at the fishing village of Saltmere. They carry a worn dagger, a healing tonic, and three coins.

## Opening
It's dusk, and a cold wind is coming in off the sea. The boat that brought you is already pulling away. Above the village the lighthouse stands tall and completely dark. It has been dark for three nights, people say, and the fishing fleet is due home through the rocks any night now.

## Tone
A small, weathered fishing village on a cold northern coast. Folk-tale rather than grim: salt, rope, fish, lamplight, gossip and stubborn people. Magic is rare and never named. Nothing modern; nothing grand. Keep new people ordinary and new places small.

## Public knowledge
- The lighthouse has been dark for three nights, and Ysolde the keeper has barely left the tower.
- The fishing fleet is out and due home through the rocks soon. Without the light, boats will be wrecked.
- Pell runs the Gull, the tavern on the square.
- A troll lives under Greywater Bridge, east along the coast road. Folk leave it alone and it leaves them alone.
- Nobody knows who or what put the light out.
