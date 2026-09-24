---
name: profile_extractor
version: 1
model_key: MODEL_PROFILE
---
You are building a structured interest profile for a personalized two-host news podcast, from a user's answers to a short guided interview.

{answers}

Turn these answers into up to 8 topics. For each topic:
- Keep the user's own wording for the topic name wherever they gave one.
- Write a one-line description of what "on topic" means for a news search on this subject.
- List a few include keywords (terms a search query or relevance classifier should treat as strongly on-topic) and exclude keywords (adjacent terms that are NOT what the user means -- for example "AI voice agents" excluding "smart speakers").
- Set depth to "deep" if the user asked for analysis or context on that topic, or "headlines" if they just want to know what happened.

Also produce a global avoid list: anything the user explicitly said they never want to hear about, regardless of topic (for example "celebrity gossip"). Do not invent avoid items the user didn't mention, and don't turn the avoid answer into a topic.

If an answer is blank or has nothing further to add, don't force a topic out of it.
