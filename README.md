# DASE7506 MP3 — SQL Repair Agent

**Guo Yang · 3036797817 · Final v2 submission, 12 November 2026**

A CPU-only SQL repair controller using real official tool feedback, fixed shared repair hints, and SQLGlot syntax-tree edits. It does not train or load a language model, use a GPU, or contact a model API. `--checkpoint` loads a JSON configuration, not model weights.

| Official evaluation | Correct | Accuracy |
|---|---:|---:|
| Validation | 98 / 120 | 81.67% |
| Test, requiring all three instances | 182 / 240 | 75.83% |

The canonical agent is **`submission/submission.py:create_agent`**, configured by **`submission/config.json`**. The complete unchanged official predictions and score are **`outputs/test.json`** and **`outputs/test-score.json`**. These are student-side results from the official scorer, subject to instructor verification.

The formal run completed prediction and scoring in **20.289 seconds**, with **115.934 MiB** peak sampled process-tree RSS and **791.516 MiB** virtual memory. All **51 synthetic regression tests** passed. The formal [Linux reproduction](https://github.com/gy13687638535-design/DASE7506-MP3-SQL-Repair/actions/runs/43217148261) evaluates the canonical entry point. See [REPORT.md](REPORT.md) for the agent loop, controlled ablations, failure cases, runtime measurements, safety and assistance disclosure, and [DATA_PROVENANCE.md](DATA_PROVENANCE.md) for data access boundaries.

## Reproduce on Linux

Use Python 3.11 or 3.12. Download the unchanged [official student package](https://xudongwu-0.github.io/courses/dase7506/mp3/downloads/MP3_SQL_student_package.zip?v=406d69507ccf) and extract it outside this repository. Its ZIP SHA-256 is `406d69507ccf955a53b35db1c1368bd7452565ebd928b47d0f6161fe35b99a61`.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
PACKAGE=/absolute/path/to/MP3_SQL_student_package
python -m pip install -r "$PACKAGE/requirements.txt" -r requirements.txt
(cd "$PACKAGE" && python -m mp3_sql.check_data)
PYTHONPATH="$PWD/submission" python -m unittest discover -s tests -v
PYTHONPATH="$PWD/experiments/v2" python -m unittest discover -s experiments -p 'test_*.py' -v
python scripts/reproduce.py --package "$PACKAGE" --split test --output-dir outputs/reproduced-test
```

Provision dependencies and data before offline evaluation. The wrapper invokes the unchanged official predictor and scorer with four workers, enforces a combined 180-second deadline, limits CPU affinity to at most four CPUs, applies a 2 GiB per-process address-space limit, and monitors aggregate process-tree virtual memory. It records resource measurements separately from the official score.

To reproduce the selected configuration and final controlled validation comparisons:

```bash
python scripts/reproduce.py --package "$PACKAGE" --split validation --ablations --output-dir outputs/reproduced-validation
```

Equivalent direct official test commands, without the wrapper's resource monitoring:

```bash
EXPORT="$PWD"
mkdir -p outputs/reproduced-test
cd "$PACKAGE"
PYTHONPATH="$EXPORT/submission" python -m mp3_sql.predict --split test --workers 4 \
  --method "$EXPORT/submission/submission.py" --checkpoint "$EXPORT/submission/config.json" \
  --output "$EXPORT/outputs/reproduced-test/test.json"
python -m mp3_sql.score --split test --workers 4 \
  --predictions "$EXPORT/outputs/reproduced-test/test.json" \
  --output "$EXPORT/outputs/reproduced-test/test-score.json"
```

## Code and evidence

```text
submission/
  submission.py       Decide the next official tool action and select checked SQL
  repairs.py          Basic schema, projection, grouping and ordering repairs
  semantic_repairs.py Semantic candidate generation and projection-reference repair
  ranking.py          Fixed, untrained structural scoring among checked matches
  config.json         Frozen selected configuration; no model weights
outputs/              Canonical test predictions, score and runtime evidence
experiments/          Validation comparisons, selection record and exploration history
tests/                Synthetic protocol, safety and SQL regression tests
scripts/reproduce.py  Official evaluator orchestration and resource measurements
REPORT.md             Final method, results, limitations and reproduction details
DATA_PROVENANCE.md    Dataset identity, permitted access and assistance disclosure
```

The canonical implementation is a byte-for-byte promotion of the validation-selected `experiments/v2` candidate. [experiments/selection.json](experiments/selection.json) freezes its configuration and source hashes before the first v2 test. [The Chinese experiment report](experiments/README.md) explains the structure and all 15 configuration trials; its earlier exploration status is historical. Final submission evidence is identified by this README and `REPORT.md`.

The previous submission scored 175/240 (72.92%); v2 scores 182/240 (75.83%). The first comparison found eight formerly incorrect tasks repaired and one formerly correct task regressed. The prior immutable source commit, `7b6ba20f79a2731fc5b1db24888cfb8205c70476`, remains available for audit. This export and its GitHub issue use a new immutable source ZIP; the old issue and archive are retained as required by the course's update procedure.

## 中文说明

本次正式版本为 v2：验证集 98/120，测试集 182/240。查看 `submission/` 理解代码，查看 `outputs/test-score.json` 核对官方成绩，按上面的命令复现。评分要求每题在三个数据库实例上都正确，公开示例通过不等于最终正确。没有训练模型，也没有模型权重检查点；配置文件只控制修复策略。

课程要求更新成绩时创建新 Issue，排行榜采用截止前最高的可复现成绩，因此保留旧提交记录。提交仍属于学生自报成绩，课程方验证另行进行。

## Attribution

[Official project specification](https://xudongwu-0.github.io/courses/dase7506/mp3/PROJECT.md). Spider-derived data and course modifications retain CC BY-SA 4.0 attribution; see the official package `NOTICE`. SQLGlot is MIT licensed. OpenAI Codex assisted development, evaluation, documentation and submission preparation; the agent does not contact Codex during grading. No benchmark databases, model weights, virtual environments, caches or credentials are included in the source export.
