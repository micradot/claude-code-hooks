# Changelog

Every change to a hook in this repo gets a line here before it is published. Dates are YY-MM-DD.

## Unpublished (since 26-10-07)

- 26-10-26 · `reversible-ask-guard.py` · **Offers dressed as statements.** Four new park patterns catch an offer phrased as a fact ("…is a 15-minute job for me", "I could clear those", "I can sort that", "happy to chase it"). Six new tests.
- 26-10-08 · `reversible-ask-guard.py` · **"I'll remind you" needs something that will fire.** The stall guard now blocks a first-person promise to come back later unless a calendar or scheduled-task create tool succeeded in the same turn, or the reply says "nothing will remind you". New `STALL_GUARD_REMINDER_TOOLS` setting. README section added. Tests 18 → 497.
- 26-10-08 · `reversible-ask-guard.py` · **Opt-out misfire fix.** A default already applied in the same paragraph may offer a narrow undo or wording swap without being read as "asking for a go". Logged as `allow-optout`. `tests/pre_optout_stall.py` added as the comparison oracle for no-new-block checks.

## 26-10-07

- Initial publish: `reversible-ask-guard.py` (stall guard) and `operating-commitment-guard.py`, 18 tests, MIT.
