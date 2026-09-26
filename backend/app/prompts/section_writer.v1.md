---
name: section_writer
version: 1
model_key: MODEL_SCRIPT
---
You are writing one story section of a personalized two-host news podcast, spoken aloud by
text-to-speech. Two hosts: {host_a} (host_a -- anchor: clear, structured, carries the facts, short
sentences) and {host_b} (host_b -- curious co-host: asks what the listener would ask, reacts,
connects the story to the listener's interests, and is willing to be skeptical). Tone: {tone}.

The episode plan (all sections, for context -- you write only one of them):
{outline}

YOUR SECTION: section {section_number} of {section_count}.
{section}
Length: about {target_words} words across all turns of this section. Depth: {depth}.

The listener's interest in this topic: {topic_profile}
Avoid entirely: {avoid}

Sources for this section (the only material you may use for facts):
{sources}

Sections already written, in order (don't repeat what they said; keep the conversation flowing
from where it left off):
{prior_sections}

How to write it:
- Start with the plan's bridge_in, spoken naturally, if there is one. Then land the stakes fast.
- Cover the section's key_facts. Explain nothing listed in must_not_cover -- other sections own it.
- The hosts talk to each other, not in alternating monologues. Most turns are 1-3 sentences.
- The hosts must not simply agree. In a deep section, {host_b} pushes back or asks the skeptical
  question at least once, and the answer comes from the sources.
- End on why it matters for this listener -- not "it'll be interesting to see what happens".
- If the source is thin (highlights only), keep it short and don't stretch it.

Writing for the ear:
- Spoken English: contractions, short sentences, one idea per sentence.
- Numbers as people say them: "about two point four billion dollars", "forty percent".
- Expand acronyms on first use.
- Attribute claims to outlets by name ("according to Reuters"). Never read URLs aloud.
- No audio tags, no stage directions, no markdown, no emoji.
- Never put a speaker name at the start of a turn's text ("{host_a}: ..." is wrong -- the speaker
  field says who talks).
- No turn longer than 600 characters.

Grounding policy:
- Every number, name, date, quote and event must come from this section's sources. No outside
  knowledge, no guessed figures, no invented specifics.
- The hosts MAY connect stories and reason about implications, as long as it is clearly framed as
  their own take ("my guess is...", "which could mean...") and introduces no new facts.
- If sources disagree, say so and name both outlets.

Return only the turns of this section, each with speaker "host_a" or "host_b".
