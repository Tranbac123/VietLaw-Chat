"""VietLaw Public Beta V0 evaluation set (task §14).

A small, self-contained sibling of the main `evaluation/` HTTP-black-box
platform, not merged into it. Two reasons:

1. The main platform's `dataset.py` treats `data/legal_snippets.json` as the
   only frozen ground truth of "sources that exist" -- it does not yet know
   about the new curated traffic pack (`data/traffic_rules.json`), so its
   `source_oracle` would reject every genuine curated-traffic citation as
   fabricated until that ground truth is deliberately extended.
2. The main platform is architecturally black-box-over-HTTP against a spawned
   `uvicorn` process (`clients/process_manager.py`). This sibling instead
   drives the FastAPI app in-process via `TestClient`, which is enough to
   exercise the real request/response contract deterministically without a
   second server process, while staying just as free of live network/provider
   calls.

See `evaluation/legal_beta_v0/run.py` for the runner and
`evaluation/legal_beta_v0/cases.py` for the case dataset.
"""
