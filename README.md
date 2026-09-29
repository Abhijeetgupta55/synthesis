# smart-ci-tcp — Smart CI Test Prioritization

Rank CI test classes so failures surface early, with a focus on **first-time failures** (tests that never failed
before, which history-based prioritisation cannot predict). The data is LRTS (ISSTA 2024), 10 Apache projects,
Jenkins PR builds 2020–2024, test-class granularity.

**Status:** repository, data pipeline and EDA only. `features/`, `baselines/`, `models/`, `evaluation/` and `plugin/`
are empty stubs. Findings: [`reports/EDA_REPORT.md`](reports/EDA_REPORT.md).

## Reproduce the EDA (Windows or Linux)

```bash
uv venv --python 3.11 .venv            # or: python3.11 -m venv .venv
uv pip install --python .venv -e ".[dev]"
# activate: .venv\Scripts\activate (Windows)  |  source .venv/bin/activate (Linux)

python -m stp.data.download            # shallow-clone LRTS to external/, gdown the 3.0 GB zip, extract (14.8 GB)
python -m stp.data.build_tables        # data/raw -> data/interim/*.parquet   (~30-60 min, streams, ~3 GB RAM)
python -m stp.data.audit               # count cross-checks -> reports/eda_json/audit.json
python -m stp.eda.run_all              # sections A-H -> reports/figures/*.png, reports/eda_json/*.json
jupyter nbconvert --to notebook --execute --inplace notebooks/01_eda.ipynb
pytest
```

Section A (paper baselines) needs only the LRTS git repo, so `python -m stp.data.download --skip-gdrive` followed by
`python -m stp.eda.a_baselines` works without the big download. If `gdown` fails (quota), download
<https://drive.google.com/file/d/13vnCA0tY2BMY9irfn0nV01bJnST6z4kx/view> manually into `data/raw/` and re-run
`python -m stp.data.download`.

## Layout

| Path | What |
|---|---|
| `configs/data.yaml` | paths, project list, split fractions, EDA sample sizes |
| `src/stp/paths.py` | every path, resolved from the config |
| `src/stp/data/` | `download.py`, `build_tables.py` (tidy parquet), `audit.py` (count checks) |
| `src/stp/eda/` | one module per EDA section (A–H); each writes figures and a JSON of numbers |
| `data/{raw,interim,processed}` | gitignored |
| `external/LRTS` | shallow clone of lrtsuser/LRTS (MIT), gitignored |
