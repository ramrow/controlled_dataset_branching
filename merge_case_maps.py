import argparse
import json
from pathlib import Path


def load_map(path: Path):
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding='utf-8'))


def main():
    ap = argparse.ArgumentParser(description='Merge chunked case_tutorial_map files')
    ap.add_argument('--inputs', nargs='+', required=True)
    ap.add_argument('--out', default='case_tutorial_map.json')
    args = ap.parse_args()

    merged = {}
    for i in args.inputs:
        for row in load_map(Path(i)):
            merged[row['case_name']] = row

    rows = sorted(merged.values(), key=lambda x: x['case_name'])
    Path(args.out).write_text(json.dumps(rows, indent=2), encoding='utf-8')
    matched = sum(1 for x in rows if x.get('matched'))
    print(f"merged_cases={len(rows)} matched={matched} unmatched={len(rows)-matched}")
    print(args.out)


if __name__ == '__main__':
    main()
