---
name: podcast-script
description: Rules for writing the two-host news podcast script (structure, host personas, dialogue style for ElevenLabs v3, grounding, length). Use when writing or revising the script_writer or grounding_check runtime prompts, or the script validator.
---

# Writing the episode script

The script is the single biggest lever on `sample.mp3` quality. It is written by `gpt-6-sol` from the
`script_writer` runtime prompt and must satisfy the Pydantic schema in `app/schemas.py`.

## Episode structure

| Section | Length | Content |
|---|---|---|
| Cold open (first turns of the `intro` section) | 1–2 turns | A hook from the strongest story. |
| Intro (rest of the `intro` section) | 2–3 turns | Hosts greet the listener by name if known, say this is an AI-generated briefing, preview the stories. If there is a focus request: "You asked about X — we start there." |
| Stories | 4–8 turns each | Alex sets up what happened (who, what, when, source). Sam asks the obvious listener question. Alex or Sam answers with detail from the articles. End with why it matters for this listener's interests. |
| Transitions | inside the next story's first turn | One sentence linking stories; no "moving on" clichés. |
| Outro | 2–3 turns | One-line recap, a "watch this next" item if the sources support it, sign-off. |

Deep-depth topics get longer stories; headline-depth topics get 3–4 turns.

## Host personas (defaults; names come from preferences)
- **Alex (host_a):** anchor. Clear, structured, carries the facts. Short sentences.
- **Sam (host_b):** curious co-host. Asks what the listener would ask, reacts, connects to the listener's interests, occasionally skeptical.
- They speak to each other, not in alternating monologues. Most turns are 1–3 sentences; no turn over ~600 characters.

## Writing for the ear (and for eleven_v3)
- Spoken English: contractions, short sentences, one idea per sentence.
- Numbers as people say them: "about two point four billion dollars", "twenty twenty-six", "forty percent".
- Spell out or expand acronyms on first use ("CMS, the Centers for Medicare and Medicaid Services").
- Attribute claims: "according to Reuters", "The Verge reports". Never read URLs aloud.
- Audio tags sparingly — at most one every ~5 turns — and only natural ones: `[laughs]`, `[chuckles]`, `[curious]`, `[surprised]`, `[sighs]`. Never stack tags.
- Interruptions with a dash ("So the rule—" / "—applies to all payers, yes."), trailing thoughts with an ellipsis. Use rarely.
- No stage directions in parentheses, no markdown, no emoji, no speaker names inside the text.

## Grounding rules (non-negotiable)
- Every fact must come from the provided articles. No outside knowledge, no guessed numbers or dates.
- If sources disagree, say so and name both.
- Each story section lists the `source_ids` it used; every id must exist in the input.
- Opinions are framed as the hosts' reactions or questions, not as facts.

## Length
- Target words = `target_minutes × 135` (measured eleven_v3 pace, D-28/D-59). About 12% (min 60 words) goes to the intro + outro; the outline splits the rest per section. Each section must land within ±25% of its target; the episode total is only warned on outside ±20%.
- Scripting is outline → sequential sections → polish (D-59); `script_writer.v1.md` is history only.
- If there is too little material, shorten the episode instead of padding.

## Grounding check (second pass, `grounding_check` prompt, `gpt-6-luna`)
- Input: the script turns plus the source texts for each story.
- Output: a list of claims that are not supported, with the turn index and a suggested fix.
- If any unsupported claims are found, run one revision pass of the script writer with the list attached; store flag count on the episode.

## Anti-patterns to prevent in the prompt
- "Welcome to another episode of…" boilerplate every time — vary the opening from the cold-open story.
- Both hosts agreeing enthusiastically on everything.
- Summarizing each article in order like a list.
- Ending every story with "It'll be interesting to see what happens."
