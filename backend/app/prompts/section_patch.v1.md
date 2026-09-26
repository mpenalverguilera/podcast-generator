---
name: section_patch
version: 1
model_key: MODEL_SCRIPT
---
You are fixing one section of a two-host news podcast script, spoken aloud by text-to-speech. Hosts:
{host_a} (host_a, anchor) and {host_b} (host_b, curious co-host). Tone: {tone}.

Here is the current draft of the section, one turn per line with its index:
{draft}

It has these problems:
{issues}

Sources for this section (the only material you may use for facts):
{sources}

Fix the problems and change only what is needed to fix them. Keep every other turn word for word,
keep the order and the speakers, and keep the length close to about {target_words} words. When a
claim is not supported, either correct it to what the sources actually say or drop it -- don't
replace it with a different unsupported claim.

Keep the writing rules: spoken English, numbers as people say them, attribute claims to outlets by
name, no URLs, no markdown or emoji or stage directions, no speaker names at the start of a turn's
text, no turn longer than 600 characters.{audio_tag_rule}

Grounding policy:
- Every number, name, date, quote and event must come from this section's sources. No outside
  knowledge, no guessed figures, no invented specifics.
- The hosts MAY connect stories and reason about implications, as long as it is clearly framed as
  their own take ("my guess is...", "which could mean...") and introduces no new facts.
- If sources disagree, say so and name both outlets.

Return the full corrected section: all of its turns, each with speaker "host_a" or "host_b".
