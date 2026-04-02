# dataset_branching

Velocity-first branching augmentation (lightweight) with immediate-save behavior.

## Goal

- Start from `foamgpt_train.jsonl`
- Group by unique `user_prompt`
- For each case, create velocity variants at:
  - +10%
  - +20%
  - +30%
- Update `0/U` velocity vectors directly
- Run through Foam-Agent
- If successful, save rows immediately to output JSONL
- If failed, discard into failed JSONL

## Files

- `scripts/map_cases_to_tutorials.py`
  - builds case-to-tutorial mapping JSON
- `scripts/velocity_branching_pipeline.py`
  - main pipeline
- `output/`
  - immediate append outputs

## 1) Build case mapping

```bash
python scripts/map_cases_to_tutorials.py \
  --train-jsonl "C:/Users/Peijing Xu/projects/yue_research/dataset/foamgpt_train.jsonl" \
  --tutorials-root "<PATH_TO_OPENFOAM_TUTORIALS>" \
  --out "case_tutorial_map.json"
```

## 2) Run velocity branching pipeline

```bash
python scripts/velocity_branching_pipeline.py \
  --input "C:/Users/Peijing Xu/projects/yue_research/dataset/foamgpt_train.jsonl" \
  --case-map "case_tutorial_map.json" \
  --foam-agent-dir "C:/Users/Peijing Xu/projects/yue_research/dataset/Foam-Agent" \
  --work-dir "work" \
  --out-jsonl "output/accepted_velocity.jsonl" \
  --fail-jsonl "output/failed_velocity.jsonl" \
  --timeout-sec 2600
```

## Immediate save behavior

Each successful case variant is appended to `output/accepted_velocity.jsonl` immediately (no end-of-run wait).

## Notes

- Pipeline keeps only files in `0/`, `system/`, `constant/`.
- It patches `0/U` by scaling all `uniform (x y z)` vectors.
- If Foam-Agent run fails or has no positive time directory, variant is discarded.
