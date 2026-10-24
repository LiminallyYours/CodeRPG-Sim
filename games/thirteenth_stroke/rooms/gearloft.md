---
name: The Gearloft
exits:
  down: tock_tower
expand: no
work:
  stat: might
  pay: 1-3
terrain: indoors
---
The top of the tower is a dim, tilted room full of turning wheels. Some are as small as buttons and some as big as cart wheels, and they all tick and grind and nibble at one another with brass teeth. The back of the great clock face glows like a sick yellow moon, and the hands creep across it from the inside.

In the middle of everything turns the Great Gear, taller than a door, with teeth like a row of tombstones. Each time it clicks forward, the whole tower shudders. Something about it is grinning. The only way out is the ladder, down.

## If clock_stopped
An iron poker is wedged deep between the Great Gear's teeth. The wheels strain, creak and stay put. The clock's hands sit frozen a whisker before midnight.

## If thirteenth_stroke and not clock_stopped
The Great Gear has struck. The thirteenth stroke is still humming in the brass, and the whole room smells of something burnt.

## Details
- The Great Gear: it turns slowly, one tooth per tick, toward a big iron hammer poised over the bell. Ambrose's legend says it must never strike thirteen. Something stout and iron, jammed between its teeth, would stop it. The bent umbrella would just snap; it has to be iron.
- **Jamming the gear:** if the player carries `iron_poker` and tries to wedge it in, it takes a Might check to force it home (`check might 12`). On a success: `lose iron_poker`, then `flag set clock_stopped`. The wheels groan and stop, and the tower goes silent. On a failure, the gear bucks and pinches their fingers (`hurt 1d3`); the poker is still in their hand and they can try again, but each try costs time. Once `thirteenth_stroke` is set it's too late: the clock has struck, and jamming it now changes nothing (don't set the flag).
- The clock face: from behind, the numbers are backwards, and there is a thirteenth mark squeezed in between the eleven and the twelve that you can't see from the square.
- Small gears: they're slick with oil. Reaching in to touch them only gets oily fingers.
- The oil can: a big tin can and a rag hang on a nail by the ladder. The big wheels want oiling, and it's heavy work, heaving the can up and leaning into the teeth. Ambrose pays a few buttons to anyone who'll do it for him (`work`), since he can't climb up any more. Oiling isn't jamming: the Great Gear turns on regardless.
