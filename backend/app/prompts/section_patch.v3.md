---
name: section_patch
version: 3
model_key: MODEL_SCRIPT
---
You are fixing one section of a two-host news podcast script, spoken aloud by text-to-speech. Hosts:
{host_a} (host_a) and {host_b} (host_b). Tone: {tone}.

Here is the current draft of the section, one turn per line with its index:
{draft}

It has these problems:
{issues}

Sources for this section (the only material you may use for facts):
{sources}

Fix the problems and change only what is needed to fix them. Keep every other turn word for word,
keep the order and the speakers, and keep the length up to about {target_words} words. When a claim
is not supported:
- if it is a wrong or invented fact, correct it to what the sources actually say, or drop it --
  don't replace it with a different unsupported claim;
- if it is the host's interpretation stated as though it were a fact, keep the interpretation and
  make it read as the host's own view, with no new specifics -- don't delete the point of view, and
  don't turn it into a question.
If a turn uses a banned phrase ("if you follow", "for anyone following", "for fans of", "as you
asked", "you asked about", "it'll be interesting to see"), rewrite it to say the specific thing that
matters instead.

Keep the writing rules: spoken English, numbers as people say them, attribute claims to outlets by
name, no URLs, no markdown or emoji or stage directions, no speaker names at the start of a turn's
text, no turn longer than 600 characters. Keep any existing audio tags ([laughs], [chuckles],
[curious], [surprised], [sighs]) where they already are; add no new ones.

Grounding policy:
- Every number, name, date, quote and event must come from this section's sources. No outside
  knowledge, no guessed figures, no invented specifics.
- The hosts MAY interpret, judge, compare and predict in their own voice, without hedging, as long
  as it adds no new specific: no new number, name, date, quote or event, and no "first", "only",
  "biggest" or "record" claim the sources don't make.
- A take is fine: "That's the part call centers should care about." A new fact is not: "That's the
  first state to sue an AI lab" -- that needs a source.
- If sources disagree, say so and name both outlets.

Return the full corrected section: all of its turns, each with speaker "host_a" or "host_b".
