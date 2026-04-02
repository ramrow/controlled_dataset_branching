#!/bin/bash
set -e
cd /mnt/home/DDN_Copy/rpi/pxu10/dataset_branching
python scripts/merge_case_maps.py --inputs case_tutorial_map_chunk_0.json case_tutorial_map_chunk_1.json case_tutorial_map_chunk_2.json case_tutorial_map_chunk_3.json --out case_tutorial_map.json
