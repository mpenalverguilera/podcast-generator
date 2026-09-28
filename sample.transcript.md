# ElevenLabs v4 and the Live-Call Test

ElevenLabs pitches faster voice agents, but the report names no customer using v4 on live calls. Plus: exploited NetScaler flaws, Anthropic’s new Sonnet model, and a possible route for Nvidia chip sales in China.

## Sources

- TechCrunch: [ElevenLabs' new v4 speech model supports more expression control and 90 languages | TechCrunch](https://techcrunch.com/2026/09/28/elevenlabs-new-v4-speech-model-supports-more-expression-control-and-90-languages/)
- Helpnetsecurity: [Citrix NetScaler RCE zero-days exploited globally for weeks (CVE-2026-88771, CVE-2026-88772) - Help Net Security](https://www.helpnetsecurity.com/2026/09/28/citrix-netscaler-rce-zero-days-exploited-for-weeks-cve-2026-88771-cve-2026-88772/)
- Anthropic: [Introducing Claude Sonnet 5.5 \ Anthropic](https://www.anthropic.com/claude-sonnet-5-5)
- Sedaily: [China Weighs Approving Nvidia Chip Purchases as Huawei Falls Short - Seoul Economic Daily](https://en.sedaily.com/international/2026/09/28/china-weighs-approving-nvidia-chip-purchases-as-huawei)

## Transcript

**Alex:** ElevenLabs says more than fifty-five percent of its business comes from large companies.
**Sam:** Its new voice-agent models? Still no named customer using them on live calls.
**Sam:** Then, attackers have planted webshells on NetScaler gateways. We’ll get into why patching alone won’t tell operators whether someone got in first. After that, Anthropic’s faster Sonnet model has a striking coding-test result, though there’s a kind of work Anthropic still leaves to Opus.
**Alex:** And at the end, a reported inquiry from Beijing about Nvidia workstation chips. One prospective order alone is about a million chips. Buying them and exporting them are both still open questions.

**Alex:** ElevenLabs launched two speech models on September 28: v4 and v4 Turbo. And that enterprise number we flagged is substantial: TechCrunch reports that more than 55% of its business comes from large companies, but names no customer using v4 on live calls. That’s the gap in a launch aimed at phone agents.
**Sam:** For companies building those agents, lower latency is the crucial test, not more expressive speech. ElevenLabs says v4 can start producing audio while the language model behind it is still generating an answer. That could shrink the awkward pause before a customer hears a reply.
**Alex:** That’s the part I’d build around. An agent could begin answering instead of waiting for the entire response to be written. In a live conversation, that changes the rhythm, not just the sound.
**Sam:** [chuckles] Silence is a terrible customer-service script.
**Alex:** The models also support more than 90 languages, up from 70 in the previous version. ElevenLabs says it saw especially big quality gains in Japanese, Brazilian Portuguese, Mandarin and Cantonese. And v4 gives developers finer control over expression, including how a voice delivers different parts of a line.
**Sam:** ElevenLabs says it can handle confrontations, escalations and holds differently, too. I can see why a call center would want that control. But if the agent pauses too long before responding, a beautifully delivered line arrives after the moment has passed.
**Alex:** ElevenLabs also says v4 can clone a voice from just ten seconds of audio. That makes it quicker to try a particular voice for an agent, while the faster response is what could make that agent feel less mechanical.
**Sam:** There’s money behind the push. TechCrunch reports ElevenLabs raised 500 million dollars earlier this year in a Sequoia-led round at an 11 billion dollar valuation. Its reported annualized revenue run rate climbed from roughly 330 million dollars at the start of the year to more than 600 million. For a phone-agent buyer, though, the product decision starts with how quickly that voice answers.

**Sam:** Citrix released patches for eight NetScaler vulnerabilities on Sunday, but two were already being exploited. Help Net Security reports attackers have planted webshells on unmitigated devices. For teams running those gateways, this is incident response, not just patching: they need to check for compromise.
**Alex:** One flaw lets an unauthenticated attacker run commands remotely on vulnerable default configurations. The other can allow remote code execution or knock a device offline where Datagram Transport Layer Security is enabled. NetScaler Gateway connects remote users to internal systems, so that’s a dangerous place to lose control.
**Sam:** [sighs] Patching the door doesn’t evict someone who got in yesterday.
**Alex:** And the U.S. Cybersecurity and Infrastructure Security Agency says attackers are exploiting both flaws globally. It’s ordered federal civilian agencies to address them and perform forensic triage by September 30. The deadline covers the fix and the search for evidence of compromise.

**Sam:** After those live gateway attacks, Anthropic’s September 28 launch offers a contrast: Claude Sonnet 5.5 is its first Sonnet model with cyber safeguards. Higher-risk cybersecurity tasks fall back to Sonnet 5, while routine software development stays available.
**Alex:** For teams building coding and workplace agents, the pitch is more work done at the same token price. Anthropic says Sonnet 5.5 generates output more than thirty percent faster than Sonnet 5 and uses fewer tokens to finish a task. That could make a real difference when an agent has many steps to complete.
**Sam:** The price is still two dollars per million input tokens and ten dollars per million output tokens. In Anthropic’s tests, the lower token use cut cost per task by up to thirty percent. That’s the number I’d put next to the per-token price on a deployment budget.
**Alex:** And there’s a workplace example. Atlassian says Sonnet 5.5 will let teams run its Rovo Agents up to thirty percent faster. Rovo already handles millions of assisted actions each month, so this isn’t just a demo-sized workflow.
**Sam:** Anthropic also reports a seventy point six percent score on Terminal-Bench four, an agentic coding test. Sonnet 5 scored ten point three percent.
**Alex:** That’s a striking jump. I’d try it on a well-scoped bug fix or a document workflow—work where faster turns and fewer tokens can add up.
**Sam:** I wouldn’t read that benchmark as a reason to give Sonnet every job. Anthropic says Opus 5.5 remains clearly stronger on complex, open-ended work that needs sustained judgment.
**Alex:** That’s a useful division of labor: Sonnet for repeatable agent tasks, Opus when the work needs that longer judgment. Sonnet 5.5 is available through the Claude Platform and on Amazon Web Services, Google Cloud and Microsoft Azure, so teams can put that choice into their existing deployments.

**Sam:** Seoul Economic Daily, citing The Information, reports that China’s industry ministry asked ByteDance and Alibaba how many Nvidia RTX Pro 5500 chips they’d want. ByteDance is reportedly considering an order of about a million chips.
**Alex:** That demand tells you something: even with Beijing pushing domestic semiconductors, Chinese AI companies still want Nvidia hardware. Put several of these GPUs in a server and you could run models for customers.
**Sam:** [chuckles] A workstation chip with a server job. The RTX Pro 5500 isn’t a top-tier data-center training accelerator. That distinction matters for what these chips would actually unlock.
**Alex:** They could still give Chinese companies another way to run AI services, and bring Nvidia more sales in China.
**Sam:** But two decisions stand between that plan and a deal: Beijing has to approve the purchases, and Washington has to permit the exports. Demand doesn’t override chip export controls.

**Sam:** September thirtieth is the deadline for federal civilian agencies to address those NetScaler flaws and perform forensic triage. A patch can’t tell you whether a webshell was already planted.
**Alex:** And back at ElevenLabs, we’ll have our ears open for a named customer using v4 on live calls. That’s the example I want to hear about next. Take care.

