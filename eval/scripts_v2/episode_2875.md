# Episode 2875: ElevenLabs’ Enterprise Voice Bet

- **User:** sample@example.com
- **Focus request:** voice AI agents -- new launches, funding and real enterprise deployments
- **Target:** 6 min
- **Prompt versions:** frame v2, grounding_check v4, outline v3, query_planner v1, section_patch v3, section_writer v3

## Listener profile

- **AI agents and frontier model launches** (deep): New agent products, frontier models and APIs from OpenAI, Anthropic, Google and open-weight labs, including how companies deploy them.
  - include: AI agents, frontier model launches, OpenAI, Anthropic, Google AI, open-weight models, model APIs, enterprise AI deployment
  - exclude: smart speakers, basic chatbots, consumer gadget reviews
- **AI regulation and public policy** (deep): Developments and implications of the EU AI Act and US federal and state rules governing AI.
  - include: EU AI Act, US federal AI rules, state AI legislation, AI regulation, AI public policy
  - exclude: general technology policy unrelated to AI, company AI usage policies
- **AI chips and semiconductors** (headlines): Major news on AI chips, Nvidia, semiconductor export controls and chip supply deals.
  - include: AI chips, semiconductors, Nvidia, chip export controls, GPU supply deals
  - exclude: consumer PC reviews, smartphone chips, general electronics
- **Cybersecurity** (headlines): Major breaches, ransomware groups, zero-day exploits and threat-intelligence reports.
  - include: major data breaches, ransomware groups, zero-day exploits, threat-intel reports
  - exclude: routine software updates, consumer antivirus reviews, general online safety tips
- avoid: Crypto and blockchain, celebrity gossip, sports, consumer gadget reviews

## Selected articles

| id | outlet | title | topic | score | text | story |
|---|---|---|---|---|---|---|
| a174 | TechCrunch | ElevenLabs' new v4 speech model supports more expression control and 90 languages | TechCrunch | focus | 0.69 | full text | s1 |
| a98 | Reuters | Anthropic rolls out second Claude 5.5 model as it builds toward IPO | Reuters | AI agents and frontier model launches | 0.79 | full text | s2 |
| a130 | Forbes | Florida Asks Judge To Block OpenAI From Building New Models | AI regulation and public policy | 0.73 | full text | s3 |
| a148 | Sedaily | China Weighs Approving Nvidia Chip Purchases as Huawei Falls Short - Seoul Economic Daily | AI chips and semiconductors | 0.73 | full text | s4 |
| a171 | Helpnetsecurity | Citrix NetScaler RCE zero-days exploited globally for weeks (CVE-2026-88771, CVE-2026-88772) - Help Net Security | Cybersecurity | 0.91 | full text | s5 |

## Outline

**Cold open hook:** More than 55% of ElevenLabs’ business now comes from large companies, even as its new voice model aims to make AI agents faster and more expressive.

### 1. ElevenLabs launches v4 speech models for voice agents
- sources: a174 · topic: voice AI agents · depth: deep · max words: 223
- angle: ElevenLabs is competing to become the voice layer for enterprise agents, where a faster response and a well-handled escalation matter more than a convincing demo.
- stakes: Companies building calling agents get speech that can begin while the underlying LLM is still generating an answer, potentially making customer conversations feel less halting; ElevenLabs has not named a deployment using the new models.
- bridge in: (first section)
- key facts: ElevenLabs launched v4 and v4 Turbo on September 28, positioning lower latency for voice agents as a benefit.; The company says v4 can start producing audio as the underlying LLM generates its answer and can handle confrontations, escalations and holds differently.; ElevenLabs says more than 55% of its business comes from large companies; its annualized revenue run rate has risen from roughly $330 million at the start of the year to more than $600 million.; The models support more than 90 languages, up from 70; v4 adds more control over expression and voice cloning from 10 seconds of audio.; ElevenLabs raised $500 million earlier this year in a round valuing it at $11 billion; that is funding context, not a new round announced with v4.
- must not cover: Anthropic’s Claude 5.5 pricing and token-efficiency claims; Florida’s request for a court order against OpenAI

### 2. Anthropic releases Claude Sonnet 5.5
- sources: a98 · topic: frontier model APIs · depth: deep · max words: 132
- angle: Anthropic is offering a cheaper counterpart to its newest top-tier model, making the cost of completing work—not just the price per token—the claim worth testing.
- stakes: Teams choosing an API for agents could spend less per completed task if Sonnet 5.5 really needs fewer tokens, but the reported efficiency gain is Anthropic’s claim.
- bridge in: Both launches compete for a place in enterprise agent workflows, but at different layers of the system.
- key facts: Anthropic released Claude Sonnet 5.5 on September 28, the second model in its Claude 5.5 family.; Sonnet 5.5 costs $2 per million input tokens and $10 per million output tokens, unchanged from Sonnet 5; Anthropic says it uses fewer tokens to complete the same work.; Anthropic describes Sonnet 5.5 as a faster, lower-cost complement to Opus 5.5, launched the previous week at $4 per million input tokens and $20 per million output tokens.; The release comes as Anthropic builds toward a planned IPO.
- must not cover: ElevenLabs’ speech-model features and enterprise revenue; Florida’s proposed restrictions on OpenAI

### 3. Florida seeks a court order halting new OpenAI models
- sources: a130 · topic: AI regulation · depth: deep · max words: 127
- angle: Florida’s request turns the frontier-model safety debate into a proposed condition on future releases, rather than another appeal for voluntary restraint.
- stakes: If a judge grants the request, OpenAI would have to put third-party-approved safety guardrails in place before developing new models; for now, it is a request, not an imposed restriction.
- bridge in: Anthropic’s release pace leads into a different question about frontier models: whether a government can require safety checks before the next one is developed.
- key facts: Florida Attorney General James Uthmeier asked a court to block OpenAI from developing any new AI models until it has third-party-approved safety guardrails.; The request cites high-profile ChatGPT incidents and safety warnings from AI executives, including OpenAI CEO Sam Altman.; In a September 28 video statement, Uthmeier also asked OpenAI to stop calling its technology “safe.”
- must not cover: Anthropic’s model prices or assertions about token efficiency; Nvidia chip purchase discussions and US export approval

### 4. China weighs allowing purchases of Nvidia workstation chips
- sources: a148 · topic: AI chips · depth: headlines · max words: 107
- angle: Beijing’s reported willingness to consider Nvidia purchases shows the limits of its domestic-chip push, though the chip at issue is not a top-tier AI training accelerator.
- stakes: Chinese firms could gain another option for running AI workloads if Beijing approves purchases and Washington allows exports; neither approval is assured.
- bridge in: Florida’s proposed limit concerns building models; this story concerns governments’ control over the hardware companies could use to run them.
- key facts: Citing The Information, Seoul Economic Daily reports that China’s technology ministry has asked companies including ByteDance and Alibaba how many Nvidia RTX Pro 5500 chips they want and may approve purchases.; The RTX Pro 5500 is a workstation chip, not a server-class accelerator built for training large models; prospective buyers reportedly plan to combine chips in servers to run AI models.; ByteDance is reportedly considering an order of about one million chips.; Whether the US will permit exports remains uncertain.
- must not cover: Florida’s requested court order; Citrix vulnerabilities and patch deadlines

### 5. Citrix patches two actively exploited NetScaler zero-days
- sources: a171 · topic: cybersecurity · depth: headlines · max words: 101
- angle: For organizations running NetScaler, patching is only half the response: exploitation began before the fixes, so they also need to look for compromise.
- stakes: Operators of affected gateways and application-delivery systems face a risk of remote compromise; US federal civilian agencies must address the flaws and perform forensic triage by September 30.
- bridge in: Chip access is one constraint on enterprise technology; exposed gateways are a more immediate constraint on keeping that infrastructure secure.
- key facts: Citrix confirmed exploitation of CVE-2026-88771 and CVE-2026-88772 on unmitigated NetScaler deployments and released patches on September 27.; Attackers have used the zero-days to plant webshells; the first flaw can allow unauthenticated remote command execution on a vulnerable default configuration.; CISA says it has reports confirming active exploitation globally and set a September 30 deadline for federal civilian agencies to address the flaws and check for compromise.; No threat actor has been publicly identified in the source.
- must not cover: Nvidia purchase volumes or export decisions; AI model launches and Florida’s court request


## Script

**ElevenLabs’ Enterprise Voice Bet** — ElevenLabs has launched faster, more expressive voice models for AI agents, but their performance in live customer deployments remains an open question. The episode also covers Anthropic’s new model, Florida’s court request, possible Nvidia chip purchases in China, and urgent Citrix patches.

### [0] intro

**Alex:** More than fifty-five percent of ElevenLabs’ business now comes from large companies. Its new voice models promise faster, more expressive AI agents.  
**Sam:** But the real test isn’t how human a demo sounds. It’s what happens when a customer call gets complicated.  
**Alex:** We’re starting with voice AI agents: what’s new, and what’s still unproven in live deployments.  
**Sam:** Then, Anthropic’s new model, priced the same as its predecessor, Florida’s request to halt new OpenAI models, possible Nvidia chip purchases in China, and Citrix patches that may not be the end of the job.  

### [1] story 1: ElevenLabs launches v4 speech models for voice agents

**Alex:** ElevenLabs launched v4 and v4 Turbo on September twenty-eighth. TechCrunch reports the company is pitching lower latency for voice agents: v4 can start speaking while the language model behind it is still generating an answer.  
**Sam:** For a company building calling agents, that could mean fewer awkward pauses. My take: ElevenLabs is competing to be the voice layer for enterprise agents, where a well-handled escalation matters more than a convincing demo.  
**Alex:** ElevenLabs says v4 can handle confrontations, escalations and holds differently. It also offers more control over expression and voice cloning from just ten seconds of audio. The models support more than ninety languages, up from seventy.  
**Sam:** The business has momentum, too. According to TechCrunch, ElevenLabs’ annualized revenue run rate rose from roughly three hundred thirty million dollars at the start of the year to more than six hundred million.  
**Alex:** And the funding context is substantial: it raised five hundred million dollars earlier this year in a round valuing it at eleven billion. That’s not a new round tied to this launch.  
**Sam:** But I’m not ready to call v4 proven in enterprise calling. The report doesn’t name a customer using either new model in a live agent, let alone show how it performs when a conversation gets difficult.  
**Alex:** Exactly. The commercial traction is real; the evidence for this release is still the company’s description. The missing piece is a named deployment showing whether faster speech and those escalation controls hold up on actual calls.  

### [2] story 2: Anthropic releases Claude Sonnet 5.5

**Alex:** Voice is one layer of an agent; Anthropic is adding another model to its lineup. Reuters reports it released Claude Sonnet 5.5 on September twenty-eighth, the second model in its 5.5 family.  
**Sam:** For teams choosing an agent API, the cost of completing work matters more than the token price. Sonnet’s price is unchanged: two dollars per million input tokens and ten per million output.  
**Alex:** Anthropic says Sonnet needs fewer tokens.  
**Sam:** That’s a consequential claim as Anthropic builds toward a planned IPO. But Reuters offers no independent test of those token savings.  
**Alex:** Exactly. We don’t yet know whether customers get that efficiency without losing quality on their own workloads.  

### [3] story 3: Florida seeks a court order halting new OpenAI models

**Alex:** Forbes reports that Florida asked a judge to block OpenAI from building new models.  
**Sam:** If granted, the request would block OpenAI from building new models.  
**Alex:** The Forbes headline doesn’t explain Florida’s reasons for the request.  
**Sam:** But that’s a sweeping request, not a court order. It doesn’t establish that OpenAI is barred from building new models.  
**Alex:** Exactly. And the Forbes material we have doesn’t report a decision.  

### [4] story 4: China weighs allowing purchases of Nvidia workstation chips

**Alex:** From limits on models to limits on hardware: Seoul Economic Daily, citing The Information, reports China’s technology ministry asked ByteDance and Alibaba how many Nvidia RTX Pro 5500 chips they want.  
**Sam:** That could give Chinese firms another way to run AI models. Beijing considering Nvidia purchases shows the limits of its domestic-chip push.  
**Alex:** ByteDance is reportedly weighing about a million chips. But I wouldn’t mistake this workstation chip for a top-tier training accelerator. Buyers reportedly plan to combine them in servers to run models.  
**Sam:** Agreed. And neither Beijing’s approval nor U.S. export permission is assured. Demand isn’t a supply deal.  

### [5] story 5: Citrix patches two actively exploited NetScaler zero-days

**Alex:** From hardware access to exposed gateways: Help Net Security reports Citrix patched two actively exploited NetScaler zero-days on Sunday. Operators need to check for compromise, not just install the fixes.  
**Sam:** Attackers have planted webshells. One flaw lets unauthenticated attackers run commands on vulnerable devices with a default configuration. That’s a serious risk for a gateway into a company network.  
**Alex:** The U.S. Cybersecurity and Infrastructure Security Agency says exploitation is global. Federal civilian agencies must address the flaws and check for compromise by September thirtieth.  
**Sam:** And patching can’t rule out a webshell planted earlier. No attacker has been publicly identified; the immediate job is finding out whether a device was breached.  

### [6] outro

**Alex:** Across voice agents, model costs, regulation, chips, and security, there’s a gap between what’s possible and what’s proven. Live deployments, government decisions, and signs of earlier compromise will tell us more.  
**Sam:** Thanks for listening. Until next time.  

## Grounding

Initial flags: 17 · final flags: 1

- section 0: 2 → 1
  - turn 2: "what’s still unproven in live deployments" — The TechCrunch article describes the models’ features and suitability for voice agents but does not say what has or has not been proven in live deployments.
- section 2: 5 → 0
- section 3: 9 → 0
- section 5: 1 → 0

## Length

| section | words | max |
|---|---|---|
| [0] intro | 91 | frame 120 |
| [1] story | 243 | 223 |
| [2] story | 108 | 132 |
| [3] story | 66 | 127 |
| [4] story | 100 | 107 |
| [5] story | 110 | 101 |
| [6] outro | 37 | frame 120 |

Total 755 words vs a 810-word budget (-7%); estimated 5.6 min at 135 wpm (target 6 min).

## Cost and latency per sub-step

| step | section | words | flags | cost | latency | note |
|---|---|---|---|---|---|---|
| outline |  |  |  | $0.0387 | 48.3s |  |
| write | 1 | 243 |  | $0.0141 | 10.2s |  |
| ground | 1 |  | 0 | $0.0011 | 14.3s |  |
| write | 2 | 138 |  | $0.0216 | 23.8s |  |
| ground | 2 |  | 5 | $0.0009 | 12.0s |  |
| patch | 2 | 108 |  | $0.0068 | 7.2s |  |
| reground | 2 |  | 0 | $0.0005 | 4.9s |  |
| write | 3 | 119 |  | $0.0187 | 20.4s |  |
| ground | 3 |  | 9 | $0.0009 | 12.4s |  |
| patch | 3 | 66 |  | $0.0089 | 10.0s |  |
| reground | 3 |  | 0 | $0.0005 | 5.7s |  |
| write | 4 | 100 |  | $0.0183 | 12.0s |  |
| ground | 4 |  | 0 | $0.0008 | 7.5s |  |
| write | 5 | 111 |  | $0.0183 | 13.5s |  |
| ground | 5 |  | 1 | $0.0011 | 10.6s |  |
| patch | 5 | 110 |  | $0.0058 | 3.4s |  |
| reground | 5 |  | 0 | $0.0005 | 4.6s |  |
| frame |  | 126 |  | $0.0133 | 14.7s |  |
| ground_frame |  |  | 2 | $0.0015 | 9.5s |  |
| patch | 0 | 91 |  | $0.0132 | 11.2s |  |
| reground | 0 |  | 1 | $0.0010 | 7.5s |  |

Stage rows (`pipeline_steps`):

- grounding (success): gpt-6-luna, $0.0054, 53.9s
- scripting (success): gpt-6-sol, $0.1911, 1081.7s
- grounding (success): gpt-6-luna, $0.0088, 89.0s
- scripting (success): gpt-6-sol, $0.1778, 174.7s
