import argparse
import json
import os
import re
import shutil
import stat
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


def make_executable(path: Path):
    if not path.exists() or not path.is_file():
        return
    mode = path.stat().st_mode
    path.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def copy_optional_script(src_dir: Path, dst_case: Path, name: str):
    src = src_dir / name
    if src.exists() and src.is_file():
        dst = dst_case / name
        shutil.copy2(src, dst)
        make_executable(dst)
        return dst
    return None


def run_shell(cmd: str, cwd: Path, timeout_sec: int):
    try:
        p = subprocess.run(["bash", "-lc", cmd], cwd=str(cwd), capture_output=True, text=True, timeout=timeout_sec)
        return p.returncode, (p.stdout or "")[-6000:], (p.stderr or "")[-6000:]
    except subprocess.TimeoutExpired:
        return 124, "", f"TimeoutExpired after {timeout_sec}s while: {cmd}"


def has_positive_time(case_dir: Path):
    if not case_dir.exists():
        return False
    for p in case_dir.iterdir():
        if p.is_dir() and p.name != "0":
            try:
                if float(p.name) > 0:
                    return True
            except Exception:
                pass
    return False


def detect_application(case_dir: Path):
    cdict = case_dir / "system" / "controlDict"
    if not cdict.exists():
        return None
    txt = cdict.read_text(encoding="utf-8", errors="ignore")
    m = re.search(r"\bapplication\s+([A-Za-z0-9_\-]+)\s*;", txt)
    return m.group(1) if m else None


def run_case(case_dir: Path, tutorial_path: Path, timeout_sec: int):
    # Copy All* scripts from tutorial case if present
    allclean = copy_optional_script(tutorial_path, case_dir, "Allclean")
    allmesh = copy_optional_script(tutorial_path, case_dir, "Allmesh")
    allrun = copy_optional_script(tutorial_path, case_dir, "Allrun")

    logs = []

    # run in safe order
    if allclean:
        rc, so, se = run_shell("./Allclean", case_dir, timeout_sec)
        logs.append(("Allclean", rc, so, se))
        if rc not in (0,):
            return rc, logs

    if allmesh:
        rc, so, se = run_shell("./Allmesh", case_dir, timeout_sec)
        logs.append(("Allmesh", rc, so, se))
        if rc not in (0,):
            return rc, logs

    if allrun:
        rc, so, se = run_shell("./Allrun", case_dir, timeout_sec)
        logs.append(("Allrun", rc, so, se))
        return rc, logs

    # fallback if tutorial has no scripts
    rc, so, se = run_shell("blockMesh", case_dir, timeout_sec)
    logs.append(("blockMesh", rc, so, se))
    if rc not in (0,):
        return rc, logs

    app = detect_application(case_dir)
    if app:
        rc, so, se = run_shell(app, case_dir, timeout_sec)
        logs.append((app, rc, so, se))
        return rc, logs

    return 2, logs


def build_system_prompt_for_file(base_system_prompt: str, file_name: str, folder_name: str) -> str:
    sp = base_system_prompt or ""
    sp = re.sub(r"<file_name>.*?</file_name>", f"<file_name>{file_name}</file_name>", sp, flags=re.DOTALL)
    sp = re.sub(r"<folder_name>.*?</folder_name>", f"<folder_name>{folder_name}</folder_name>", sp, flags=re.DOTALL)
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
            rows.append({
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
                "tutorial_path": meta.get("tutorial_path"),
            })
    return rows


def main():
    ap = argparse.ArgumentParser(description="Velocity branching: reuse matched files + tutorial Allrun/Allmesh/Allclean")
    ap.add_argument("--matched-root", required=True)
    ap.add_argument("--work-dir", default="work")
    ap.add_argument("--out-jsonl", default="output/accepted_velocity.jsonl")
    ap.add_argument("--fail-jsonl", default="output/failed_velocity.jsonl")
    ap.add_argument("--timeout-sec", type=int, default=2600)
    ap.add_argument("--chunk-index", type=int, default=0)
    ap.add_argument("--chunk-count", type=int, default=1)
    args = ap.parse_args()

    matched_root = Path(args.matched_root)
    work = Path(args.work_dir)
    out_ok = Path(args.out_jsonl)
    out_fail = Path(args.fail_jsonl)

    groups = load_prompt_groups_from_matched(matched_root)

    for pid, user_prompt, meta, src_case_dir in groups:
        if stable_bucket(pid, args.chunk_count) != args.chunk_index:
            continue

        tutorial_path = Path(meta.get("tutorial_path") or "")
        if not tutorial_path.exists():
            append_jsonl(out_fail, {"time": datetime.utcnow().isoformat(), "prompt_id": pid, "reason": "missing_tutorial_path"})
            continue

        base_req = extract_requirement(user_prompt, meta)
        if not base_req:
            append_jsonl(out_fail, {"time": datetime.utcnow().isoformat(), "prompt_id": pid, "reason": "missing_requirement"})
            continue

        for pct in [10, 20, 30]:
            factor = 1.0 + pct / 100.0
            variant_id = f"{pid}__vel_plus_{pct}pct"
            case_dir = work / variant_id / "case"

            if case_dir.exists():
                shutil.rmtree(case_dir)
            shutil.copytree(src_case_dir, case_dir)

            if not patch_u_file(case_dir, factor):
                append_jsonl(out_fail, {"time": datetime.utcnow().isoformat(), "prompt_id": pid, "variant_id": variant_id, "reason": "cannot_patch_U"})
                continue

            new_req = f"{base_req} Velocity increased by {pct}% from baseline."
            new_prompt = f"user_requirement: {new_req}\n {PROMPT_SUFFIX}"

            rc, logs = run_case(case_dir, tutorial_path, args.timeout_sec)
            ok = (rc == 0 and has_positive_time(case_dir))

            if ok:
                for row in export_files_to_rows(case_dir, new_req, new_prompt, meta, variant_id, factor):
                    append_jsonl(out_ok, row)
            else:
                last = logs[-1] if logs else ("none", rc, "", "")
                append_jsonl(out_fail, {
                    "time": datetime.utcnow().isoformat(),
                    "prompt_id": pid,
                    "variant_id": variant_id,
                    "return_code": rc,
                    "reason": "run_failed_or_no_positive_time",
                    "last_step": last[0],
                    "stdout_tail": last[2],
                    "stderr_tail": last[3],
                })


if __name__ == "__main__":
    main()
