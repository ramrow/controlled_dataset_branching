# dataset_branching

Velocity-first branching augmentation with immediate-save behavior.

## Scope

- Uses both `foamgpt_train.jsonl` and `foamgpt_test.jsonl` for case-to-tutorial mapping.
- Exports matched prompt groups into unique numeric folders with:
  - `user_prompt.txt`
  - `system_prompt.txt`
  - `0/`, `system/`, `constant/`
  - excludes `constant/polyMesh/**`

## Scripts

- `scripts/map_cases_to_tutorials.py` — map case names to OpenFOAM tutorials (heuristic + optional Bedrock Sonnet fallback)
- `scripts/merge_case_maps.py` — merge chunked case-map outputs
- `scripts/export_matched_prompt_cases.py` — export matched prompt groups to unique-id folders
- `scripts/velocity_branching_pipeline.py` — velocity +10/+20/+30 pipeline with immediate save

## One-shot mapping (both train + test)

`python scripts/map_cases_to_tutorials.py --inputs foamgpt_train.jsonl foamgpt_test.jsonl --tutorials-root /mnt/home/pxu10/OpenFOAM/OpenFOAM-10/tutorials --out case_tutorial_map.json --use-bedrock`

## 4-batch mapping with SLURM

Submit all 4 chunks:

`bash /mnt/home/DDN_Copy/rpi/pxu10/dataset_branching/slurm/submit_map_chunks.sh`

Each chunk writes:
- `case_tutorial_map_chunk_0.json`
- `case_tutorial_map_chunk_1.json`
- `case_tutorial_map_chunk_2.json`
- `case_tutorial_map_chunk_3.json`

Merge chunk outputs:

`bash /mnt/home/DDN_Copy/rpi/pxu10/dataset_branching/slurm/merge_map_chunks.sh`

Final merged file:
- `case_tutorial_map.json`

## Export matched prompt groups into unique-id folders

`python scripts/export_matched_prompt_cases.py --jsonl foamgpt_train.jsonl --case-map case_tutorial_map.json --out-dir matched_data --digits 4`

## Run velocity branching pipeline (+10%, +20%, +30%)

`python scripts/velocity_branching_pipeline.py --input foamgpt_train.jsonl --case-map case_tutorial_map.json --foam-agent-dir /mnt/home/DDN_Copy/rpi/pxu10/dataset/Foam-Agent --work-dir work --out-jsonl output/accepted_velocity.jsonl --fail-jsonl output/failed_velocity.jsonl --timeout-sec 2600`

## Immediate-save guarantee

Successful variants are appended immediately to `output/accepted_velocity.jsonl` (flush + fsync on each write).

Failed variants are appended immediately to `output/failed_velocity.jsonl`.
