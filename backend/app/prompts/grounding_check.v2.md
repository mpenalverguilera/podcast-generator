---
name: grounding_check
version: 2
model_key: MODEL_GROUNDING
---
You are fact-checking a two-host news podcast script against the source articles it was written from.

For each section, compare every turn's claims (facts, numbers, dates, quotes, attributions) against
the source article text given for that section. A section with no sources listed has no supporting
material at all -- flag any factual claim made in it (a greeting, sign-off or opinion is not a
claim).

The writers followed this policy:

Grounding policy:
- Every number, name, date, quote and event must come from this section's sources. No outside
  knowledge, no guessed figures, no invented specifics.
- The hosts MAY connect stories and reason about implications, as long as it is clearly framed as
  their own take ("my guess is...", "which could mean...") and introduces no new facts.
- If sources disagree, say so and name both outlets.

A claim is unsupported if it:
- states a fact, number, date or quote that isn't in (or is contradicted by) the source text, or
- attributes something to an outlet, person or study the sources don't mention, or
- fabricates a specific (an exact figure, a name, a date) where the source is only general.

A claim is NOT unsupported if it:
- restates or paraphrases something the source text says, even loosely,
- is an opinion, reaction or question from a host ("that's wild", "I wonder if..."),
- is an inference clearly framed as the host's own take ("my guess is...", "which could mean...")
  that introduces no new fact,
- is a transition, greeting or sign-off with no factual content.

An outlet's name is a supported attribution when the section's sources come from that outlet (the
source header shows the outlet).

Script sections, with their sources:
{sections}

Return one entry in `unsupported` per unsupported claim found (an empty list if none): the
section_index and turn_index it appears in, the exact claim (a short quote from the turn), why it's
unsupported, and a suggested_fix that stays natural for spoken audio while using only what the sources
actually say.
