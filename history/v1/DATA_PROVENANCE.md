# Data and execution provenance

Project: DASE7506 MP3 SQL Repair Agent. Student: Guo Yang, 3036797817.
Source inspected on 10–11 November 2026. This file records benchmark provenance and access boundaries; it contains no grading answers.

## Exact benchmark release

The input package is the official `MP3_SQL_student_package`, benchmark identity `spider-sql-repair-public-evaluation-v3`, protocol `dase7506-sql-repair-v1`. Its upstream `NOTICE` retains the text “assignment v2”; the manifest and official submission validator identify the evaluation as v3. The submission does not edit either record.

- Project specification: https://xudongwu-0.github.io/courses/dase7506/mp3/PROJECT.md
- Official ZIP: https://xudongwu-0.github.io/courses/dase7506/mp3/downloads/MP3_SQL_student_package.zip?v=406d69507ccf
- Official checksum source: https://raw.githubusercontent.com/xudongwu-0/xudongwu-0.github.io/main/courses/dase7506/mp3/downloads/MP3_SQL_student_package.zip.sha256

| File / identity | SHA256 |
|---|---|
| Official student ZIP | `406d69507ccf955a53b35db1c1368bd7452565ebd928b47d0f6161fe35b99a61` |
| `PACKAGE_MANIFEST.json` | `85b645ee9413c36d215253544fd0657679b9e66175b304ee24a386ddeca762a1` |
| `mp3_sql/data/manifest.json` | `bf7a517249ebe31b9cad8cbf5d6598fde98316d89f9aa1172cae3ad83289a6bc` |
| `mp3_sql/data/provenance.json` | `7ab15b9a304bbed2f4fd79292e11732b5eaa5558ea444c9ae1818038ef934964` |
| `mp3_sql/data/train.jsonl` | `562d6d54cbfac83829cf528a3b8ca5f101994c9fe5b1a502519beba328900f65` |
| `mp3_sql/data/validation.jsonl` | `ccb66ffc9214bb9484b278718acf7eae55afac7c4d4afa25ee03f74ad3fea6eb` |
| `mp3_sql/data/test.jsonl` | `598b1a072a47cdcf7308dc5646ae2bffd356390ab8df533510b69f2c884d712c` |
| `mp3_sql/data/repair_hints.json` | `cedf7056f9248bc6296ee80bc03e2a7744c119111f640d8596ea195c5d1e6b03` |
| `mp3_sql/data/train_memory.jsonl` | `25dced1001defe1d96b87e67eb007a106a3b96ac57d0bd76988a0ee63ee563d2` |
| `mp3_sql/data/public_results.json` | `1dba955aab6ef8f6cbe4f05bad697f513929400f262afbc1bd6bd4f37efba8c2` |
| Official scorer `mp3_sql/score.py` | `87870af26173fbe6d8994e4de179fb272ef1fadf7dcaafc2e7b4c814c61ec95b` |
| Official executor `mp3_sql/sqlite_tool.py` | `4ecc3839728d68bd83f0d2a52cdd8392fd76dbaec3e54a19422118dee587b471` |
| Test references identity required by official validator | `8be5f2746ee324d6b4b880dd84a2f8de56fa540af08e93842c0476adec581506` |

Local file hashes above were calculated for integrity checking. The official ZIP checksum and test-reference identity were obtained from the course's published checksum and submission-validator metadata. Recording or validating those file-level hashes is not using task-level grading result fingerprints as agent input.

## Origin and licensing

The course provenance record attributes the data to Spider (Yu et al., 2018), mirrored at `HAL-9001/spider-databases` revision `4a01bbac6520cd35b216db9e1724e5e1ada60aa4`. The upstream database archive hash recorded by the course is `00636695dabed6b5f4b8328a16b13e069a2f16591d5efcce57660669c85b121b`. This is a different archive from the student-package ZIP and must not be substituted for its checksum.

The mirror revision, upstream archive identity, sampling method, and model-generation claims are declarations in the official package; this project did not independently reconstruct the upstream dataset or regenerate the model outputs. The course applies CC BY-SA 4.0 to Spider-derived data and course modifications. Its notice identifies Qwen terms as Apache-2.0 and SQLGlot as MIT. The export includes attribution and necessary prediction traces but excludes the benchmark corpus/databases and model weights.

The package contains 480 training, 120 validation, and 240 test tasks. Course metadata describes schema-disjoint splitting: 20 selected original-training schemas for validation, the remaining original-training schemas for training, and original-development schemas for course test. The source benchmark is old and publicly accessible; pretraining contamination of provider models cannot be excluded. This is not an official Spider or BIRD leaderboard result.

## Data roles and permitted access

| Material | Use in this project | Available to runtime agent? |
|---|---|---|
| Training tasks and training memory examples | Preliminary format inspection and smoke tests; no parameter fitting, learned index, or generated training dataset | No direct file access; retrieval is not used |
| Validation tasks | Select controller behavior and assess generic repair changes; controlled ablations and failure analysis | Only the current official observation and authorized tool feedback |
| Validation references/additional instances | Unchanged official scoring; failure analysis used scorer outcomes and traces rather than reference fingerprints | No |
| Test tasks | Final official local evaluation and independent Linux reproduction | Only the current official observation and authorized tool feedback |
| Test references/additional instances | Unchanged official scorer only; not training or candidate selection | No |
| Public database | Executed only by the official `check` tool during agent episodes | Indirect feedback only |
| Shared hint cache | Course-provided fixed proposals, accessed through `repair_hint` after checking the exact draft | Tool-returned suggestions only |
| Schema metadata | Course `schema` tool when needed | Tool-returned schema only |
| Public examples | Initial observation and check feedback; structural headings, counts and match signals guide repair | Yes; result cell values are not copied into SQL |

No model, LoRA adapter, non-LLM classifier, embedding index, or learned ranker was trained. No synthetic task-specific training material was produced. There are no model training logs because no training took place. The code does not include a task-ID-to-SQL map or other benchmark answer lookup. Validation and test evaluation remain separate from the agent's permitted inputs; the evaluator is not imported to rank candidates.

## Shared model-output cache

`model_generation.json` records original drafts from `Qwen/Qwen3-0.6B`, immutable revision `c1899de289a04d12100db370d81485cdf75e47ca`, generated from question and schema only. Provider settings include 384 maximum new tokens, temperature 0.7, top-p 0.8, top-k 20, thinking disabled, and seed base 750608.

`hint_generation.json` records four original-draft repair suggestions per task from `Qwen/Qwen3-8B`, immutable revision `b968826d9c46dd6066d109eabc6255188de91218`, with no adapter or assignment fine-tuning. Its recorded inputs are question, schema, draft, public example and causal public SQL feedback. Provider settings include four draws, no refinement draws, thinking disabled, 512 maximum new tokens, and seed 751110. The cache identifies its semantics as original-draft root proposals, not adaptive suggestions conditioned on later controller feedback.

The submission consumes this authorized shared cache but loads neither model. Cache-generation compute, including any provider GPU use, is not the submitted agent's inference or training cost. No runtime model identity, model revision, parameter-count declaration, or adapter loading code is required for this no-live-model route; provider identities are listed solely for transparent provenance.

## External assistance and reproducibility boundary

OpenAI Codex provided development assistance with code, debugging, evaluation orchestration, tests, documentation and submission preparation. No external LLM or network service is contacted by the agent during grading. The source package and declarations must not be read as claiming unaided authorship.

The official environment, predictor, scorer, executor, task files, cache, and grading files remain unchanged. Agent configuration is separate under `submission/`; reproduced results and runtime records are written outside the official package. `scripts/reproduce.py` invokes the official command-line entry points and retains complete unmodified predictions and score output. Submission helper files under `scripts/official/` reproduce the website's public validation/encryption logic; they are never imported by the SQL agent.

The canonical `outputs/test.json` and `outputs/test-score.json` are unchanged copies of the Linux run evaluated at implementation commit `32a7addf948ae132369c4b7a91549bccbc363f37`. The original Linux evidence is retained under `outputs/linux/`, and the separate Windows test run under `outputs/windows/`. Both runs agree on all final SQL strings and grading pass/fail flags, but intermediate feedback differs on two tasks. Linux traces were selected for the required Linux reproduction environment; no traces were merged or rewritten to hide platform differences. The full comparison and file hashes appear in `REPORT.md`.

The publication receipt identifies the immutable source archive. The report records the evaluated implementation commit and the final test-score/prediction hashes. Runtime JSON includes environment-specific paths and measurements; no authentication tokens, private keys, database copies, virtual environments, or caches belong in the archive.
