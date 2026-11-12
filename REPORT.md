# SQL Repair Agent for DASE7506 MP3 — Final v2

Guo Yang · Student ID 3036797817 · 12 November 2026

This submission is a deterministic CPU controller that repairs SQLite queries through the official tools. It combines real execution feedback, the course's fixed repair suggestions, and bounded syntax-tree edits. It neither trains nor loads a model and makes no external API calls during evaluation. The canonical entry point is `submission/submission.py:create_agent`; `submission/config.json` is a policy configuration, not a trained checkpoint.

The selected v2 configuration achieved **98/120 validation tasks (81.67%)** and **182/240 test tasks (75.83333333333333%)**. Every correct test task must pass all three grading database instances. The unchanged official score, predictions, and separate runtime measurements are retained under `outputs/`. Instructor verification is distinct from this student-side official-tool evaluation.

## Agent loop and information flow

Each task supplies a question, exact imperfect draft, public example, ordered flag, remaining tool budget, and causal history. The controller derives all episode state from that history; it requests schema information explicitly when needed.

1. `check` the exact original draft before requesting any hint. The initial draft is passed unchanged to the official executor, including when malformed or unsafe, so its real error is available.
2. Obtain `repair_hint` at most once. Even an initial public-example match is verified through the fixed hint cache when a distinct eligible hint exists. Empty/all-NULL results are treated as weak evidence; numeric zero is not empty. Hints are fixed original-draft proposals, not adaptive model completions.
3. Generate candidates from checked SQL, question text, public headings, real errors and schema. Request `schema` at most once: after two checks when the latest failed execution, or after the current pool is exhausted, provided at least two calls remain.
4. Canonicalize SQL with SQLGlot, reject unsafe or oversized candidates and avoid rechecking canonical equivalents. Rank remaining proposals with fixed priorities, then spend one official `check` on the highest-priority candidate. Recompute after its feedback.
5. Once a public match exists, restrict further attempts to eligible hint-origin candidates. Stop after the required initial verification, when useful candidates are exhausted, or when the eight-call budget is depleted. The selected configuration does not continue unrestricted refinement after a match.
6. Among checked public matches with informative examples, use a fixed structural quality score to select the final SQL. For empty/all-NULL examples, keep the last matching query instead. If no query matched, return the last executable checked query; if all failed, return the original. Executability is a fallback, not proof of correctness.

`submit` is free. The agent returns official action dictionaries; it does not access databases, call the executor directly, alter observations, or fabricate traces. The official framework enforces the eight charged calls, and the scorer replays the actual tool history. Using `check` instead of `execute` supplies execution feedback and public-example comparison at the same charged cost.

The entire task history is episode memory. A fresh agent is constructed for each task. There is no persistent cross-task answer cache, task-ID map, embedding index or accumulated test memory. The only runtime file the agent itself reads is its explicit configuration.

Retrieval is not used. The provided retriever can return training examples, but this controller has no general mechanism to transfer arbitrary SQL across disjoint schemas. A retrieval call would also consume a candidate-check opportunity. This is a design rationale, not evidence that retrieval is ineffective; retrieval was not experimentally compared.

## Repair rules and selection

`repairs.py` proposes table/column spelling repairs, column qualification, plausible missing joins, projection alignment, duplicate handling, count-distinct variants, grouping, ordering, question-supported limits, and moving aggregate filters from `WHERE` to `HAVING`. Qualified join operands are preserved during ambiguity repair. An ambiguous-column error does not trigger adding an omitted table merely because another schema table shares its name.

`semantic_repairs.py` adds several general hypotheses:

- A row-level inequality for a question containing “never” may need a correlated `NOT EXISTS` condition.
- Clear existential “greater than any” or “less than any” wording may require a `MIN` or `MAX` boundary different from the draft.
- Projection repair preserves deleted alias references and expands positional `ORDER BY`/`GROUP BY` references against the original projection. It can also repair related aggregation and ordering together.
- Numeric conditions explicitly present in the question can support numeric casts; selected join/group structures can suggest pruning a superfluous clause.

These are candidate hypotheses, not guaranteed equivalences. Removing an apparently unused join can change row multiplicities; “any” in natural language can be ambiguous. Generated SQL must still be checked. Scope restrictions deliberately leave many multi-scope and disjunctive cases unrepaired. Each repair generator bounds its proposals, and only the official eight-call allowance can execute candidates.

`ranking.py` uses manually specified feature contributions for projection shape and alignment, aggregation, distinctness, frequency ordering, negation, quantifier boundaries, tautological joins and known schema bindings, plus a small complexity tie-breaker. Window aggregates are distinguished from ordinary aggregates when checking grouping. No ranker weights were fitted, and its values are not probabilities. In the selected policy it selects among already checked public matches; it does not replace execution feedback. Weak examples retain the last-match policy because a structural preference can choose a shorter but incorrect SQL.

The selected configuration disables **whole-pool projection precomposition** (`compose_projection=false`). This does not disable all compositional repair: the semantic generator still maintains projection references and composes selected semantic edits. `safe_projection=true` remains in the frozen configuration but has no additional effect when that whole-pool step is disabled. More aggressive `refine_matches` and `quality_priority` modes are not enabled.

## Evaluation and controlled ablations

The official package, predictor, scorer, tool semantics and benchmark files were not modified. Accuracy is `100 × correct / n` across all three instances, not public-example match rate. Validation has 120 tasks; test has 240, with schemas disjoint across splits. The course explicitly provides a public benchmark, so these results are not a hidden-test generalization claim.

The final five validation configurations were run on the same corrected v2 code, Python 3.12.14 on Windows, with the same official tools, SQLGlot version, tasks and eight-call budget. Full prediction and official-score files are preserved in `experiments/results/validation-final*.json`.

| Configuration | Correct / 120 | Accuracy | Mean charged calls | Controlled intervention relative to `final` |
|---|---:|---:|---:|---|
| `final` | 97 | 80.83% | 3.3083 | Semantic rules, whole-pool composition, verification and match ranking enabled |
| `final_no_semantic` | 94 | 78.33% | 3.3000 | Disable semantic generator and its safe projection implementation |
| `final_no_verification` | 95 | 79.17% | 2.6583 | Disable verification of all initial matches; retain weak-example verification |
| `final_no_ranking` | 97 | 80.83% | 3.3083 | Disable structural selection among checked matches |
| **`final_no_composition` — submitted** | **98** | **81.67%** | **3.4250** | **Disable whole-pool projection precomposition** |

These include more than two controlled ablations. The semantic ablation changes two coupled switches and therefore measures that subsystem, not a single rule. Other rows isolate the stated switch relative to the all-enabled `final` configuration. Differences are not independent additive contributions. Removing match ranking did not change total correctness in that contrast; there is no demonstrated stand-alone accuracy benefit for it here.

The selected configuration is the highest validation count among these five. Its source and configuration hashes were recorded in `experiments/selection.json` before the first v2 test, evaluated at commit `6f3c2369d1987ae4b1cf2252e1971770fc507c32`. The canonical `submission/` files are an unchanged promotion of those five frozen files. Formal-entry reproduction verifies packaging without selecting new rules from test outcomes. [outputs/reproduction-check.json](outputs/reproduction-check.json) confirms that all 240 prediction records, including SQL and tool traces, match the frozen experimental run; only run-level timing metadata differs. All five source/configuration files match the pre-test hashes.

Ten earlier configurations are documented in `experiments/README.md`. They were part of iterative development and do not all represent the same final source revision. The aggressive refinement trial reached only 91/120, but multiple switches differed, so its failure cannot be attributed causally to one switch. Final audits corrected projection ordinals, window-aggregate scoring and ambiguity-induced joins before the five controlled comparisons. Multiple validation trials create overfitting risk even though test data were not used to choose their settings.

| Version comparison | Validation | Test | Test mean calls |
|---|---:|---:|---:|
| Previous immutable submission v1 | 91/120 (75.83%) | 175/240 (72.92%) | 2.9625 |
| Submitted v2 | 98/120 (81.67%) | 182/240 (75.83%) | 3.4208 |

The frozen first-v2 test comparison found 174 tasks correct in both versions, eight newly correct, one newly incorrect, and 57 incorrect in both. This is a net gain of seven test tasks, or 2.92 percentage points. Only official pass/fail flags were compared afterward for this report; no test SQL or failed cases were used to revise the agent. `experiments/results/verification.json` records this comparison and the exact first-v2 evidence. The new result does not guarantee the same benefit on arbitrary databases or error distributions.

Canonical submission hashes from the formal-entry run:

| File | SHA-256 |
|---|---|
| `outputs/test.json` | `9f43529b67d0dd154f282b8c4ec638e3dd2ad258e71d465b898bc791bba4f210` |
| `outputs/test-score.json` | `47e57aabd83b26a859a8e22770a9849331e4fbc6f103217f6a1a37289948b1c4` |

## Runtime, memory and model cost

The wrapper runs four official workers and sets numerical-library thread counts to one. On Linux it limits CPU affinity to at most four CPUs, applies a 2 GiB per-process address-space ceiling, samples aggregate process-tree virtual memory and enforces 180 seconds total for prediction plus scoring. Dependency installation, benchmark download and integrity checks occur before the timed pair. Measurement output is separate from the unchanged score JSON.

Linux wall time and descendant CPU use are recorded with `getrusage`, with process-tree RSS/virtual-memory samples every 20 ms and GNU `/usr/bin/time -v` reports when available. Sampled memory peaks are not continuous maxima; shared pages may be counted in multiple processes, and the wrapper itself is outside the sampled command tree. Parallel CPU-seconds can exceed elapsed wall seconds.

| Formal canonical-entry test measurement | Value |
|---|---|
| Evaluated implementation commit | `9c024db7bf5280bd7d731de4724909fb1bdc2e1a` |
| Environment | GitHub Actions Ubuntu 24.04; actual Python/platform recorded in `outputs/test-runtime.json` |
| Combined prediction + scoring wall time | 20.289 seconds |
| Combined descendant CPU time | 59.146 CPU-seconds |
| Sampled peak process-tree RSS | 115.934 MiB |
| Sampled peak process-tree virtual memory | 791.516 MiB, below 2 GiB |
| Charged tool calls, mean / limit | 3.4208333333333334 / 8 |
| Evidence | [Successful formal workflow](https://github.com/gy13687638535-design/DASE7506-MP3-SQL-Repair/actions/runs/43217148261), `outputs/test-runtime.json` and its logs |

The preceding frozen experimental-entry Linux run independently measured 20.353 seconds elapsed, 60.445 CPU-seconds, 108.246 MiB peak sampled RSS and 784.852 MiB peak sampled virtual memory. Its evidence is [run 43157511762](https://github.com/gy13687638535-design/DASE7506-MP3-SQL-Repair/actions/runs/43157511762) and `experiments/results/linux/`. Different CI hosts and timing noise mean these numbers do not establish a guaranteed speedup over v1. Test mean tool use rises approximately 15.47%; validation mean rises from 2.825 to 3.425, approximately 21.24%.

Windows development measurements cover only the controller process and do not enforce the Linux address-space policy. They are not resource-compliance evidence. SQLite versions/platforms can also change intermediate feedback; the submitted score and traces come from the same Linux run and are never spliced with Windows traces.

Runtime model completions, generated tokens, loaded model parameters, GPU use and external model API calls are zero. The course generated the shared hint cache; its provider compute is not this agent's runtime or training cost. No LoRA adapter or separate weight artifact is submitted. Dependencies are Python 3.11/3.12, its standard library, the official package and `sqlglot==27.29.0`.

## Failure cases and limits

The selected validation run has 22 failed tasks. Fourteen submitted a checked SQL that matched the public example but failed at least one grading instance. The remaining eight submitted SQL without a matching final check. These counts are derived from the recorded submitted-query checks and official pass/fail flags, not grading fingerprints or additional database contents.

For `validation-de306200a6efff23`, both the original and hint checks returned an empty public match. The agent submitted the checked restaurant/type-join query after three charged calls. The scorer reported `[true, false, true]` across the three instances. This establishes that extra hint verification can still agree on a weak sample without repairing the semantics; it does not identify a gold query.

For `validation-3c4d5ecbd3a4ffc8`, four checked company/employment queries executed and returned zero rows but never matched the example. After six charged calls, the candidate pool was exhausted and the controller returned its last executable query. All three grading cases failed. The fallback makes the uncertainty explicit but cannot recover semantics absent from the rules and hints.

Join cardinality, duplicate handling, aggregate scope, ties, text comparisons, absent predicates and complex nested queries remain difficult. A syntactically read-only query or high structural score can still be wrong. Canonicalization does not prove semantic equivalence. Natural-language keyword matching is limited, and the finite budget can stop before the right repair. More general planning, schema-grounded join reasoning, learned ranking or budgeted retrieval would require separate implementation and controlled evaluation; no performance claim is made for untested training/LoRA alternatives.

## Prompt-injection risks and safeguards

Questions, drafts, schema names, result headings/values and cached hints are untrusted data. They may contain instructions to ignore the tool budget, read a file, contact an API, alter the database or treat an answer as authoritative. This agent has no runtime natural-language instruction interpreter or text-to-shell path: it uses fixed action names, and neither `eval`/`exec`, subprocesses, network access nor direct database connections occur in the agent modules.

Generated candidates must parse as one read-only `SELECT` or set operation, exclude modifying/command AST nodes, and fit 16,000 UTF-8 bytes. Public headings are restricted to supported column/aggregate expressions; subqueries and result-value literals are not copied into SQL. Explicit question-derived limits and numeric conditions have constrained parsing. Cached hints are treated as candidate SQL subject to the same checks, not as trusted instructions. Retrieval is unused, so this route does not consume retrieval prompt injections.

The exact initial draft is deliberately checked without rewriting and relies on the unchanged official SQLite executor for rejection. That executor opens databases read-only, restricts functions/tables, disables extension loading and enforces execution limits. The framework enforces action uniqueness/budget, and official trace replay checks the recorded feedback. Agent guards supplement this sandbox; they do not replace it.

Untrusted text can still bias a permitted SQL hypothesis through misleading headings, keywords or syntactically valid hints. Read-only filtering is therefore not a semantic-security proof. Parsing also consumes finite CPU/memory. Bounded generation and the official offline executor limit exposure, but this work does not claim comprehensive adversarial robustness.

All 51 synthetic regression tests passed (23 protocol/basic-repair tests and 28 semantic/ranking/audit tests). They cover the exact-draft prerequisite, deduplication, budget exhaustion, observation immutability, weak examples, malicious/stacked SQL and headings, join binding preservation, aggregate scope, projection aliases/ordinals and filtered window aggregates. Their fixtures are in-memory SQLite tables and artificial observations, not benchmark answer fixtures. The two suites complement official trace replay; they do not prove every transformation correct.

## Data provenance and assistance

`DATA_PROVENANCE.md` records the exact course archive, benchmark identities and permitted data roles. The agent reads neither grading references/fingerprints, additional database files, raw hint-cache files nor training-memory files. Training examples were inspected for format/smoke tests, not fitted. Validation guided routine designs; only the official scorer reads the grading bundle. No task-ID lookup, task-specific SQL answer map, trained classifier, embedding index or learned ranker is embedded in the export.

OpenAI Codex substantially assisted specification review, code, experiments, debugging, tests, documentation and submission preparation. This is disclosed assistance, not unaided human authorship. The running agent does not call Codex or any other external model. No task-specific training material was generated, and no training logs or adapter files are applicable. The student remains responsible for reviewing the method and limitations.

Course provenance attributes drafts to `Qwen/Qwen3-0.6B` revision `c1899de289a04d12100db370d81485cdf75e47ca` and four cached repair suggestions to `Qwen/Qwen3-8B` revision `b968826d9c46dd6066d109eabc6255188de91218`, without assignment fine-tuning. These are provider declarations, not models loaded by this agent. Their pretraining exposure to the old public Spider benchmark cannot be excluded. The course `NOTICE` attributes Spider to Yu et al. (2018), data/course modifications to CC BY-SA 4.0, Qwen material to its applicable terms and SQLGlot to MIT.

## Exact reproduction and export

Provision Python 3.11/3.12, declared dependencies and the exact official package before going offline. The official archive SHA-256 is `406d69507ccf955a53b35db1c1368bd7452565ebd928b47d0f6161fe35b99a61`. Run from this source export's root on Linux:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
export MP3_PACKAGE=/absolute/path/to/MP3_SQL_student_package
python -m pip install -r "$MP3_PACKAGE/requirements.txt" -r requirements.txt
(cd "$MP3_PACKAGE" && python -m mp3_sql.check_data)
PYTHONPATH="$PWD/submission" python -m unittest discover -s tests -v
PYTHONPATH="$PWD/experiments/v2" python -m unittest discover -s experiments -p 'test_*.py' -v
python scripts/reproduce.py --package "$MP3_PACKAGE" --split validation --ablations --output-dir outputs/reproduced-validation
python scripts/reproduce.py --package "$MP3_PACKAGE" --split test --output-dir outputs/reproduced-test
```

`--ablations` reruns the selected configuration and the final five controlled configurations under `experiments/configs/`; it is restricted to validation. Direct official test commands, equivalent to the wrapper's evaluation without its resource monitor:

```bash
export MP3_SOURCE="$PWD"
mkdir -p outputs/reproduced-test
cd "$MP3_PACKAGE"
export PYTHONPATH="$MP3_SOURCE/submission"
python -m mp3_sql.predict --split test --workers 4 \
  --method "$MP3_SOURCE/submission/submission.py" \
  --checkpoint "$MP3_SOURCE/submission/config.json" \
  --output "$MP3_SOURCE/outputs/reproduced-test/test.json"
python -m mp3_sql.score --split test --workers 4 \
  --predictions "$MP3_SOURCE/outputs/reproduced-test/test.json" \
  --output "$MP3_SOURCE/outputs/reproduced-test/test-score.json"
```

Use the wrapper for measured enforcement. The immutable HTTPS source ZIP includes implementation, configuration, requirements, report, provenance, reproduction scripts, tests and both complete official output files. It excludes benchmark databases, base/adapter weights, virtual environments, caches and credentials. Timing-dependent score JSON hashes or platform-specific error text can vary on reproduction; compare valid trace replay, official counts, final SQL and benchmark identities instead of requiring every timing byte to match.

The original v1 submission remains pinned to `7b6ba20f79a2731fc5b1db24888cfb8205c70476`. The course requires improved submissions to use new issues and immutable artifacts with the same account/student ID; its best eligible reproducible score determines the student's ranking. The updated issue therefore supersedes the old result without editing or deleting its historical record.

Primary sources are the [official specification](https://xudongwu-0.github.io/courses/dase7506/mp3/PROJECT.md), the package's `NOTICE`/manifest/provenance/model-cache metadata, and the retained unmodified scorer outputs. Proposed explanations of experimental differences are identified as hypotheses above, separate from measured counts.
