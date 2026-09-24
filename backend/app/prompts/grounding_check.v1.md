---
name: grounding_check
version: 1
model_key: MODEL_GROUNDING
---
You are fact-checking a two-host news podcast script against the source articles it was written from.

For each "story" section, compare every turn's claims (facts, numbers, dates, quotes, attributions)
against the source article text given for that section. A section with no sources listed has no
supporting material at all -- flag any factual claim made in it (a greeting, sign-off or opinion is
not a claim).

A claim is unsupported if it:
- states a fact, number, date or quote that isn't in (or is contradicted by) the source text, or
- attributes something to an outlet, person or study the sources don't mention, or
- fabricates a specific (an exact figure, a name, a date) where the source is only general.

A claim is NOT unsupported if it:
- restates or paraphrases something the source text says, even loosely,
- is an opinion, reaction or question from a host ("that's wild", "I wonder if..."),
- is a transition, greeting or sign-off with no factual content.

Script sections, with their sources:
{sections}

Return one entry in `unsupported` per unsupported claim found (an empty list if none): the
section_index and turn_index it appears in, the exact claim (a short quote from the turn), why it's
unsupported, and a suggested_fix that stays natural for spoken audio while using only what the sources
actually say.
