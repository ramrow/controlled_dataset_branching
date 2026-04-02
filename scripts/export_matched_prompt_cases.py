import argparse
import json
from pathlib import Path
from collections import defaultdict


def load_jsonl(path: Path):
    rows = []
    with path.open('r', encoding='utf-8') as f:
        for i, line in enumerate(f, 1):
            if line.strip():
                rows.append(json.loads(line))
    return rows


def normalize_rel(folder_name: str, file_name: str):
    fd = (folder_name or '').replace('\\', '/').strip()
    fn = (file_name or '').replace('\\', '/').strip()
    if not fn:
        return ''
    if not fd or fd in {'.', './'}:
        return fn
    return f"{fd}/{fn}".strip('/')


def in_scope(rel: str):
    if not rel:
        return False
    top = rel.split('/', 1)[0]
    if top not in {'0', 'system', 'constant'}:
        return False
    if rel.startswith('constant/polyMesh/') or rel == 'constant/polyMesh':
        return False
    return True


def main():
    ap = argparse.ArgumentParser(description='Export matched user_prompt groups to unique-id folders')
    ap.add_argument('--jsonl', required=True, help='Input dataset jsonl (train or test)')
    ap.add_argument('--case-map', required=True, help='case_tutorial_map.json from mapping step')
    ap.add_argument('--out-dir', default='matched_data', help='Output directory')
    ap.add_argument('--digits', type=int, default=4, help='Zero-padding digits for folder ids')
    args = ap.parse_args()

    rows = load_jsonl(Path(args.jsonl))
    case_map = json.loads(Path(args.case_map).read_text(encoding='utf-8'))
    case_to_map = {x.get('case_name'): x for x in case_map}

    groups = defaultdict(list)
    for r in rows:
        up = (r.get('user_prompt') or '').strip()
        if up:
            groups[up].append(r)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    prompt_index = []
    exported = 0

    for i, (user_prompt, grp) in enumerate(sorted(groups.items(), key=lambda kv: kv[0]), start=1):
        rep = grp[0]
        case_name = rep.get('case_name')
        m = case_to_map.get(case_name) or {}
        if not m.get('matched'):
            continue

        uid = f"{i:0{args.digits}d}"
        root = out_dir / uid
        root.mkdir(parents=True, exist_ok=True)

        system_prompt = rep.get('system_prompt', '')
        user_requirement = rep.get('user_requirement', '')

        meta = {
            'id': uid,
            'case_name': case_name,
            'tutorial_path': m.get('tutorial_path'),
            'match_method': m.get('method'),
            'match_confidence': m.get('confidence'),
            'user_prompt': user_prompt,
            'system_prompt': system_prompt,
            'user_requirement': user_requirement,
            'rows_in_group': len(grp),
        }
        (root / 'meta.json').write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding='utf-8')
        (root / 'user_prompt.txt').write_text(user_prompt, encoding='utf-8')
        (root / 'system_prompt.txt').write_text(system_prompt, encoding='utf-8')

        for r in grp:
            rel = normalize_rel(r.get('folder_name', ''), r.get('file_name', ''))
            if not in_scope(rel):
                continue
            out_path = root / rel
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(r.get('file_content', ''), encoding='utf-8')

        prompt_index.append({'id': uid, 'case_name': case_name, 'tutorial_path': m.get('tutorial_path')})
        exported += 1

    (out_dir / 'index.json').write_text(json.dumps(prompt_index, indent=2), encoding='utf-8')
    print(json.dumps({'groups_total': len(groups), 'groups_exported': exported, 'out_dir': str(out_dir)}, indent=2))


if __name__ == '__main__':
    main()
