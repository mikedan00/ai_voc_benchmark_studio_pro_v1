# Hotfix v1.0.2

## Fixed

- Fixed `TypeError` in RAG answer generation caused by calling `build_rag_answer_prompt()` with positional arguments while the function was keyword-only.
- Fixed the same positional/keyword compatibility risk in `build_voc_insight_report_prompt()`.
- Updated `app.py` to call prompt builders with explicit keyword arguments.
- Kept prompt builder functions backward-compatible with both positional and keyword call styles.

## Validation

```bash
python -m py_compile app.py models/*.py utils/*.py
pytest -q
```

Result: `4 passed`.
