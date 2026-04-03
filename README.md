# dataset_branching

Branching augmentation pipeline that reuses matched case files and applies velocity perturbations.

## What this pipeline does

- Uses pre-matched case folders from `matched_hf_raw` (or `matched_complete`) as the reusable base.
- Always skips initial file generation by passing `--reuse_generated_dir` to Foam-Agent.
- For each matched prompt-group, creates velocity variants:
  - +10%
  - +20%
  - +30%
- Patches `0/U` directly for each variant.
- Runs Foam-Agent (runner + reviewer + rewrite still active).
- If successful, appends dataset rows immediately (no end-of-run wait).

## Output row fields

Each accepted row includes at least:
- `system_prompt` (rebuilt per file using base system prompt with updated `<file_name>` and `<folder_name>`)
- `user_prompt` (velocity-updated)
- `user_requirement` (velocity-updated)
- `file_content`
- `case_name`, `folder_name`, `file_name`, `variant_id`, `velocity_scale_factor`, `source_prompt_id`

## Required folders/files

At repo root (`/mnt/lustre/rpi/pxu10/branching` on cluster):
- `matched_hf_raw/`
- `Foam-Agent/`
- `velocity_branching_pipeline.py`
- `slurm/aws_env.sh`

## AWS env file

`slurm/aws_env.sh` should define:

```bash
export AWS_ACCESS_KEY_ID="..."
export AWS_SECRET_ACCESS_KEY="..."
export AWS_SESSION_TOKEN="..."
```

## Run locally (single process)

```bash
python velocity_branching_pipeline.py --matched-root /mnt/lustre/rpi/pxu10/branching/matched_hf_raw --foam-agent-dir /mnt/lustre/rpi/pxu10/branching/Foam-Agent --work-dir /mnt/lustre/rpi/pxu10/branching/work --out-jsonl /mnt/lustre/rpi/pxu10/branching/output/accepted_velocity.jsonl --fail-jsonl /mnt/lustre/rpi/pxu10/branching/output/failed_velocity.jsonl --timeout-sec 2600 --chunk-index 0 --chunk-count 1
```

## 15-batch SLURM parallel run

Generated files:
- `slurm/branch_chunk_0.slurm` ... `slurm/branch_chunk_14.slurm`
- `slurm/submit_branch_15.sh`

Submit all 15:

```bash
cd /mnt/lustre/rpi/pxu10/branching/slurm
bash submit_branch_15.sh
```

Each chunk runs with:
- `--chunk-index <0..14>`
- `--chunk-count 15`

## Mapping/export utilities (optional)

Root-level utilities available:
- `map_cases_to_tutorials.py`
- `merge_case_maps.py`
- `export_matched_prompt_cases.py`
- `rebuild_matched_hf_raw.py`

If mapping with Bedrock Sonnet is needed:

```bash
python map_cases_to_tutorials.py --inputs foamgpt_train.jsonl foamgpt_test.jsonl --tutorials-root /mnt/home/pxu10/OpenFOAM/OpenFOAM-10/tutorials --out case_tutorial_map.json --use-bedrock
```

## Immediate-save guarantee

- Success rows are appended immediately to `output/accepted_velocity.jsonl`.
- Failures are appended immediately to `output/failed_velocity.jsonl`.
