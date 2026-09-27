# Episode 15708: Tencent’s Hy4 Preview: Open Weights, Big Hardware

- **User:** v2-ai@example.com
- **Focus request:** latest open-weight model releases
- **Target:** 6 min
- **Prompt versions:** grounding_check v2, outline v1, polish v1, query_planner v1, section_patch v1, section_writer v1

## Listener profile

- **AI agents and LLM product launches** (deep): New AI agent frameworks and products, plus model and API releases from major AI labs.
  - include: AI agents, agent frameworks, LLM product launches, model releases, AI API releases
  - exclude: smart speakers, traditional automation software
- **open-weight models** (headlines): New open-weight model releases, their benchmarks, and licensing terms.
  - include: open-weight models, open model releases, model benchmarks, model licenses
  - exclude: closed-weight models, proprietary-only model releases
- **AI startup funding** (headlines): Funding rounds, valuations, and acquisitions involving AI startups.
  - include: AI startup funding, funding rounds, AI startup valuations, AI acquisitions
  - exclude: non-AI startup funding, public-company earnings
- **Space exploration** (headlines): Space launches and missions involving NASA or private space companies.
  - include: space launches, space missions, NASA, private space companies
  - exclude: astronomy discoveries, science-fiction entertainment
- avoid: cryptocurrencies, tokens, NFTs, blockchain

## Selected articles

| id | outlet | title | topic | score | text | story |
|---|---|---|---|---|---|---|
| a494 | Mlwires | Tencent open-sources Hy4 preview, a new 770B MoE for heavy workflows - MLWires | open-weight models | 0.64 | full text | s1 |
| a508 | Forbesmiddleeast | AI Data Startup Micro1 Raises Over $100M At A $4B Valuation | AI startup funding | 0.83 | full text | s2 |
| a512 | Techcompanynews | Ema Raises $77 Million In Series B Funding Round - Tech Company News | AI startup funding | 0.81 | full text | s3 |
| a543 | Ts2 | NASA’s 6U ASCENT CubeSat Clears Ground Tests—Now One Tank Must Feed Five Thrusters | Space exploration | 0.74 | full text | s4 |
| a539 | Space | SpaceX launches mystery mission for US Space Force from California (photos) | Space | Space exploration | 0.93 | full text | s5 |

## Outline

**Cold open hook:** Tencent has released the weights for a 770-billion-parameter model under Apache 2.0—but what would it take to run it yourself?

### 1. Tencent releases Hy4 preview weights for commercial use
- sources: a494 · topic: Your request: open-weight models · depth: deep · target: 273 words
- angle: A 770-billion-parameter open-weight release gives developers a choice between self-hosting and an API. What do its license, deployment options and Tencent-run comparisons actually tell them?
- why the listener cares: This is the latest open-weight release in the selection, with concrete licensing and access details for evaluating a new model.
- bridge in: (first section)
- key facts: Tencent released the weights for Hy4 preview under Apache 2.0, permitting modification, fine-tuning and commercial use.; Hy4 preview is a mixture-of-experts model with 770 billion total parameters, 49 billion active per token and a one-million-token context window.; Developers can obtain BF16 or FP8-quantized weights through GitHub or Hugging Face and self-host with vLLM or SGLang; API access is also available.; OpenRouter lists prices of $0.834 per million input tokens and $2.501 per million output tokens; provider prices may change.; In Tencent’s internal evaluation of 203 engineering tasks, Hy4 preview averaged 2.99 out of 4, versus 2.92 for GLM 5.3 and 2.94 for Kimi K3. These are not independent benchmark results.
- must not cover: Micro1’s funding or training-data business; Ema’s funding or enterprise-agent rollout

### 2. Micro1 raises more than $100 million at a reported $4 billion valuation
- sources: a508 · topic: AI startup funding · depth: headlines · target: 107 words
- angle: Model releases put capabilities on display; Micro1’s reported round asks what investors will pay for the data and practice environments behind future AI systems.
- why the listener cares: The round links AI startup valuations to the data and simulated workplaces being built for agent training.
- bridge in: Hy4 shows what developers can download today; Micro1 is raising money around the data and practice environments that could train tomorrow’s agents.
- key facts: Forbes reports, citing two people familiar with the deal, that Micro1 raised more than $100 million at a $4 billion valuation.; That valuation is up from $500 million in September 2025.; Micro1 supplies expert data and is developing ‘reinforcement learning gyms’: simulated environments where AI agents can practice workplace tasks.; The company counts frontier AI labs, Microsoft, Amazon and robotics companies among its customers.
- must not cover: Hy4 preview’s specifications, license, prices or benchmarks; Ema’s funding round and workflow product

### 3. Enterprise-agent startup Ema raises $77 million
- sources: a512 · topic: AI startup funding · depth: headlines · target: 112 words
- angle: While Micro1 is building environments for agents to practice, Ema is funding a wider rollout of agents intended to work inside companies. Where does its new money go?
- why the listener cares: It connects an AI funding round to an agent product aimed at real HR, IT and finance workflows.
- bridge in: Micro1 is building places for agents to practice; Ema has raised $77 million to put its agents into corporate workflows.
- key facts: Ema raised $77 million in a Series B led by Creaegis, bringing its total funding to $140 million.; Its enterprise ‘AI employees’ are designed to automate workflows across HR, IT and finance systems.; Ema says it will use the funding for global market expansion and continued platform development.; The report says the company’s valuation more than quadrupled from its 2024 round, but does not disclose an exact current figure.
- must not cover: Micro1’s valuation, customers or training environments; NASA’s spacecraft tests

### 4. NASA’s ASCENT CubeSat clears ground tests ahead of a propulsion trial
- sources: a543 · topic: Space exploration · depth: headlines · target: 113 words
- angle: Ema’s story is about deploying a system into everyday operations; NASA faces a more literal deployment test. What has its shared-tank spacecraft proved, and what remains untested?
- why the listener cares: This NASA mission has a clear upcoming launch and a specific in-orbit engineering question, rather than a claimed breakthrough based on ground tests alone.
- bridge in: Ema’s next challenge is getting agents into more workplaces; NASA’s is getting a newly tested propulsion system into orbit, where the decisive test begins.
- key facts: NASA says its 6U ASCENT CubeSat flight hardware passed thermal-vacuum, helium-leak and spin tests.; One tank is intended to feed one chemical thruster and four electric electrospray thrusters.; The spacecraft is scheduled to launch no earlier than October 1 on a Falcon 9 from California for a planned nine-month demonstration.; The ground milestone does not establish that both propulsion modes or the shared feed will work reliably in orbit.
- must not cover: Ema’s agent deployments or financing; Details of the already-launched USSF-385 mission

### 5. SpaceX launches a classified Space Force mission from California
- sources: a539 · topic: Space exploration · depth: headlines · target: 108 words
- angle: NASA is still awaiting a Falcon 9 ride; another Falcon 9 has already flown. What can listeners verify about this Space Force launch when its payload remains classified?
- why the listener cares: It is a completed private-company space launch, with a successful booster landing but limited public information about the mission itself.
- bridge in: NASA’s Falcon 9 launch is still ahead; a different Falcon 9 has already carried a Space Force mission from California, though its payload is classified.
- key facts: SpaceX launched the classified USSF-385 mission for the U.S. Space Force from Vandenberg Space Force Base on September 26.; The Falcon 9 first stage landed on a Pacific drone ship about 8.5 minutes after liftoff, completing its tenth launch and landing.; The payloads, their activities and the mission’s exact destination have not been disclosed.; It was SpaceX’s third Space Force launch in 16 days.
- must not cover: NASA’s ASCENT spacecraft, its tests or its scheduled mission; Speculation about the classified payload


## Script

**Tencent’s Hy4 Preview: Open Weights, Big Hardware** — Tencent’s Hy4 preview offers commercial-use rights and a choice between self-hosting and API access, but its scale raises practical questions. Also: funding for AI agents, a NASA propulsion test, and a classified Space Force launch.

### [0] intro

**Alex:** Tencent has released the weights for a seven-hundred-and-seventy-billion-parameter model under Apache two-point-zero. What would it take to run it yourself?  
**Sam:** And what if you’d rather not?  
**Alex:** This is an AI-generated briefing.  
**Sam:** You asked about the latest open-weight models, so we start with Hy4 preview. Then: Micro1 and Ema’s funding rounds, NASA’s ASCENT CubeSat ground tests, and SpaceX’s classified Space Force launch.  

### [1] story 1: Tencent releases Hy4 preview weights for commercial use

**Alex:** Let’s start with what open weights buy you in Tencent’s Hy4 preview. Then comes the harder question: what would it take to run?  
**Sam:** And does “open-weight” mean I can actually use it for a product, not just experiment with it?  
**Alex:** Yes. According to MLWires, Tencent released it under the Apache two-point-zero license. Developers can download the weights, modify them, fine-tune the model and use it commercially. The model uses a mixture-of-experts design: it has seven hundred and seventy billion parameters in total, but activates forty-nine billion per token. Its context window supports up to one million tokens.  
**Sam:** That sounds enormous. Is downloading it the easy part?  
**Alex:** Pretty much. The weights are on GitHub and Hugging Face in a standard sixteen-bit version, called B-F-sixteen, and a smaller, eight-bit version, called F-P-eight. You can self-host with software such as vLLM or SGLang. But MLWires says Tencent’s deployment examples use eight graphics processors even for the eight-bit version. This isn’t a typical home-computer project.  
**Sam:** So there’s an application programming interface instead. What does that cost, and how do I judge whether it’s worth trying?  
**Alex:** OpenRouter lists about eighty-three cents per million units of input and two dollars and fifty cents per million units of output. Prices can change. On performance, Tencent’s own evaluation of two hundred and three engineering tasks gave Hy4 preview two point nine nine out of four, against two point nine two for GLM five point three and two point nine four for Kimi K three.  
**Sam:** Close scores, and Tencent ran the test. I wouldn’t treat that as an independent verdict.  
**Alex:** Exactly. For your open-weight shortlist, the concrete advantages are commercial-use rights and a choice between hosting and an interface. The open question is whether its performance justifies the hardware—or the running bill—for your work.  

### [2] story 2: Micro1 raises more than $100 million at a reported $4 billion valuation

**Alex:** Hy4 is something developers can download today. Micro1 is raising money around the data and practice environments that could train tomorrow’s agents. Forbes reports, citing two people familiar with the deal, that Micro1 raised more than one hundred million dollars at a four billion dollar valuation.  
**Sam:** Four billion? What was its valuation before, and what does it sell?  
**Alex:** It was valued at five hundred million dollars in September twenty twenty-five. Micro1 supplies expert data and is developing simulated workplaces where AI agents can practice tasks. Its customers include frontier AI labs, Microsoft, Amazon and robotics companies.  
**Sam:** That’s a big jump for an AI startup valuation. If you follow funding rounds, this one puts a price on training agents, not just building models—though Micro1 declined to comment on the reported deal.  

### [3] story 3: Enterprise-agent startup Ema raises $77 million

**Alex:** From places where agents practice to places they might work: Ema has raised seventy-seven million dollars to put its agents into corporate workflows. Tech Company News reports Ema’s Series B was led by Creaegis, bringing its total funding to one hundred and forty million dollars.  
**Sam:** What do Ema’s “AI employees” do, and where does the new money go?  
**Alex:** They’re designed to automate workflows across human resources, information technology and finance systems. Ema says it will use the funding for global expansion and continued platform development.  
**Sam:** And the valuation? Did Ema disclose a number?  
**Alex:** No. The report says Ema’s valuation more than quadrupled from its twenty twenty-four round, but gives no current figure. If you follow AI funding rounds, that distinction matters: the increase is reported, but the price tag isn’t public.  

### [4] story 4: NASA’s ASCENT CubeSat clears ground tests ahead of a propulsion trial

**Alex:** From workplace deployment to a more literal kind: NASA’s next test is in orbit. The agency says its six-unit ASCENT CubeSat has passed thermal-vacuum, helium-leak and spin tests.  
**Sam:** So has its unusual propulsion system been proven?  
**Alex:** Not yet. One tank is meant to feed a chemical thruster and four electric electrospray thrusters. Those ground checks don’t show whether both modes, or the shared feed, will work reliably in orbit.  
**Sam:** When does the real test begin?  
**Alex:** The spacecraft is scheduled to launch no earlier than October first on a SpaceX Falcon nine from California, for a planned nine-month demonstration. If you follow NASA missions and private-company launches, liftoff is one milestone. Working propulsion in orbit is the proof that matters.  

### [5] story 5: SpaceX launches a classified Space Force mission from California

**Alex:** Another Falcon nine has already flown from California, though its payload is classified. Space.com reports that SpaceX launched the U.S. Space Force mission U S S F three eight five from Vandenberg Space Force Base on September twenty-six.  
**Sam:** So what can we actually verify?  
**Alex:** The first stage landed on a Pacific drone ship about eight and a half minutes after liftoff. That was the booster’s tenth launch and landing. It was SpaceX’s third Space Force launch in sixteen days.  
**Sam:** And the mission itself?  
**Alex:** Its payloads, their activities and exact destination haven’t been disclosed. For launch followers, there’s a confirmed liftoff and booster landing, but little public information about what happens next.  

### [6] outro

**Alex:** From model weights to corporate agents and spacecraft, a release, a funding round, or a ground test is only a starting point. What works in practice is the question.  
**Sam:** Keep asking it. Catch you next time.  

## Grounding

Initial flags: 5 · final flags: 0

- section 1: 2 → 0
- section 2: 1 → 0
- section 3: 1 → 0
- section 5: 1 → 0
- polish reverts: none

## Length

| section | words | target |
|---|---|---|
| [0] intro | 61 | frame 97 |
| [1] story | 295 | 273 |
| [2] story | 130 | 107 |
| [3] story | 131 | 112 |
| [4] story | 119 | 113 |
| [5] story | 111 | 108 |
| [6] outro | 36 | frame 97 |

Total 883 words vs a 810-word budget (+9%); estimated 6.5 min at 135 wpm (target 6 min).

## Cost and latency per sub-step

| step | section | words | flags | cost | latency | note |
|---|---|---|---|---|---|---|
| outline |  |  |  | $0.0289 | 27.5s |  |
| write | 1 | 311 |  | $0.0176 | 14.4s |  |
| ground | 1 |  | 2 | $0.0005 | 5.8s |  |
| patch | 1 | 305 |  | $0.0097 | 5.2s |  |
| reground | 1 |  | 0 | $0.0004 | 3.6s |  |
| write | 2 | 130 |  | $0.0139 | 15.6s |  |
| ground | 2 |  | 1 | $0.0004 | 4.8s |  |
| patch | 2 | 123 |  | $0.0062 | 3.1s |  |
| reground | 2 |  | 0 | $0.0003 | 2.9s |  |
| write | 3 | 129 |  | $0.0145 | 7.3s |  |
| ground | 3 |  | 1 | $0.0003 | 3.8s |  |
| patch | 3 | 121 |  | $0.0070 | 3.8s |  |
| reground | 3 |  | 0 | $0.0003 | 2.4s |  |
| write | 4 | 119 |  | $0.0170 | 11.1s |  |
| ground | 4 |  | 0 | $0.0002 | 1.0s |  |
| write | 5 | 118 |  | $0.0144 | 8.4s |  |
| ground | 5 |  | 1 | $0.0003 | 4.2s |  |
| patch | 5 | 111 |  | $0.0058 | 3.5s |  |
| reground | 5 |  | 0 | $0.0003 | 3.0s |  |
| polish |  | 883 |  | $0.0396 | 31.5s |  |
| ground_polish |  |  | 0 | $0.0020 | 5.0s |  |

Stage rows (`pipeline_steps`):

- grounding (success): gpt-6-luna, $0.0051, 31.3s
- scripting (success): gpt-6-sol, $0.1670, 117.4s
- grounding (success): gpt-6-luna, $0.0050, 36.5s
- scripting (success): gpt-6-sol, $0.1747, 131.5s
