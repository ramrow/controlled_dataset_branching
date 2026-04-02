#!/bin/bash
#SBATCH -N 1
#SBATCH -n 1
#SBATCH -p rpi
#SBATCH -A rpi
#SBATCH --gres=gpu:nvidia_h100_80gb_hbm3:1
#SBATCH --time=04:00:00
#SBATCH --output=%x_out
#SBATCH --error=%x_err

source /mnt/lustre/rpi/pxu10/agent/bin/activate
source /mnt/home/DDN_Copy/rpi/pxu10/dataset_branching/slurm/aws_env.sh
cd /mnt/home/DDN_Copy/rpi/pxu10/dataset_branching
python scripts/map_cases_to_tutorials.py --inputs /mnt/home/DDN_Copy/rpi/pxu10/dataset_branching/foamgpt_train.jsonl /mnt/home/DDN_Copy/rpi/pxu10/dataset_branching/foamgpt_test.jsonl --tutorials-root /mnt/home/pxu10/OpenFOAM/OpenFOAM-10/tutorials --out case_tutorial_map_chunk_2.json --use-bedrock --chunk-index 2 --chunk-count 4

