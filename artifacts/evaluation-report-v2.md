# Benchmark — Regulatory intelligence synthetic challenge benchmark

Dataset version: `2.0.0` · Split: `test` · SHA-256: `af6477a4b102489b364e575ad960d46ac31ccefcf0ff6de66365ef3d2db8714b`

## Results

| Evaluation | Metric | Estimate with uncertainty | Cases |
|---|---:|---:|---:|
| Lexical retrieval | Recall@5 | 75.0% (95% CI 55.0%–90.0%) | 20 |
| Lexical retrieval | MRR | 61.4% (95% CI 41.4%–79.2%) | 20 |

## Synthetic regression checks

- Change rules matched 40/40 template-derived fixtures.
- Evidence reviewer matched 20/20 synthetic fixtures.

These fixture pass counts verify expected code paths; they are not independent estimates of change-detection F1 or reviewer accuracy on regulatory texts.

## Retrieval by generator stratum

- **Easy** — Recall@5 83.3%, 95% CI 50.0%–100.0% (n=6).
- **Medium** — Recall@5 71.4%, 95% CI 42.9%–100.0% (n=7).
- **Hard** — Recall@5 71.4%, 95% CI 42.9%–100.0% (n=7).

> “Easy”, “medium” and “hard” are generator strata, not demonstrated levels of real-world difficulty. Bootstrap intervals use a fixed seed. The dataset is synthetic and no result establishes performance on EUR-Lex. Gemini scores are advisory and kept separate from deterministic baseline metrics.
