import argparse
import shutil
from pathlib import Path


def main():
    ap = argparse.ArgumentParser(description='Recreate matched_hf_raw from matched_complete')
    ap.add_argument('--source', default='matched_complete', help='Source folder')
    ap.add_argument('--target', default='matched_hf_raw', help='Target folder to create')
    ap.add_argument('--clean', action='store_true', help='Delete target if it exists before copy')
    args = ap.parse_args()

    root = Path(__file__).resolve().parents[1]
    src = (root / args.source).resolve()
    dst = (root / args.target).resolve()

    if not src.exists() or not src.is_dir():
        raise SystemExit(f'Source not found: {src}')

    if dst.exists():
        if args.clean:
            shutil.rmtree(dst)
        else:
            raise SystemExit(f'Target already exists: {dst}. Use --clean to overwrite.')

    shutil.copytree(src, dst)
    print(f'Created: {dst}')


if __name__ == '__main__':
    main()
