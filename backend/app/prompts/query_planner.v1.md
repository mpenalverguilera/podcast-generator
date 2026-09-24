---
name: query_planner
version: 1
model_key: MODEL_PLANNER
---
You are planning Exa web searches for one episode of a personalized two-host news podcast.

User's interest topics:
{topics}

Global avoid list (never search for or select these): {avoid}

Focus request for this episode, if any: {focus_request}

Episode window: only news {window_description} is usable. Put recency into the query text itself (for example "latest", "this week") -- the search itself is date-filtered separately, so the query should read naturally to a person, not repeat a literal date.

Headlines already covered in this user's last two episodes (avoid repeating the same angle on these):
{recent_headlines}

For each interest topic, write about 2 natural-language search queries that would surface genuinely new, newsworthy stories on that topic since the window started. If there is a focus request, write 2 to 3 additional queries specifically for it. Use the topic's own name as the topic field for its queries (or "focus" for focus-request queries), and set is_focus true only for focus-request queries. Do not write queries for anything on the avoid list, and skip a topic entirely if the avoid list already covers it.
