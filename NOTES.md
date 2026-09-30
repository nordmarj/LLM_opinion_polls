# Lab notebook

## 2026-09-30: project initialized

- Scaffolded `survey/` package, configs, tests (52 passing, no network), PREREG draft.
- Cloned Kastner's repo into `vendor/dt-audience-cues` (gitignored). Reused verbatim:
  `H_mwi` (→ `qm_binary`), `Q_neutral` (→ `dt_control`), `H_realism`, `V_zombie`, `V_stats` (panel),
  and persona sentences `lw_reader`, `ctrl_nurse`, `ctrl_swe`, `v_physprof`, `acad_prof`, `acad_phil`,
  `v_statsprof`. Kastner's persona sentences are prepended with a single space, as in his `render()`.
- Kastner context worth keeping in mind:
  - His post's headline numbers are from **tag-free** prompts judged by an LLM; his tagged runs were
    earlier. We use tags (per CLAUDE.md), so direct comparison should use his tagged `H_mwi` rows.
  - DT direction for the positive control: Fable 5.1 names FDT/UDT 100% with no persona, and CDT
    45–81% under academic-philosophy personas (`results/OTHER_MODELS.md`). So "shift toward CDT under
    `dt_phil_prof`" is the expected direction.
  - Output-token usage from his raw data (tagged, sets B/H/V): Claude Fable 5.1 high median 800–1300,
    Opus 5 high 1000–2800, Sonnet 5 high ~600, GPT-6 Astra default ~150–200. Used as cost priors.
- Fetched and cached the OpenRouter catalog (`survey/cache/models_2026-09-30.json`, 464 models) and
  per-model endpoints for the 26 candidates (`endpoints_2026-09-30.json`). No API key used.
- Observations about the API (also noted in CLAUDE.md):
  - `/models` now carries a `reasoning` object per model (`mandatory`, `default_enabled`,
    `supported_efforts`, `default_effort`). models.yaml is generated from it.
  - Catalog `pricing` is the cheapest provider's; pinned first-party prices can differ a lot
    (DeepSeek V4.1 Flash: catalog $0.02/$0.40 per M, first-party `deepseek` $0.15/$0.60). `survey plan`
    uses the pinned endpoint's price.
  - Several open-weight first-party endpoints are quantized (`moonshotai/mxfp4`, `z-ai/fp8`). gpt-oss has
    no first-party endpoint; pinned to `deepinfra/bf16`. Llama 4 Maverick (Apr 2025) is the newest Llama.
- Estimated cost of `pilot_core` (7 questions, 47 cells/model, n=10, 26 models): **~$300**, dominated by
  Fable 5.1/5 (~$43 each), Kimi K3 (~$35), Opus 5 (~$30). Waiting for model-list approval.
- Not yet done: judge runner (rubric and cache helpers exist), regression/figures, smoke run
  (needs `.env` with `OPENROUTER_API_KEY`).

### To verify on the first (smoke) run
- `provider.order` accepts endpoint tags with variants (`deepinfra/bf16`, `google-vertex/global`).
- Top-level `provider` field in the chat response gives the served provider; otherwise fetch
  `/generation?id=`.
- `usage.cost` is present in the response.
- Anthropic models return `message.reasoning` (summarized) at default effort.
