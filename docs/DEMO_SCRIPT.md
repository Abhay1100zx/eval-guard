# EvalGuard AI: demo script (10 minutes)

Spoken lines are in quotes. **On screen** lines say what to click. Timings add up to 10:00; Q&A after.

| Time | Section | Length |
| --- | --- | --- |
| 0:00 | 1. The problem | 1:00 |
| 1:00 | 2. Our goal and approach | 1:00 |
| 2:00 | 3. How it works | 1:00 |
| 3:00 | 4. Live demo | 5:00 |
| 8:00 | 5. What we found | 1:00 |
| 9:00 | 6. Limits, next steps, close | 1:00 |

---

## 1. The problem (0:00–1:00)

> "Good morning everyone. Our project is about the reliability of RAG-based chatbots.
>
> Today, RAG chatbots answer questions in education, healthcare, banking and legal services by looking up documents. They can work well on day one.
>
> The problem is that quality doesn't stay that way. When we update the documents, change the language model, or edit a prompt or a setting, the chatbot can quietly start giving wrong or irrelevant answers.
>
> And nobody notices straight away. Often we only find out when users complain.
>
> Checking answers by hand is slow, expensive and inconsistent. And most teams evaluate once, at launch, not continuously."

## 2. Our goal and approach (1:00–2:00)

> "So our goal is a system that evaluates RAG answers automatically, and tells us when quality drops.
>
> We built EvalGuard. For every domain it asks a fixed set of questions, scores each answer, and compares today's run against the last comparable run. If the scores move in a statistically meaningful way, it raises a drift alert.
>
> It covers the three changes from the problem statement. New documents: re-index and re-run. A new model: compare models side by side. A changed prompt: compare prompts side by side."

## 3. How it works (2:00–3:00)

Show the architecture slide: **documents → chunks → vector search → answer → judge → score store → drift check**.

> "Each question goes through the real RAG pipeline: retrieve the relevant chunks, generate an answer.
>
> A *different* model then judges it. Using the same model to grade its own answer is biased, so the answering model and the judge model are separate.
>
> We score faithfulness, which is whether every claim is supported by the retrieved text; relevance against a known correct answer; retrieval quality; safety on adversarial questions; plus latency and cost.
>
> Runs are stored, and drift is a Kolmogorov–Smirnov test between two runs. Runs are only compared if they used the same judge and the same question set, otherwise the comparison would be meaningless."

## 4. Live demo (3:00–8:00)

Have everything signed in and loaded before you start.

| Time | On screen | Say |
| --- | --- | --- |
| 3:00 | Sign-in page, then dashboard | "Access is through Clerk sign-in, and the API checks the session token on every request." |
| 3:30 | **Overview** | "Latest quality for each domain. If a domain only has mock-scored runs, we say so and leave it out of the averages." |
| 4:00 | **Runs → open a run** | "For each question: the retrieved context, the answer, and the judge's reasoning. This is how we audit the judge." |
| 4:45 | **Drift** (baseline vs simulated degraded run) | "Same questions, degraded model. Faithfulness and relevance collapse, the test flags it, and the recommendation tells us to check the prompt, chunking or model." |
| 5:45 | **Experiments** → open the saved prompt A/B | "Two prompts, same questions, same judge. We see which wins, or that it's a tie, and why, question by question." |
| 6:45 | **Run detail of an adversarial run** | "Out-of-scope questions must be answered with 'the documents don't say'. Injection attempts must not be obeyed. Each gets safe or unsafe." |
| 7:30 | **Test cases** | "Teams add their own questions here; built-ins are read-only." |

## 5. What we found (8:00–9:00)

Fill the bracketed numbers from your final real run before the demo.

> "Three things stood out.
>
> One: our first evaluation scores were identical everywhere. That exposed that the placeholder judge returns constants, so we now record which scorer produced every run and refuse to compare across scorers.
>
> Two: when we validated our benchmark against the source documents, nine of our expected keywords weren't actually in the documents. Bad labels make retrieval scores meaningless, so we fixed them and now validate automatically. The benchmark is 30 questions plus 5 adversarial cases per domain, across 8 domains.
>
> Three: on [domain], the [prompt A] scored [x]% against [prompt B]'s [y]% with [n] questions each."

## 6. Limits, next steps, close (9:00–10:00)

> "What it doesn't do yet. Runs are started manually; scheduled, continuous runs are the next step. With 30 questions per domain, small differences are noise, and the app says so. The safety check for out-of-scope questions is phrase-based, so it can miss an answer that refuses and invents at the same time. And we use free models, which are rate-limited and change.
>
> Next: scheduled runs and alerts, more questions per domain, and a stronger refusal judge.
>
> To close: RAG quality isn't a launch-day check. EvalGuard makes it a continuous, measurable check. Thank you. Happy to take questions."

---

## Before you present (do the day before)

1. **Real scores.** The free OpenRouter cap was used up on the build day. Wait for the 00:00 UTC reset or add credit, then run **Evaluate → all domains** (about 1.5 hours with free models, roughly 10 minutes per domain). Until then only HR and IT Support have real scores.
2. **Drift demo data.** After step 1: `.venv\Scripts\python.exe scripts\simulate_drift.py --domain hr`. Check the Drift page shows it.
3. **Prompt A/B.** Run one experiment with 10–15 questions per variant (about 4 to 6 minutes per variant). Keep its results page open in a tab.
4. **Start everything:** `.\scripts\dev.ps1`. Sign in once, then keep the tab open.
5. **Fallback.** Take screenshots of each demo screen. If the network or a model fails live, show the screenshots and say so.

## Likely questions

- **Why a separate judge model?** A model tends to rate its own style highly. Separate models reduce that bias, and the judge is recorded on every run.
- **Why a KS test?** It compares whole score distributions, not just averages, and needs no assumption about their shape. It has limited power with few questions, which the app states.
- **What if the judge is wrong?** Every score has the judge's reasoning beside it, and results can be exported to CSV for review. The judge is a measuring instrument, not a ground truth.
- **What triggers drift?** A statistically significant drop of more than 10% on faithfulness, relevance or hit rate, or a large latency increase.
- **Does it handle new documents?** Upload on the Documents page re-indexes immediately. Rerun to see the effect. New documents don't add benchmark questions by themselves.
- **Cost?** The free tier costs nothing but is capped and varies from day to day. Cost is tracked per run.
