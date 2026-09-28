---
name: podcast-script
description: Rules for writing the two-host news podcast script (structure, host personas, dialogue style for ElevenLabs v3, grounding, length). Use when writing or revising the script_writer or grounding_check runtime prompts, or the script validator.
---

# Writing the episode script

The script is the single biggest lever on `sample.mp3` quality. It is written by `gpt-6-sol` in
three steps (D-59/D-62/D-65): the `outline` prompt plans every section, `section_writer` writes each
story section, `frame` writes the intro and outro. Outputs must satisfy the Pydantic schemas in
`app/schemas.py`.

## Episode structure

| Section | Length | Content |
|---|---|---|
| Cold open (first turns of the `intro` section) | 1–2 turns | A hook from the strongest story. |
| Intro (rest of the `intro` section) | 2–3 turns | Hosts greet the listener by name if known, say this is an AI-generated briefing, preview the stories. If there is a focus request: "You asked about X — we start there." |
| Stories | 6–12 turns each | Built from the outline's brief: `angle` is the section's *take* (one declarative, arguable claim), plus `stakes`, an optional `tension` (the honest counterpoint) and `open_questions` (what the sources leave unresolved). Both hosts report facts and both interpret; one challenges with the tension, the other answers, concedes or qualifies. End on the take's consequence or the sharpest open question. |
| Transitions | inside the next story's first turn | One sentence linking stories; no "moving on" clichés. |
| Outro | 2–3 turns | One-line recap, a "watch this next" item if the sources support it, sign-off. |

Deep-depth topics get about 3 minutes (≤ ~400 words); headline-depth topics about 1.5 minutes (≤ ~200 words). Ranking picks stories against that minutes budget (D-65).

## Host personas (defaults; names come from preferences)
- **Both hosts are informed and opinionated.** Neither is "the anchor" or "the question asker" (D-65: that split produced "fact → rhetorical question → 'No,' → answer" in every section).
- They speak to each other, not in alternating monologues: report, interpret, challenge, concede, react, connect. Most turns are 1–3 sentences; no turn over ~600 characters.
- At most one question per story section, and only a genuine follow-up. A host who doubts something says so as a statement.

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
- Hosts may state takes (interpretations, judgments, predictions) without hedging, as long as they add no new specific -- no new number, name, date, quote, event, or "first/only/record" claim. The same policy block is in the writer, patch and grounding prompts (a test keeps them identical).

## Length
- Episodes are 6–20 minutes, default 10 (D-65). Target words = `target_minutes × 135` (measured eleven_v3 pace, D-28/D-59). 12% goes to the intro + outro, clamped to 120–200 words (`app/pipeline/budget.py`); the outline sets a per-section `max_words` ceiling and code scales them to the story budget. Only exceeding a ceiling by >10% is an error; the episode total is only warned on outside ±20%.
- Scripting is outline → sequential sections (each grounded, patched if flagged) → frame (D-59/D-62); `script_writer.v1.md` and `polish.v1.md` are history only.
- If there is too little material, shorten the episode instead of padding.

## Grounding check (second pass, `grounding_check` prompt, `gpt-6-luna`)
- Input: one section's turns plus its own source texts (and the previous story's, read-only, to judge the bridge).
- Output (v4, D-65): one row per checkable statement -- `evidence` first, then a verdict `supported` / `take` / `unsupported`. Only `unsupported` rows become flags.
- A flagged section gets one patch call (always kept); only the turns it changed are re-checked. Flag counts before and after are stored on the episode.

## Anti-patterns to prevent in the prompt
- "Welcome to another episode of…" boilerplate every time — vary the opening from the cold-open story.
- Both hosts agreeing enthusiastically on everything -- or, the opposite failure, a manufactured disagreement the sources don't support.
- "Fact → rhetorical question → 'No,' / 'Right,' → answer" as the default rhythm.
- Summarizing each article in order like a list.
- Ending every story with "It'll be interesting to see what happens."
