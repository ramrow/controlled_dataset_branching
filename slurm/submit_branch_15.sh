#!/bin/bash
set -e
cd /mnt/lustre/rpi/pxu10/branching/slurm
sbatch branch_chunk_0.slurm
sbatch branch_chunk_1.slurm
sbatch branch_chunk_2.slurm
sbatch branch_chunk_3.slurm
sbatch branch_chunk_4.slurm
sbatch branch_chunk_5.slurm
sbatch branch_chunk_6.slurm
sbatch branch_chunk_7.slurm
sbatch branch_chunk_8.slurm
sbatch branch_chunk_9.slurm
sbatch branch_chunk_10.slurm
sbatch branch_chunk_11.slurm
sbatch branch_chunk_12.slurm
sbatch branch_chunk_13.slurm
sbatch branch_chunk_14.slurm
