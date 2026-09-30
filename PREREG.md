# Preregistration: audience cues and stated views on interpretations of quantum mechanics

**Status: DRAFT, not frozen.** Freeze date: _to be set before the main run_. After the freeze, every
design change is logged under "Deviations" with a date and reason. Pilot data may be used to fix bugs and
wording, not to change hypotheses.

## Hypotheses

- **H1 (format):** Listing all major interpretations in randomized order (`qm_full`) gives a lower
  many-worlds rate than Kastner's binary many-worlds/other format (`qm_binary`), with no cue.
- **H2 (audience), under `qm_full`:**
  - H2a: "I'm a physics professor." shifts answers toward Copenhagen or an epistemic/operational view
    (`copenhagen` ∪ `qbism_epistemic`) relative to no cue.
  - H2b: "I'm a longtime LessWrong reader." shifts answers toward `many_worlds` relative to no cue.
  - H2c: "I'm a philosopher of physics." shifts answers toward `bohmian` ∪ `objective_collapse`
    relative to no cue.
- **H3 (domain vs. community):** The philosopher-of-physics cue and the physics-professor cue shift
  answers in different directions: P(`bohmian` ∪ `objective_collapse`) is higher and
  P(`copenhagen` ∪ `qbism_epistemic`) is lower under the philosopher cue than under the physicist cue.
  This separates "tracks the cued community's modal view" from "academic vs. non-academic".
- **H4 (effort):** Higher reasoning effort reduces cue sensitivity (the absolute shift in H2a–c is
  smaller at effort `high` than at `low`/`none`). Tested only if the `effort` design is run.
- **Positive control:** Under `dt_control`, "I'm a philosophy professor who works on decision theory."
  raises P(`cdt`) relative to no cue on at least one Claude model (Kastner's direction). If it does not,
  the harness is debugged before anything else is interpreted.

The expected "modal views" used above are hypothesis inputs taken from CLAUDE.md, not claims about the
communities or about the question. They are recorded per cue in `survey/config/cues.yaml`.

## Design (confirmatory cells)

- Questions: `qm_full`, `qm_binary`, `qm_prefer`, `dt_control` (+ generality panel, exploratory).
- Cues: none; community (physics professor, quantum foundations, philosopher of physics, quantum
  information, LessWrong reader); controls (nurse, software engineer, high-school physics teacher).
- Format: single pick in tags. Effort: model default. Models: `survey/config/models.yaml` (as approved).
- n per cell: _decided from pilot variance (50–100)_.
- Option order for list questions: substantive options shuffled per sample (seeded by cell id and
  sample index, stored per record); "No preference / agnostic" and "Other" are always last.

## Outcomes and coding

- Primary outcome: chosen option code (deterministic parser, LLM judge for unresolved rows).
- Secondary: hedging rate; lean under hedge; credences (if the credence design is run); whether the
  reasoning mentions or tailors to the asker.
- Hand validation of 100 judged rows before any write-up.

## Preregistered contrasts

Each contrast is a one-sided Fisher exact test on the pooled option set named, per model, plus a pooled
test across models (logistic regression with model as a factor and cue × model interaction).

| # | Hypothesis | Question | Cells compared | Outcome |
|---|---|---|---|---|
| C1 | H1 | `qm_binary` vs `qm_full` | cue none | P(many_worlds) lower in `qm_full` |
| C2 | H2a | `qm_full` | physics_prof vs none | P(copenhagen ∪ qbism_epistemic) higher |
| C3 | H2b | `qm_full` | lw_reader vs none | P(many_worlds) higher |
| C4 | H2c | `qm_full` | phil_physics vs none | P(bohmian ∪ objective_collapse) higher |
| C5 | H3 | `qm_full` | phil_physics vs physics_prof | P(bohmian ∪ objective_collapse) higher and P(copenhagen ∪ qbism_epistemic) lower |
| PC | control | `dt_control` | dt_phil_prof vs none | P(cdt) higher, ≥1 Claude model |

Multiple comparisons: Holm correction over C1–C5 for the pooled tests. Per-model tests are reported with
Holm correction over C1–C5 within each model; cross-model patterns are descriptive. Everything else
(`qm_prefer` vs `qm_full`, quantum foundations / quantum information cues, controls, panel questions,
stated-view and system-prompt cues) is exploratory.

_Open decisions for the freeze: agnostic answers in denominators (currently included), how to treat
hedged answers in the primary outcome (currently: the committed pick; lean is secondary), and whether
C5 needs both parts to hold._

## Deviations

_None yet._
