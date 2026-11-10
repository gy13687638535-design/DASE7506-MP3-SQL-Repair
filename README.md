# DASE7506 MP3 - SQL Repair Agent

**Author:** Guo Yang (3036797817)  
**Route:** CPU-only harness optimization; no live model, no LoRA, no training.

The agent checks the original draft, reads the shared cached repair hints when
needed, generates read-only AST edits from feedback, and checks candidates within
the official eight-call budget. Empty/all-NULL example matches receive an extra
hint-based check before selection. It runs offline using Python 3.11 or 3.12 and
SQLGlot 27.29.0.

## Reproduce

Download the unchanged official [student package](https://xudongwu-0.github.io/courses/dase7506/mp3/downloads/MP3_SQL_student_package.zip?v=406d69507ccf).
Its ZIP SHA-256 is `406d69507ccf955a53b35db1c1368bd7452565ebd928b47d0f6161fe35b99a61`.
Extract it outside this repository; the dataset is intentionally not distributed here.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
PACKAGE=/absolute/path/to/MP3_SQL_student_package
(cd "$PACKAGE" && python -m mp3_sql.check_data)
python -m unittest discover -s tests -v
python scripts/reproduce.py --package "$PACKAGE" --split test --output-dir outputs/reproduced
```

The runner invokes the unchanged official predictor and scorer with four workers,
enforces a combined 180-second deadline, and records CPU/memory measurements
separately. On Linux it restricts CPU affinity to at most four CPUs, imposes a
2 GiB address-space ceiling per process, and checks aggregate process-tree VMS.
Provision dependencies/data before running offline evaluation. Windows execution
is supported for development, but its resource measurements have a narrower scope.

To reproduce all validation comparisons:

```bash
python scripts/reproduce.py --package "$PACKAGE" --split validation --ablations --output-dir outputs/validation-reproduced
```

Direct official commands, equivalent to the full-agent run:

```bash
EXPORT=/absolute/path/to/this/repository
cd "$PACKAGE"
PYTHONPATH="$EXPORT/submission" python -m mp3_sql.predict --split test --workers 4 \
  --method "$EXPORT/submission/submission.py" --checkpoint "$EXPORT/submission/config.json" \
  --output "$EXPORT/outputs/test.json"
python -m mp3_sql.score --split test --workers 4 \
  --predictions "$EXPORT/outputs/test.json" --output "$EXPORT/outputs/test-score.json"
```

`outputs/test-score.json` is the complete, unmodified official score. The scorer
replays the tool traces and checks all three instances for every one of 240 tasks.
See `REPORT.md` for measured results, controlled ablations, failure analysis,
security considerations and assistance disclosure.

## Contents

- `submission/`: portable agent, generic repair rules and ablation configurations.
- `outputs/`: predictions, official scores and resource evidence.
- `tests/`: synthetic protocol, safety and SQL transformation regression tests.
- `scripts/reproduce.py`: evaluator orchestration and measurement; no agent imports it.
- `.github/workflows/reproduce.yml`: Linux reproduction using the verified official ZIP.
- `scripts/prepare_submission.mjs`: official form-compatible encrypted GitHub handoff.
- `scripts/github_publish.py`: optional maintainer publication helper; not used in grading.

No benchmark database, grading reference, model weights, virtual environment,
access token or task-specific SQL lookup is included in the source export.
The final submission uses a GitHub archive URL pinned to the full source commit.

## 中文使用说明

正式结果查看 `outputs/test-score.json`，方法与实验查看 `REPORT.md`。
评分是 240 道题在三个数据库实例上全部正确的比例，不能用公开示例通过率替代。
本项目不需要 GPU、API Key 或模型下载。报告公开披露了 Codex 开发辅助；
代理运行时仅调用课程提供的工具，不能读取额外评分数据库或答案。

## Attribution

Course specification: <https://xudongwu-0.github.io/courses/dase7506/mp3/>.
Spider-derived benchmark and course modifications: CC BY-SA 4.0; see `NOTICE`.
SQLGlot is MIT licensed. Shared cached hints are course-provided Qwen outputs;
they are fallible suggestions, not trained weights or gold answers in this export.
