#!/usr/bin/env python3
"""Paired-lift measurement over the real BenchFlow harness.

This does NOT reimplement scoring - it shells out to `bench eval run` (the same
CLI that scores the competition) so local numbers are apples-to-apples with the
private-mix scoring, not an approximation. It parses each rollout's result.json
(`rewards.reward` is the terminal scalar) and computes the competition's own
lift metric: g = (pass_skill - pass_vanilla) / (1 - pass_vanilla), plus raw pp.

Two phases, mirroring how Track 2 actually scores:
  evolve  - run self-gen across dev-calibration; harvest each task's exported
            generated skills into one accumulating frozen library dir.
  score   - paired lift of a FROZEN skills dir (with-skill) vs no-skill on a
            split. This is the number that goes in the writeup.

Model routing (Groq free tier, OpenAI-compatible -> the `vllm` provider, no code
change needed):  --model vllm/<groq-model>
  and env: BENCHFLOW_PROVIDER_BASE_URL=https://api.groq.com/openai/v1
           OPENAI_API_KEY=<groq key>   (passed through via --agent-env)
Agent: deepagents (LangChain ACP shim; resolves the OpenAI-compatible provider).

Requires Docker running (bench sandbox) + a Groq key. Use --dry-run to print the
exact commands without executing (and without spending budget).
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SKILL_CREATOR = REPO / "skills" / "skill-creator"
GROQ_BASE_URL = "https://api.groq.com/openai/v1"


def load_split(split_path):
    return json.loads(Path(split_path).read_text(encoding="utf-8"))


def base_cmd(task_dir, jobs_dir, agent, model, groq_key):
    """The shared prefix for a single-task `bench eval run`, Groq-routed."""
    cmd = [
        "bench", "eval", "run",
        "--tasks-dir", str(task_dir),
        "--agent", agent,
        "--model", model,
        "--sandbox", "docker",
        "--jobs-dir", str(jobs_dir),
        "--concurrency", "1",
    ]
    if model.startswith("vllm/"):
        cmd += [
            "--agent-env", f"BENCHFLOW_PROVIDER_BASE_URL={GROQ_BASE_URL}",
            "--agent-env", f"OPENAI_API_KEY={groq_key}",
        ]
    return cmd


def run(cmd, dry_run):
    printable = " ".join(f'"{c}"' if " " in c else c for c in cmd)
    if dry_run:
        print("  DRY:", printable)
        return None
    env = {**os.environ, "PYTHONUTF8": "1"}  # bench has a cp1252 read bug on Windows
    return subprocess.run(cmd, env=env, capture_output=True, text=True)


def rollout_reward(jobs_dir):
    """Find the newest result.json under jobs_dir and return (reward, invoked, error)."""
    results = sorted(Path(jobs_dir).rglob("result.json"), key=lambda p: p.stat().st_mtime)
    if not results:
        return None, 0, "no result.json"
    data = json.loads(results[-1].read_text(encoding="utf-8"))
    reward = (data.get("rewards") or {}).get("reward")
    return reward, data.get("n_skill_invocations", 0), data.get("error")


def passed(reward, threshold):
    return reward is not None and reward >= threshold


def normalized_lift(pass_vanilla, pass_skill):
    """g = (pass_skill - pass_vanilla) / (1 - pass_vanilla); competition's metric."""
    denom = 1.0 - pass_vanilla
    if denom <= 1e-9:
        return 0.0  # vanilla already solves it every time - no headroom
    return (pass_skill - pass_vanilla) / denom


def cmd_score(args):
    split = load_split(args.split)
    tasks = split[args.split_name]
    if args.limit:
        tasks = tasks[: args.limit]
    tasks_root = Path(args.tasks_dir)
    jobs_root = Path(args.jobs_dir)

    per_task = []
    for task in tasks:
        task_dir = tasks_root / task
        v_pass = s_pass = 0
        for trial in range(args.trials):
            for mode, extra in (
                ("no-skill", ["--skill-mode", "no-skill"]),
                ("with-skill", ["--skill-mode", "with-skill", "--skills-dir", str(Path(args.skills_dir).resolve())]),
            ):
                jobs = jobs_root / task / mode / f"t{trial}"
                cmd = base_cmd(task_dir, jobs, args.agent, args.model, args.groq_key) + extra
                run(cmd, args.dry_run)
                if args.dry_run:
                    continue
                reward, _, _ = rollout_reward(jobs)
                if mode == "no-skill" and passed(reward, args.pass_threshold):
                    v_pass += 1
                elif mode == "with-skill" and passed(reward, args.pass_threshold):
                    s_pass += 1
        if args.dry_run:
            continue
        pv, ps = v_pass / args.trials, s_pass / args.trials
        per_task.append({"task": task, "pass_vanilla": pv, "pass_skill": ps,
                          "pp_delta": ps - pv, "lift_g": normalized_lift(pv, ps)})

    if args.dry_run:
        print(f"\n(dry-run) would score {len(tasks)} tasks x {args.trials} trials x 2 modes"
              f" = {len(tasks) * args.trials * 2} bench runs")
        return

    n = len(per_task) or 1
    summary = {
        "split": args.split_name, "n_tasks": len(per_task), "trials": args.trials,
        "mean_pp_delta": sum(t["pp_delta"] for t in per_task) / n,
        "mean_lift_g": sum(t["lift_g"] for t in per_task) / n,
        "per_task": per_task,
    }
    out = jobs_root / f"lift_{args.split_name}.json"
    out.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k != "per_task"}, indent=2))
    print(f"\nfull per-task report -> {out}")


def cmd_evolve(args):
    """Run self-gen across the calibration split; harvest exported skills into a
    frozen library. ponytail: harvests BenchFlow's own per-task exported-skills
    output rather than re-implementing accumulation. Cross-task carry-forward
    (does task N see task N-1's skills at author time?) depends on the Track 2
    wrapper mechanics we've flagged as the open Discord question - until that's
    confirmed, this accumulates POST-hoc (union of all tasks' exports, newest
    wins), which is the faithful floor: it proves the library the loop produces,
    not a specific in-loop feedback shape."""
    split = load_split(args.split)
    tasks = split["calibration"]
    if args.limit:
        tasks = tasks[: args.limit]
    frozen = Path(args.out_skills)
    frozen.mkdir(parents=True, exist_ok=True)
    tasks_root = Path(args.tasks_dir)
    jobs_root = Path(args.jobs_dir)

    for task in tasks:
        jobs = jobs_root / "evolve" / task
        cmd = base_cmd(tasks_root / task, jobs, args.agent, args.model, args.groq_key) + [
            "--skill-mode", "self-gen",
            "--skill-creator-dir", str(SKILL_CREATOR),
        ]
        run(cmd, args.dry_run)
        if args.dry_run:
            continue
        # harvest: capture_skills writes generated packs under the rollout dir;
        # find any exported SKILL.md one level deep and copy the pack into frozen/
        import shutil
        for skill_md in Path(jobs).rglob("generated*/*/SKILL.md"):
            pack = skill_md.parent
            dest = frozen / pack.name
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(pack, dest)

    if args.dry_run:
        print(f"\n(dry-run) would self-gen across {len(tasks)} calibration tasks -> {frozen}")
        return
    packs = sorted(p.name for p in frozen.iterdir() if p.is_dir())
    print(json.dumps({"frozen_library": str(frozen), "n_skills": len(packs), "skills": packs}, indent=2))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default=str(Path(__file__).parent / "split.json"))
    ap.add_argument("--tasks-dir", required=True, help="skillsbench/tasks root")
    ap.add_argument("--jobs-dir", default="jobs")
    ap.add_argument("--agent", default="deepagents")
    ap.add_argument("--model", default="vllm/llama-3.3-70b-versatile")
    ap.add_argument("--groq-key", default=os.environ.get("GROQ_API_KEY", ""))
    ap.add_argument("--trials", type=int, default=3)
    ap.add_argument("--pass-threshold", type=float, default=1.0,
                    help="reward >= this counts as a pass (SkillsBench is binary 0/1)")
    ap.add_argument("--limit", type=int, default=0, help="cap tasks (budget control)")
    ap.add_argument("--dry-run", action="store_true")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("score", help="paired lift of a frozen skills dir vs no-skill")
    p.add_argument("--skills-dir", required=True)
    p.add_argument("--split-name", default="holdout", choices=["calibration", "holdout"])
    p.set_defaults(func=cmd_score)

    p = sub.add_parser("evolve", help="self-gen across calibration, harvest frozen library")
    p.add_argument("--out-skills", required=True)
    p.set_defaults(func=cmd_evolve)

    args = ap.parse_args()
    if not args.dry_run and not args.groq_key and args.model.startswith("vllm/"):
        print("error: set --groq-key or GROQ_API_KEY (or use --dry-run)", file=sys.stderr)
        sys.exit(1)
    args.func(args)


if __name__ == "__main__":
    main()
