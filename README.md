# LLM opinion polls

Do LLMs' stated views on contested intellectual questions shift with cues about who is asking?
Primary target: interpretations of quantum mechanics. Positive control: decision theory
(Kastner 2026). All model calls go through OpenRouter. See `CLAUDE.md` for the full design and
`PREREG.md` for hypotheses and contrasts.

## Setup

```bash
uv sync --group dev
cp .env.example .env        # then put your OpenRouter key in .env (never commit it)
uv run pytest               # no network
```

## Usage

```bash
uv run survey models refresh                  # refresh model + endpoint cache (public, no key)
uv run survey models show                     # configured models, pinned provider, prices
uv run survey plan --design pilot_core --pilot
uv run survey run  --design smoke --pilot --approve-new-models
uv run survey code --pilot                    # parse answers -> results/derived/coded_pilot.jsonl
```

`survey run` refuses to start when the estimate exceeds `ask_above_usd` (pass `--confirm-cost`) or
when a model has never been approved (add it to `approved_models` in `survey/config/budget.yaml`), and
stops when spend would exceed `hard_cap_usd`.

## Layout

| Path | Contents |
|---|---|
| `survey/config/` | `questions.yaml`, `cues.yaml`, `models.yaml`, `budget.yaml`, `designs.yaml` |
| `survey/` | config loading, prompt building, OpenRouter client, runner, parser, judge, analysis |
| `survey/judge/rubric.md` | fixed judge rubric |
| `survey/cache/` | dated snapshots of the OpenRouter models and endpoints catalogs |
| `results/raw/`, `results/pilot/` | append-only JSONL, one line per sample |
| `results/derived/` | coded tables, judge cache, figures |
| `vendor/` | Kastner's repo, cloned locally (gitignored) |
