import argparse
import json
import os
import hashlib
from pathlib import Path
from collections import defaultdict

MODEL_ARN = 'arn:aws:bedrock:us-west-2:567316078106:inference-profile/us.anthropic.claude-sonnet-4-6'


def load_rows(paths):
    rows = []
    for pp in paths:
        path = Path(pp)
        with path.open('r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    rows.append(json.loads(line))
    return rows


def group_case_requirements(rows):
    grp = defaultdict(list)
    for r in rows:
        cn = (r.get('case_name') or '').strip()
        if cn:
            grp[cn].append(r)
    out = {}
    for cn, rs in grp.items():
        req_counts = defaultdict(int)
        for r in rs:
            req = (r.get('user_requirement') or '').strip()
            if req:
                req_counts[req] += 1
        req = max(req_counts.items(), key=lambda kv: kv[1])[0] if req_counts else ''
        out[cn] = req
    return out


def list_tutorial_candidates(tutorials_root: Path):
    cands = []
    for p in tutorials_root.rglob('*'):
        if not p.is_dir():
            continue
        if (p / '0').exists() or (p / 'system').exists() or (p / 'constant').exists():
            cands.append(p)
    return sorted(set(cands))


def heuristic_match(case_name: str, candidates):
    target = case_name.lower()
    for c in candidates:
        if c.name.lower() == target:
            return c, 'heuristic_exact'
    for c in candidates:
        n = c.name.lower()
        if target in n or n in target:
            return c, 'heuristic_contains'
    norm_target = ''.join(ch for ch in target if ch.isalnum())
    for c in candidates:
        nn = ''.join(ch for ch in c.name.lower() if ch.isalnum())
        if nn == norm_target:
            return c, 'heuristic_norm_exact'
    return None, 'heuristic_none'


def maybe_bedrock_client(enabled: bool, region: str):
    if not enabled:
        return None
    try:
        import boto3
        return boto3.client('bedrock-runtime', region_name=region)
    except Exception:
        return None


def llm_match_case(client, model_id: str, case_name: str, requirement: str, candidates, top_k: int = 120):
    cands = candidates[:top_k]
    cand_text = '\n'.join([f"{i}: {str(p)}" for i, p in enumerate(cands)])
    system = 'You map dataset case names to OpenFOAM tutorial paths. Return strict JSON only: {"index": int, "confidence": float, "reason": str}. If none matches, index=-1.'
    user = f"case_name: {case_name}\nuser_requirement: {requirement}\n\ncandidates:\n{cand_text}\n\nReturn strict JSON only."

    resp = client.converse(
        modelId=model_id,
        system=[{"text": system}],
        messages=[{"role": "user", "content": [{"text": user}]}],
        inferenceConfig={"maxTokens": 220, "temperature": 0.0},
    )

    text = ''
    for blk in resp.get('output', {}).get('message', {}).get('content', []):
        if isinstance(blk, dict) and 'text' in blk:
            text += blk['text']

    s = text.strip()
    if s.startswith('```'):
        s = s.strip('`').replace('json', '', 1).strip()
    i0 = s.find('{'); i1 = s.rfind('}')
    if i0 >= 0 and i1 > i0:
        s = s[i0:i1+1]
    obj = json.loads(s)

    idx = int(obj.get('index', -1))
    conf = float(obj.get('confidence', 0.0))
    reason = str(obj.get('reason', ''))
    if 0 <= idx < len(cands):
        return cands[idx], conf, reason, len(cands)
    return None, conf, reason, len(cands)


def stable_bucket(key: str, chunk_count: int):
    h = hashlib.sha256(key.encode('utf-8')).hexdigest()
    return int(h[:12], 16) % chunk_count


def main():
    ap = argparse.ArgumentParser(description='Map dataset cases to OpenFOAM tutorials (supports train+test + chunking)')
    ap.add_argument('--inputs', nargs='+', required=True, help='One or more JSONL files (e.g., train and test)')
    ap.add_argument('--tutorials-root', required=True)
    ap.add_argument('--out', default='case_tutorial_map.json')
    ap.add_argument('--use-bedrock', action='store_true')
    ap.add_argument('--region', default=os.getenv('AWS_REGION') or os.getenv('AWS_DEFAULT_REGION') or 'us-west-2')
    ap.add_argument('--model-id', default=MODEL_ARN)
    ap.add_argument('--top-k', type=int, default=120)
    ap.add_argument('--chunk-index', type=int, default=0)
    ap.add_argument('--chunk-count', type=int, default=1)
    args = ap.parse_args()

    rows = load_rows(args.inputs)
    case_req = group_case_requirements(rows)
    candidates = list_tutorial_candidates(Path(args.tutorials_root))
    client = maybe_bedrock_client(args.use_bedrock, args.region)

    mapping = []
    for case_name, req in sorted(case_req.items()):
        if stable_bucket(case_name, args.chunk_count) != args.chunk_index:
            continue

        matched_path = None
        method = None
        confidence = None
        reason = ''

        hmatch, hmethod = heuristic_match(case_name, candidates)
        if hmatch is not None:
            matched_path = hmatch
            method = hmethod
            confidence = 0.95
            reason = 'heuristic match'
        elif client is not None:
            try:
                lmatch, conf, rsn, k = llm_match_case(client, args.model_id, case_name, req, candidates, top_k=args.top_k)
                if lmatch is not None:
                    matched_path = lmatch
                    method = f'bedrock_sonnet_top{min(args.top_k, k)}'
                    confidence = conf
                    reason = rsn
            except Exception as e:
                reason = f'llm_error: {e}'

        mapping.append({
            'case_name': case_name,
            'tutorial_path': str(matched_path) if matched_path else None,
            'matched': bool(matched_path),
            'method': method,
            'confidence': confidence,
            'reason': reason,
            'model_provider': 'bedrock' if client else None,
            'model_version': args.model_id if client else None,
            'chunk_index': args.chunk_index,
            'chunk_count': args.chunk_count,
        })

    out = Path(args.out)
    out.write_text(json.dumps(mapping, indent=2), encoding='utf-8')
    matched = sum(1 for x in mapping if x['matched'])
    print(f"cases_in_chunk={len(mapping)} matched={matched} unmatched={len(mapping)-matched}")
    print(out)


if __name__ == '__main__':
    main()
