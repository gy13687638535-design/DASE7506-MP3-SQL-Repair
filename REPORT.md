# SQL Repair Agent for DASE7506 MP3

Guo Yang · Student ID 3036797817 · 11 November 2026

This submission implements a deterministic CPU controller that repairs SQLite queries using the official tools. It combines execution feedback, the course's fixed repair suggestions, and bounded SQL syntax-tree edits. It does not train a model, load model weights, contact a model API, or use a GPU during prediction or scoring. The source entry point is `submission/submission.py:create_agent`; the submitted configuration is `submission/config.json`.

The final official test score is **175/240 (72.91666666666667%)**, with all three grading instances required for each correct task. The measured Linux prediction-plus-scoring time is **28.531 seconds**. Validation accuracy is 91/120 (75.83%); three controlled ablations are reported below.

The complete, unmodified official score files are the primary evidence for the reported results. Final implementation changes were selected or debugged using validation and synthetic tests, not test labels.

## Agent loop and budget

The initial observation supplies the question, original draft, public example, ordering flag, remaining budget, and causal tool history. Schema information is requested explicitly when needed. The controller follows this procedure:

1. Call `check` on the exact original SQL. This obtains execution success or an error and a public-example match flag, and satisfies the prerequisite for requesting a repair hint.
2. If a checked query matches an informative public example, submit it immediately. When the example contains no non-NULL cells, request the shared hints and attempt an additional candidate before accepting the first match. This rule covers empty results and all-NULL results; it does not treat a numeric zero as empty.
3. Obtain `repair_hint` once, when enabled. Canonicalize the four suggestions with SQLGlot, count repeated forms, and avoid rechecking previously checked canonical SQL. Repetition is a priority signal, not proof of correctness. These are fixed suggestions for the original draft, not an adaptive model conversation.
4. Generate local repair hypotheses from every checked query, its execution feedback, the question, and the public example. Request `schema` when at least two candidates have been checked and the latest check reports an execution error, or after the current candidate pool is exhausted. At least two calls must remain so the schema can support a subsequent check.
5. Check the highest-priority unseen, syntactically permitted candidate. Recompute the candidate pool after receiving feedback. Stop on a public match under the stopping rule, on exhaustion of useful candidates, or when the eight-call budget is exhausted.
6. Submit the most recent checked query that matched the example. If none matched, submit the most recent executable checked query; if every query failed, submit the original draft. This fallback is explicit uncertainty, not a claim that executability establishes correctness.

`submit` is free. The agent returns only official action dictionaries and never calls the database executor itself. It never edits observations or constructs tool traces. The official predictor records those traces, and the official scorer independently replays them before evaluating final SQL on all three database instances. The controller uses `check` instead of `execute` because a check provides both execution feedback and the full public-example equality result at the same one-call cost.

## SQL repair and context management

`submission/repairs.py` creates SQLGlot abstract syntax tree hypotheses. Its repairs include close table/column spelling corrections; column qualification; missing joins suggested by declared foreign keys or distinctive shared column names; projection order/content alignment using public column headings; adding or removing `DISTINCT`; changing a column count to or from `COUNT(DISTINCT ...)`; grouping for aggregate ordering; count/sum ordering hypotheses; question-supported sort direction and limits; and moving outer aggregate filter conjuncts from `WHERE` to `HAVING` while preserving row-level predicates.

Edits are scope-aware where implemented. Nested scalar aggregates and window functions are not treated as outer aggregate filters. Schema repair deliberately skips queries containing multiple `SELECT` scopes. Moving an aggregate filter refuses predicates containing `OR`, where splitting the expression could change its logic. Generated candidates are hypotheses and must still pass through an official `check` call. The generator returns at most 24 candidates per checked SQL; the controller's actual execution budget remains eight tool calls.

Priorities are fixed, transparent heuristics. For example, explicit foreign-key joins receive high priority, public projection repairs outrank generic duplicate-removal changes, and excess public row counts increase the priority of adding `DISTINCT`. The rules do not learn weights from examples. Canonicalization reduces repeated calls caused by formatting or identifier case; it is not a complete semantic-equivalence test.

The episode history is the controller's memory. Each invocation derives checked queries, matches, hints, schema, and used SQL from that history. A fresh controller is created for every task. There is no cross-task answer cache, embedding index, task-ID lookup, accumulated test memory, or persistent conversation. Only the small explicit configuration is read from a local file by the agent.

The agent does not call `retrieve`. The built-in retriever supplies three training examples, but the database schemas are disjoint across splits and this controller has no general mechanism to transfer arbitrary retrieved SQL into a new schema. Spending one of eight calls on retrieval would reduce candidate-check opportunities. This is a design rationale, not an experimentally established claim that retrieval is unhelpful; retrieval was not a controlled experimental factor here.

## Evaluation and controlled ablations

Evaluation uses the unchanged official `mp3_sql.predict` and `mp3_sql.score` commands. A task counts as correct only when its final SQL matches all three grading instances. The official score is `100 × correct / n`; one-instance public-example success is not reported as the official metric. Validation contains 120 tasks and test contains 240 tasks, with schema-disjoint splits. Design choices were made using validation. This is the course's public benchmark, not a hidden-test generalization experiment.

The following results were measured after the final implementation correction. All variants were rerun on the same 120 validation tasks using Python 3.12.14 on Windows, and their complete score, prediction, and runtime files are included under `outputs/`.

| Validation variant | Correct / 120 | Accuracy | Mean charged calls | Intervention |
|---|---:|---:|---:|---|
| Unchanged official starter | 47 | 39.17% | 0.000 | Submit the original draft without tools; contextual baseline only |
| Full controller | 91 | 75.83% | 2.825 | Submitted settings |
| No local repairs | 80 | 66.67% | 2.258 | Disable AST edits and their schema calls; retain hints, checking and stopping |
| No hints | 60 | 50.00% | 2.375 | Disable cached suggestions; retain AST edits, schema and feedback |
| No weak-match verification | 83 | 69.17% | 2.525 | Accept an initial empty/all-NULL public match immediately |

The three ablations use the same tasks, framework, SQL parser, tool budget, and controller, changing only the indicated feature/configuration. `no_repairs.json` also disables schema because that feature serves local repair generation; thus this ablation measures the complete local-repair subsystem. Disabling hints also removes hint-based weak-match verification by construction. The measurements do not identify independent additive contributions and should not be summed.

In the final validation comparison, local repairs account for a difference of 11 correct tasks, shared hints for 31, and weak-match verification for 8, each compared with the full configuration. These comparisons motivate the selected design but do not establish the same effect sizes on new benchmarks. The official starter is useful for context but is not a compliant final repair agent because it has no feedback loop.

**Final test result:** `outputs/test-score.json` records 175 correct tasks out of 240, accuracy `72.91666666666667`, and mean charged tool calls `2.9625`. The score and predictions were produced by the unchanged official tools on Linux and copied without editing into the canonical submission paths. They include all tasks and all tool traces, not only successes.

| Canonical submission file | SHA256 |
|---|---|
| `outputs/test.json` | `4a72393678da88a7543c4c3743c01e6c776cc691ede7cf3bb67651f2b5d67b1e` |
| `outputs/test-score.json` | `1f06603944c931fdf4731f38ff23096771ebd761b5265e6885d978ef01d72be8` |

## Runtime, memory and model cost

Prediction and scoring use four official workers. The reproduction script sets numerical-library thread counts to one, limits Linux CPU affinity to at most four CPUs, applies a 2 GiB per-process virtual-address limit, monitors aggregate process-tree virtual memory, and enforces a combined 180-second prediction-plus-scoring deadline for each evaluation pair. Dependency installation, benchmark download, data verification, and report generation precede that timed pair.

On Linux, `scripts/reproduce.py` records wall time, descendant CPU time through `getrusage`, and process-tree RSS/virtual-memory samples every 20 ms. GNU `/usr/bin/time -v` records additional measurements when available. These memory measurements are sampled peaks, not exact continuous maxima. Runtime evidence is written separately from the unchanged official score JSON.

The final Windows validation run used Python 3.12.14 on Windows 11, with 40.088 seconds combined wall time. Its measured controller-only CPU time was 17.219 seconds, and the larger controller-process peak RSS was 44,130,304 bytes (42.09 MiB). Those CPU and memory numbers exclude SQLite worker subprocesses, and Windows does not enforce the Linux address-space policy. They are development measurements; the separate Linux run below supplies the resource-compliance evidence.

| Final test measurement | Value / evidence |
|---|---|
| Linux Python/platform and evaluated implementation commit | GitHub Actions Ubuntu 24.04, Python 3.12.16, x86-64/glibc 2.39; `32a7addf948ae132369c4b7a91549bccbc363f37` |
| Prediction wall time | 14.040 seconds |
| Scoring wall time | 14.485 seconds |
| Combined prediction + scoring wall time | 28.531 seconds, below the 180-second limit |
| Combined descendant CPU time | 85.586 CPU-seconds across the bounded workers |
| Sampled peak evaluation process-tree RSS | 117,526,528 bytes (112.08 MiB) |
| Sampled peak evaluation process-tree virtual memory | 827,392,000 bytes (789.06 MiB), below 2 GiB |
| Charged tool calls, mean / maximum | 2.9625 / 8; 711 charged calls in total |
| Linux evidence | [Successful workflow run](https://github.com/gy13687638535-design/DASE7506-MP3-SQL-Repair/actions/runs/42872209555); `outputs/linux/test-runtime.json` and the two `.time.txt` records |

The Linux test run used 518 `check`, 161 `repair_hint`, and 32 `schema` calls, plus 240 free submissions. The measured CPU cost includes the official predictor/scorer and their waited SQL workers. Sampled process-tree RSS can count shared pages more than once and excludes the monitoring wrapper itself. The canonical submitted files under `outputs/` are byte-for-byte copies of the unchanged Linux artifact also retained under `outputs/linux/`. The separate Windows test run is preserved under `outputs/windows/`. Later documentation and evidence commits do not change the evaluated agent implementation.

The Windows test run also scored 175/240. Its 240 final SQL strings, tool-call counts, task pass/fail flags, and 720 instance pass/fail flags match the Linux run. The full traces are not identical: two initial checks execute on Windows but report missing columns on Linux; one failed task has different grading error messages. SQLite/platform behavior can affect intermediate feedback even when final answers agree. Because the official scorer requires exact replayed observations, the submission uses the Linux traces and score rather than claiming the Windows traces are portable. Reproduce with the documented Linux environment; timing-dependent file hashes and platform-specific error text need not match across environments.

Runtime live-model completions, generated tokens, model parameters loaded, GPU use, and external model API calls are all zero. The four cached suggestions per task were generated by the course, not by this submission at runtime. The cache can therefore assist this CPU route even though its provider model has more than one billion parameters. No LoRA adapter or separate weight artifact is submitted. Required inference dependencies are Python 3.11/3.12, its standard library, and `sqlglot==27.29.0`.

## Failure analysis and limitations

The final validation run has 29 failures. Of these, 17 submitted a query whose recorded `check` matched the public example but failed at least one grading instance; the other 12 failed all three grading instances. This demonstrates why public-example feedback is necessary but insufficient. The public-match counts come from the actual submitted-query checks, and the grading outcomes come from the official score. No grading fingerprints or additional database contents were inspected for this analysis.

For `validation-6d8add77db18ef60`, the original query returned a nonempty public match and was submitted after one check. It sorted a nested broadcast query by `Time_of_day DESC LIMIT 1`. The official outcomes were `[true, false, false]`. The verified conclusion is that early acceptance of a nonempty public match can still be wrong on the other instances. Determining the intended full semantics would require more evidence; no reference SQL is inferred here.

For `validation-e271aa282462bdf7`, the cached hint used a grouped count with a `CASE` expression over roller-coaster speeds. That hint produced an empty public match, but the official outcomes were `[true, false, false]`. The weak-match policy explores beyond an initially matching draft; it does not exhaustively challenge every later empty match. A misleading shared hint can therefore pass the same weak evidence and terminate the episode.

SQL that runs can still contain an incorrect join relationship, duplicate handling, aggregate scope, tie policy, string comparison, or missing condition. AST shape checks do not prove these semantics. In development, an ambiguous-column repair was found to risk rewriting both already-qualified join operands to the same field; the final correction and regression test preserve qualified bindings while repairing the unqualified ambiguity. This does not establish that all ambiguous queries are safely repairable.

The rule set has limited natural-language understanding and limited nested-query rewriting. Fallback to the last executable candidate can return an answer with no public-match support. Canonical deduplication does not merge all equivalent SQL. Verification of empty results reduces one specific failure mode but cannot distinguish all programs that happen to agree on a sparse sample. More general query planning, join-path reasoning, or carefully budgeted retrieval are future work, not implemented capabilities.

## Safety and prompt-injection handling

Questions, SQL drafts, schema identifiers, public result headings/values, cached hints, and any retrieved text must be treated as untrusted data. A question or hint could contain instructions to ignore the budget, read a local file, contact an API, or submit destructive SQL. There is no runtime language-model interpreter or text-to-shell execution in this design, so such instructions do not become system actions. The controller chooses from fixed action names and does not use `eval`, `exec`, shell execution, network access, or direct database connections.

Candidate SQL must parse as one read-only `SELECT` or set operation, must not contain modifying/command AST nodes, and must fit 16,000 UTF-8 bytes. Public headings are accepted only as restricted column or aggregate expressions; subqueries, literals, aliases, and arbitrary functions in a heading cannot become a projection repair. Public result cell values are never copied into output SQL. Question-derived numeric limits are narrowly parsed and bounded. Retrieved-content injection is absent from the implemented route because retrieval is disabled.

These checks supplement the unchanged official executor, which opens read-only SQLite databases, disables extension loading, authorizes only allowed tables/functions, and bounds time, expression depth, result size, and worker resources. The initial exact-draft check deliberately delegates malformed or unsafe draft rejection to this executor. The official episode enforces unique actions and the eight-call limit, and trace replay detects forged feedback. The agent does not claim to replace that executor sandbox.

Untrusted text can still influence semantic choices through allowed SQL, misleading headings, or keyword matches. Passing the read-only gate therefore prevents certain operational actions, not answer manipulation. Python parsing also has finite CPU/memory costs. Offline execution, bounded candidate generation, and unchanged framework limits reduce exposure, but no comprehensive prompt-injection or adversarial robustness guarantee is claimed.

The final implementation passes 23 synthetic regression tests. They cover the original-draft prerequisite, candidate deduplication, budget exhaustion, observation immutability, weak matches, destructive and multi-statement SQL, malicious hint/headings, preservation of qualified join operands during ambiguous-column repair, and aggregate scope/filter semantics. These tests use synthetic observations and SQL rather than benchmark answer fixtures. They complement the official trace replay; they do not prove correctness for every SQL query.

## Provenance and external assistance

The exact course package, data roles, and integrity identifiers are recorded in `DATA_PROVENANCE.md`. The runtime agent does not read `*_references.json`, grading fingerprints, additional evaluation databases, the cached hint file, or training memory directly. The framework supplies only authorized observations; the scorer alone uses the grading bundle. Training examples were used for preliminary inspection/smoke testing, not for model fitting. No examples, labels, task-specific answers, or result fingerprints are embedded in the implementation.

OpenAI Codex provided substantial development assistance with specification review, implementation, debugging, experiments, tests, documentation, and submission tooling. This is disclosed assistance, not unaided human coding. The submitted agent does not call Codex or any other external model, including during grading. No task-specific training material was generated. The student remains responsible for reviewing and understanding the method and its limitations.

The course cache metadata identifies original drafts from `Qwen/Qwen3-0.6B` revision `c1899de289a04d12100db370d81485cdf75e47ca`, and four fixed repair suggestions from `Qwen/Qwen3-8B` revision `b968826d9c46dd6066d109eabc6255188de91218`, without assignment fine-tuning. These are provider provenance declarations, not models loaded by the submitted code. Their pretraining exposure to the older Spider benchmark cannot be ruled out. The course `NOTICE` attributes Spider to Yu et al. (2018), data/course modifications to CC BY-SA 4.0, Qwen material to its applicable Apache-2.0 terms, and SQLGlot to MIT.

## Exact reproduction

Start with an unpacked source export and the exact official student package. Provision Python and dependencies before disconnecting the network. The official archive SHA256 is `406d69507ccf955a53b35db1c1368bd7452565ebd928b47d0f6161fe35b99a61`. The GitHub workflow downloads it, verifies this hash, and locates its package root. The following commands run from the submitted repository root on Linux:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
export MP3_PACKAGE=/absolute/path/to/MP3_SQL_student_package
(cd "$MP3_PACKAGE" && python -m mp3_sql.check_data)
PYTHONPATH="$PWD/submission" python -m unittest discover -s tests -v
python scripts/reproduce.py --package "$MP3_PACKAGE" --split validation --ablations --output-dir outputs/reproduced-validation
python scripts/reproduce.py --package "$MP3_PACKAGE" --split test --output-dir outputs/reproduced-test
```

The last command performs the following official operations, recording measurements in a separate runtime JSON:

```bash
export MP3_SOURCE="$PWD"
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

Use the wrapper for measured resource enforcement. The source ZIP includes the final `outputs/test.json` and complete `outputs/test-score.json`, implementation, configuration, dependency list, tests, report, provenance, and reproduction scripts. It excludes the benchmark databases, base/adapter weights, virtual environments, caches, credentials, and unrelated projects. Re-running can change wall-clock timings and JSON hashes that include timings; compare task SQL, valid traces, official counts, and benchmark identities rather than requiring timing-dependent files to be byte-identical.

The requirements and submission protocol come from the [official project specification](https://xudongwu-0.github.io/courses/dase7506/mp3/PROJECT.md). Package provenance is independently inspectable in the official archive's `NOTICE`, `mp3_sql/data/provenance.json`, `model_generation.json`, and `hint_generation.json`. These course records are primary evidence for this release; the experiment files are primary evidence for the results reported here.
