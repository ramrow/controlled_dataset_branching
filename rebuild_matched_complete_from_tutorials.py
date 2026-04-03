import argparse
import json
import shutil
from pathlib import Path


def copy_dir(src: Path, dst: Path):
    if not src.exists() or not src.is_dir():
        return False
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    return True


def main():
    ap = argparse.ArgumentParser(description='Rebuild matched_complete by copying full 0/constant/system from tutorial_path in meta.json')
    ap.add_argument('--source', default='matched_hf_raw', help='Source folder with numeric IDs and meta.json')
    ap.add_argument('--target', default='matched_complete', help='Target folder to rebuild')
    ap.add_argument('--clean-target', action='store_true', help='Delete target first')
    args = ap.parse_args()

    root = Path(__file__).resolve().parent
    src_root = (root / args.source).resolve()
    dst_root = (root / args.target).resolve()

    if not src_root.exists():
        raise SystemExit(f'Source not found: {src_root}')

    if dst_root.exists() and args.clean_target:
        shutil.rmtree(dst_root)
    dst_root.mkdir(parents=True, exist_ok=True)

    kept = 0
    skipped = 0

    for d in sorted([p for p in src_root.iterdir() if p.is_dir() and p.name.isdigit()]):
        meta_path = d / 'meta.json'
        if not meta_path.exists():
            skipped += 1
            continue

        meta = json.loads(meta_path.read_text(encoding='utf-8'))
        tutorial_path = Path(meta.get('tutorial_path') or '')
        if not tutorial_path.exists() or not tutorial_path.is_dir():
            skipped += 1
            continue

        out = dst_root / d.name
        out.mkdir(parents=True, exist_ok=True)

        # preserve prompt + metadata from matched source
        shutil.copy2(meta_path, out / 'meta.json')
        if (d / 'user_prompt.txt').exists():
            shutil.copy2(d / 'user_prompt.txt', out / 'user_prompt.txt')
        if (d / 'system_prompt.txt').exists():
            shutil.copy2(d / 'system_prompt.txt', out / 'system_prompt.txt')

        ok0 = copy_dir(tutorial_path / '0', out / '0')
        okc = copy_dir(tutorial_path / 'constant', out / 'constant')
        oks = copy_dir(tutorial_path / 'system', out / 'system')

        # Require all three folders
        if ok0 and okc and oks:
            kept += 1
        else:
            # remove incomplete output folder
            shutil.rmtree(out, ignore_errors=True)
            skipped += 1

    summary = {
        'source': str(src_root),
        'target': str(dst_root),
        'kept': kept,
        'skipped': skipped,
    }
    (dst_root / 'rebuild_summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
