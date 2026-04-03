import argparse
import json
import os
import re
import shutil
import subprocess
import hashlib
from pathlib import Path
from datetime import datetime

PROMPT_SUFFIX = (
    "Generate the target OpenFOAM file so it is complete, functional, and logically consistent with the requirement. "
    "Use technically sound parameter choices and maintain internal consistency across physical models, dimensions, and numerics."
)


def append_jsonl(path: Path, obj: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())



def stable_bucket(key: str, chunk_count: int):
    h = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return int(h[:12], 16) % chunk_count

def load_prompt_groups_from_matched(matched_root: Path):
    groups = []
    for d in sorted([p for p in matched_root.iterdir() if p.is_dir() and p.name.isdigit()]):
        up_file = d / "user_prompt.txt"
        meta_file = d / "meta.json"
        if not up_file.exists() or not meta_file.exists():
            continue
        up = up_file.read_text(encoding="utf-8", errors="ignore").strip()
        meta = json.loads(meta_file.read_text(encoding="utf-8"))
        if up and (d / "0" / "U").exists() and (d / "system").exists() and (d / "constant").exists():
            groups.append((d.name, up, meta, d))
    return groups


def extract_requirement(user_prompt: str, meta: dict):
    req = (meta.get("user_requirement") or "").strip()
    if req:
        return req
    m = re.search(r"User requirement:\s*(.*)", user_prompt, flags=re.IGNORECASE | re.DOTALL)
    if m:
        txt = m.group(1)
        txt = txt.split("Generate the target OpenFOAM file", 1)[0].strip()
        return txt
    return ""


def scale_uniform_vectors(text: str, factor: float):
    pat = re.compile(r"uniform\s*\(\s*([+-]?\d*\.?\d+(?:[eE][+-]?\d+)?)\s+([+-]?\d*\.?\d+(?:[eE][+-]?\d+)?)\s+([+-]?\d*\.?\d+(?:[eE][+-]?\d+)?)\s*\)")

    def repl(m):
        x = float(m.group(1)) * factor
        y = float(m.group(2)) * factor
        z = float(m.group(3)) * factor
        return f"uniform ({x:.6g} {y:.6g} {z:.6g})"

    return pat.sub(repl, text)


def patch_u_file(case_dir: Path, factor: float):
    u = case_dir / "0" / "U"
    if not u.exists():
        return False
    old = u.read_text(encoding="utf-8", errors="ignore")
    new = scale_uniform_vectors(old, factor)
    if new == old:
        return False
    u.write_text(new, encoding="utf-8")
    return True


def run_foam_agent(foam_agent_dir: Path, prompt_path: Path, output_dir: Path, reuse_dir: Path, timeout_sec: int):
    # ALWAYS reuse provided files to skip initial generation
    cmd = [
        "python", str(foam_agent_dir / "foambench_main.py"),
        "--output", str(output_dir),
        "--prompt_path", str(prompt_path),
        "--reuse_generated_dir", str(reuse_dir),
    ]
    try:
        proc = subprocess.run(cmd, cwd=str(foam_agent_dir.parent), capture_output=True, text=True, timeout=timeout_sec)
        return proc.returncode, (proc.stdout or "")[-6000:], (proc.stderr or "")[-6000:]
    except subprocess.TimeoutExpired:
        return 124, "", f"TimeoutExpired after {timeout_sec}s"


def find_case_root(run_out: Path):
    if not run_out.exists():
        return run_out
    if (run_out / "0").exists() and (run_out / "system").exists() and (run_out / "constant").exists():
        return run_out
    for d in run_out.iterdir():
        if d.is_dir() and (d / "0").exists() and (d / "system").exists() and (d / "constant").exists():
            return d
    return run_out


def has_positive_time(run_case_root: Path):
    if not run_case_root.exists():
        return False
    for p in run_case_root.iterdir():
        if p.is_dir() and p.name != "0":
            try:
                if float(p.name) > 0:
                    return True
            except Exception:
                pass
    return False



def build_system_prompt_for_file(base_system_prompt: str, file_name: str, folder_name: str) -> str:
    sp = base_system_prompt or ""
    # Replace existing tags if present
    sp = re.sub(r"<file_name>.*?</file_name>", f"<file_name>{file_name}</file_name>", sp, flags=re.DOTALL)
    sp = re.sub(r"<folder_name>.*?</folder_name>", f"<folder_name>{folder_name}</folder_name>", sp, flags=re.DOTALL)

    # If tags not present, append lightweight context
    if "<file_name>" not in sp:
        sp += f" <file_name>{file_name}</file_name>"
    if "<folder_name>" not in sp:
        sp += f" <folder_name>{folder_name}</folder_name>"
    return sp

def export_files_to_rows(case_root: Path, user_requirement: str, user_prompt: str, meta: dict, variant_id: str, factor: float):
    rows = []
    for top in ["0", "system", "constant"]:
        d = case_root / top
        if not d.exists() or not d.is_dir():
            continue
        for fp in d.iterdir():
            if not fp.is_file():
                continue
            content = fp.read_text(encoding="utf-8", errors="ignore")
            row = {
                "case_name": meta.get("case_name"),
                "folder_name": top,
                "file_name": fp.name,
                "file_content": content,
                "system_prompt": build_system_prompt_for_file(meta.get("system_prompt", ""), fp.name, top),
                "user_requirement": user_requirement,
                "user_prompt": user_prompt,
                "variant_id": variant_id,
                "velocity_scale_factor": factor,
                "source_prompt_id": meta.get("id") or meta.get("prompt_id"),
            }
            rows.append(row)
    return rows


def main():
    ap = argparse.ArgumentParser(description="Velocity branching using matched_hf_raw as input-writer output (always reuse mode)")
    ap.add_argument("--matched-root", required=True, help="Path to matched_hf_raw or matched_complete")
    ap.add_argument("--foam-agent-dir", required=True)
    ap.add_argument("--work-dir", default="work")
    ap.add_argument("--out-jsonl", default="output/accepted_velocity.jsonl")
    ap.add_argument("--fail-jsonl", default="output/failed_velocity.jsonl")
    ap.add_argument("--timeout-sec", type=int, default=2600)
    ap.add_argument("--chunk-index", type=int, default=0)
    ap.add_argument("--chunk-count", type=int, default=1)
    args = ap.parse_args()

    matched_root = Path(args.matched_root)
    foam_agent_dir = Path(args.foam_agent_dir)
    work = Path(args.work_dir)
    out_ok = Path(args.out_jsonl)
    out_fail = Path(args.fail_jsonl)

    groups = load_prompt_groups_from_matched(matched_root)

    for pid, user_prompt, meta, src_case_dir in groups:
        if stable_bucket(pid, args.chunk_count) != args.chunk_index:
            continue
        base_req = extract_requirement(user_prompt, meta)
        if not base_req:
            append_jsonl(out_fail, {"time": datetime.utcnow().isoformat(), "prompt_id": pid, "reason": "missing_requirement"})
            continue

        for pct in [10, 20, 30]:
            factor = 1.0 + pct / 100.0
            variant_id = f"{pid}__vel_plus_{pct}pct"
            reuse_dir = work / variant_id / "reuse_generated"
            run_out = work / variant_id / "run"
            prompt_path = work / variant_id / "user_requirement.txt"

            if reuse_dir.exists():
                shutil.rmtree(reuse_dir)
            shutil.copytree(src_case_dir, reuse_dir)

            if not patch_u_file(reuse_dir, factor):
                append_jsonl(out_fail, {"time": datetime.utcnow().isoformat(), "prompt_id": pid, "variant_id": variant_id, "reason": "cannot_patch_U"})
                continue

            new_req = f"{base_req} Velocity increased by {pct}% from baseline."
            new_prompt = f"user_requirement: {new_req}\n {PROMPT_SUFFIX}"
            prompt_path.parent.mkdir(parents=True, exist_ok=True)
            prompt_path.write_text(new_req, encoding="utf-8")

            rc, so, se = run_foam_agent(foam_agent_dir, prompt_path, run_out, reuse_dir, args.timeout_sec)
            case_root = find_case_root(run_out)
            ok = (rc == 0 and has_positive_time(case_root))

            if ok:
                # immediate append per generated file (no end-of-run wait)
                for row in export_files_to_rows(case_root, new_req, new_prompt, meta, variant_id, factor):
                    append_jsonl(out_ok, row)
            else:
                append_jsonl(out_fail, {
                    "time": datetime.utcnow().isoformat(),
                    "prompt_id": pid,
                    "variant_id": variant_id,
                    "return_code": rc,
                    "reason": "run_failed_or_no_positive_time",
                    "stdout_tail": so,
                    "stderr_tail": se,
                })


if __name__ == "__main__":
    main()




