#!/bin/bash
#SBATCH -N 1
#SBATCH -n 1
#SBATCH -p rpi
#SBATCH -A rpi
#SBATCH --gres=gpu:nvidia_h100_80gb_hbm3:1
#SBATCH --time=10:00:00
#SBATCH --output=%x_out
#SBATCH --error=%x_err

source /mnt/lustre/rpi/pxu10/agent/bin/activate
source /mnt/lustre/rpi/pxu10/branching/slurm/aws_env.sh
cd /mnt/lustre/rpi/pxu10/branching
python velocity_branching_pipeline.py --matched-root /mnt/lustre/rpi/pxu10/branching/matched_hf_raw --work-dir /mnt/lustre/rpi/pxu10/branching/work --out-jsonl /mnt/lustre/rpi/pxu10/branching/output/accepted_velocity.jsonl --fail-jsonl /mnt/lustre/rpi/pxu10/branching/output/failed_velocity.jsonl --timeout-sec 2600 --chunk-index 10 --chunk-count 15

