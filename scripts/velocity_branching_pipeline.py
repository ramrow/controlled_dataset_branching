import argparse
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from datetime import datetime
from collections import defaultdict

PROMPT_SUFFIX = (
    "Generate the target OpenFOAM file so it is complete, functional, and logically consistent with the requirement. "
    "Use technically sound parameter choices and maintain internal consistency across physical models, dimensions, and numerics."
)


def load_jsonl(path: Path):
    rows = []
    with path.open("r", encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            if line.strip():
                rows.append(json.loads(line))
    return rows


def append_jsonl(path: Path, obj: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())


def group_by_prompt(rows):
    g = defaultdict(list)
    for r in rows:
        g[r.get("user_prompt", "")].append(r)
    return g


def relpath_from_row(row):
    folder = (row.get("folder_name") or "").replace("\\", "/").strip()
    name = (row.get("file_name") or "").replace("\\", "/").strip()
    if not folder or folder in {".", "./"}:
        return name
    return f"{folder}/{name}".strip("/")


def materialize_case_from_rows(rows, case_dir: Path):
    case_dir.mkdir(parents=True, exist_ok=True)
    for r in rows:
        rel = relpath_from_row(r)
        if not rel:
            continue
        top = rel.split("/", 1)[0]
        if top not in {"0", "system", "constant"}:
            continue
        out = case_dir / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(r.get("file_content", ""), encoding="utf-8")


def scale_uniform_vectors(text: str, factor: float):
    # scales all 'uniform (x y z)' entries in U file
    pat = re.compile(r"uniform\s*\(\s*([+-]?\d*\.?\d+(?:[eE][+-]?\d+)?)\s+([+-]?\d*\.?\d+(?:[eE][+-]?\d+)?)\s+([+-]?\d*\.?\d+(?:[eE][+-]?\d+)?)\s*\)")

    def repl(m):
        x = float(m.group(1)) * factor
        y = float(m.group(2)) * factor
        z = float(m.group(3)) * factor
        return f"uniform ({x:.6g} {y:.6g} {z:.6g})"

    return pat.sub(repl, text)


def apply_velocity_factor(case_dir: Path, factor: float):
    ufile = case_dir / "0" / "U"
    if not ufile.exists():
        return False
    txt = ufile.read_text(encoding="utf-8", errors="ignore")
    new_txt = scale_uniform_vectors(txt, factor)
    if new_txt == txt:
        return False
    ufile.write_text(new_txt, encoding="utf-8")
    return True


def run_foam_agent(foam_agent_dir: Path, prompt_path: Path, output_dir: Path, timeout_sec: int):
    cmd = [
        "python", str(foam_agent_dir / "foambench_main.py"),
        "--output", str(output_dir),
        "--prompt_path", str(prompt_path),
    ]
    try:
        proc = subprocess.run(cmd, cwd=str(foam_agent_dir.parent), capture_output=True, text=True, timeout=timeout_sec)
        return proc.returncode, (proc.stdout or "")[-4000:], (proc.stderr or "")[-4000:]
    except subprocess.TimeoutExpired as e:
        return 124, "", f"TimeoutExpired after {timeout_sec}s"


def has_success_signal(run_dir: Path):
    if not run_dir.exists():
        return False, "no output dir"
    # detect positive numeric time dir
    for p in run_dir.iterdir():
        if p.is_dir() and p.name != "0":
            try:
                if float(p.name) > 0:
                    return True, "ok"
            except Exception:
                pass
    return False, "no positive time dir"


def extract_requirement(row):
    req = row.get("user_requirement")
    if isinstance(req, str) and req.strip():
        return req.strip()
    return ""


def main():
    ap = argparse.ArgumentParser(description="Velocity-only branching augmentation with immediate save")
    ap.add_argument("--input", required=True, help="foamgpt_train.jsonl")
    ap.add_argument("--case-map", required=True, help="case_tutorial_map.json")
    ap.add_argument("--foam-agent-dir", required=True)
    ap.add_argument("--work-dir", default="work")
    ap.add_argument("--out-jsonl", default="output/accepted_velocity.jsonl")
    ap.add_argument("--fail-jsonl", default="output/failed_velocity.jsonl")
    ap.add_argument("--timeout-sec", type=int, default=2600)
    args = ap.parse_args()

    inp = Path(args.input)
    foam_agent_dir = Path(args.foam_agent_dir)
    work_dir = Path(args.work_dir)
    out_jsonl = Path(args.out_jsonl)
    fail_jsonl = Path(args.fail_jsonl)

    rows = load_jsonl(inp)
    groups = group_by_prompt(rows)
    case_map = {x["case_name"]: x for x in json.loads(Path(args.case_map).read_text(encoding="utf-8"))}

    for user_prompt, grp in groups.items():
        rep = grp[0]
        case_name = rep.get("case_name", "unknown_case")

        # must have matched tutorial case in map
        if not case_map.get(case_name, {}).get("matched"):
            append_jsonl(fail_jsonl, {
                "time": datetime.utcnow().isoformat(),
                "case_name": case_name,
                "reason": "no_tutorial_match",
            })
            continue

        base_req = extract_requirement(rep)
        if not base_req:
            append_jsonl(fail_jsonl, {
                "time": datetime.utcnow().isoformat(),
                "case_name": case_name,
                "reason": "missing_user_requirement",
            })
            continue

        # Build base files from dataset rows (0/system/constant), then modify 0/U
        for pct in [10, 20, 30]:
            factor = 1.0 + pct / 100.0
            variant_id = f"{case_name}__vel_plus_{pct}pct"
            case_dir = work_dir / variant_id / "seed_case"
            run_out = work_dir / variant_id / "run"
            prompt_path = work_dir / variant_id / "user_requirement.txt"

            if case_dir.exists():
                shutil.rmtree(case_dir)
            materialize_case_from_rows(grp, case_dir)

            changed = apply_velocity_factor(case_dir, factor)
            if not changed:
                append_jsonl(fail_jsonl, {
                    "time": datetime.utcnow().isoformat(),
                    "case_name": case_name,
                    "variant_id": variant_id,
                    "reason": "U_not_found_or_no_uniform_vector",
                })
                continue

            new_req = f"{base_req} Velocity increased by {pct}% from baseline."
            prompt_path.parent.mkdir(parents=True, exist_ok=True)
            prompt_path.write_text(new_req, encoding="utf-8")

            rc, so, se = run_foam_agent(foam_agent_dir, prompt_path, run_out, args.timeout_sec)
            ok, reason = has_success_signal(run_out)

            if rc == 0 and ok:
                # save successful rows immediately
                for r in grp:
                    rel = relpath_from_row(r)
                    top = rel.split("/", 1)[0] if rel else ""
                    if top not in {"0", "system", "constant"}:
                        continue
                    # keep original file content except patched U file
                    content = r.get("file_content", "")
                    if rel == "0/U":
                        content = (case_dir / "0" / "U").read_text(encoding="utf-8", errors="ignore")

                    out_row = dict(r)
                    out_row["user_requirement"] = new_req
                    out_row["user_prompt"] = f"user_requirement: {new_req}\n {PROMPT_SUFFIX}"
                    out_row["variant_id"] = variant_id
                    out_row["velocity_scale_factor"] = factor
                    out_row["tutorial_case_path"] = case_map.get(case_name, {}).get("tutorial_path")
                    out_row["file_content"] = content
                    append_jsonl(out_jsonl, out_row)
            else:
                append_jsonl(fail_jsonl, {
                    "time": datetime.utcnow().isoformat(),
                    "case_name": case_name,
                    "variant_id": variant_id,
                    "return_code": rc,
                    "reason": reason,
                    "stdout_tail": so,
                    "stderr_tail": se,
                })


if __name__ == "__main__":
    main()
