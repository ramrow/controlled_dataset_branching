#!/bin/bash
set -e
cd /mnt/home/DDN_Copy/rpi/pxu10/dataset_branching/slurm
sbatch map_chunk_0.slurm
sbatch map_chunk_1.slurm
sbatch map_chunk_2.slurm
sbatch map_chunk_3.slurm
