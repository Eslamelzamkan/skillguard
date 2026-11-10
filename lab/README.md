# Lab plane — local measurement harness

The lab is **not** part of the submission (`skills/` is). It exists so every
number in the writeup is reproducible on the real BenchFlow harness with a
free, equally-accessible model — never a hand-rolled approximation of scoring.

## What it does

- `make_split.py` — deterministic, stratified split of the public SkillsBench
  corpus into **dev-calibration** (62 tasks) and **dev-holdout** (25 tasks).
  We tune only on calibration; holdout stands in for the private bench-mix.
  Frozen output committed at [`split.json`](split.json).
- `measure_lift.py evolve` — run our `skill-creator` meta-skill in BenchFlow
  `self-gen` mode across the calibration split; harvest the exported generated
  skills into one frozen library.
- `measure_lift.py score` — paired lift of a frozen library (`with-skill`) vs
  `no-skill` on a split, computing the competition's own metric
  `g = (pass_skill − pass_vanilla) / (1 − pass_vanilla)` from each rollout's
  `result.json`.

## Setup

```bash
pip install benchflow                 # the real scoring CLI (bench)
# clone the public corpus:
git -c core.longpaths=true clone --depth 1 https://github.com/benchflow-ai/skillsbench
# Docker must be running (bench uses a Docker sandbox).
export GROQ_API_KEY=gsk_...            # free-tier Groq key
```

**Run on Linux (or WSL on Windows) — not native Windows.** `bench eval run`
calls a sandbox path-lockdown step (`_DEFAULT_LOCKED = ["/oracle", "/verifier",
…]`) that validates POSIX paths with `os.path.normpath`; on Windows that turns
`/oracle` into `\oracle` and every run aborts with
`ValueError: Invalid locked path '/oracle'` before the agent even starts
(benchflow 0.6.4). This is a harness bug on the Windows *host*, unrelated to the
submission — scoring happens on the organizers' Linux machines, so it never
affects the real result, only local rehearsal. Verified working path on Windows:
run `bench` inside **WSL** with Docker Desktop's WSL integration on:

```bash
# one-time, inside WSL (Ubuntu):
uv tool install --upgrade benchflow     # or pip, if pip is present
# then run bench with the tasks dir under /mnt/c/... ; the deterministic
# scripts in skills/ and the tests still run fine under native Windows Python.
```

**cp1252 note (native-Windows `bench` only, e.g. the SDK resolver checks):**
`bench` has a cp1252 file-read bug; direct native-Windows invocations need
`PYTHONUTF8=1`. Not needed under WSL/Linux. `measure_lift.py` sets it for its
subprocesses regardless.

**CRLF line endings (Windows clone of skillsbench).** If you `git clone`
skillsbench on Windows, git rewrites `*.sh` to CRLF; inside the Linux container
the shebang becomes `#!/bin/bash\r` and every verifier aborts with
`sh: /verifier/test.sh: not found` (rc=127). Fix once before running:

```bash
# clone with LF preserved:
git -c core.autocrlf=false -c core.longpaths=true clone --depth 1 \
    https://github.com/benchflow-ai/skillsbench
# or convert an existing clone in place:
find skillsbench/tasks -type f \( -name '*.sh' -o -name '*.py' \) \
    -exec sed -i 's/\r$//' {} +
```

Run `measure_lift.py` itself *inside WSL* (`python3 lab/measure_lift.py …`) so
its `bench` subprocesses are the WSL ones; the script is stdlib-only and runs on
WSL's system Python 3.10 without any install.

## Model routing — Groq via the OpenAI-compatible `vllm` provider (no code change)

Groq's API is OpenAI-compatible, so it routes through BenchFlow's built-in
`vllm` provider with a user-supplied base URL — nothing to patch:

```
--model vllm/llama-3.3-70b-versatile
--agent-env BENCHFLOW_PROVIDER_BASE_URL=https://api.groq.com/openai/v1
--agent-env OPENAI_API_KEY=$GROQ_API_KEY
```

Agent: `deepagents` (LangChain ACP shim — resolves the OpenAI-compatible
provider env). `measure_lift.py` wires all of this for you.

## Reproduce

```bash
# 0. regenerate the split (already committed; this just proves it's deterministic)
python lab/make_split.py --tasks-dir skillsbench/tasks

# 1. see exactly what would run, spend nothing:
python lab/measure_lift.py --tasks-dir skillsbench/tasks --dry-run \
    score --skills-dir skills --split-name holdout

# 2. evolve a frozen library on calibration (self-gen), then score it on holdout:
python lab/measure_lift.py --tasks-dir skillsbench/tasks --limit 10 \
    evolve --out-skills lab/frozen_library
python lab/measure_lift.py --tasks-dir skillsbench/tasks --trials 3 \
    score --skills-dir lab/frozen_library --split-name holdout
```

`--limit N` caps task count for budget control; `--trials N` sets repeats per
arm (the competition uses 15–20; use 3 locally, scale up for the final number).
Output: `jobs/lift_holdout.json` with per-task and aggregate `lift_g` + `pp`.

## What the local lab can and cannot run

Validated working locally (Windows + WSL + Docker Desktop):
- the whole deterministic backbone (`skills/` scripts, `tests/`) — native Windows;
- `bench eval run` provisioning, sandbox, and **verifier** — the `oracle` agent
  scores `offer-letter-generator` at reward **1.0**, so the sandbox + verifier
  path is confirmed end-to-end;
- self-gen scene setup — the creator/solver scenes provision and our
  `skill-creator` pack resolves and mounts.

**Blocked locally: the agent's model call, under Docker Desktop on WSL.**
BenchFlow routes all provider traffic through a host-side LiteLLM gateway that
binds the concrete Docker bridge-gateway IP (`172.17.0.1`) so the sandbox
container can reach it (`providers/litellm_runtime.py::_host_bind_address`).
Under Docker Desktop the daemon runs in its own VM, so a WSL-host process cannot
bind `172.17.0.1` → `[Errno 99] cannot assign requested address` → the run
aborts before any agent turn. `--usage-tracking off` does not bypass it. This is
a Docker-Desktop-on-WSL networking limitation, **not** a submission issue and
**not** present on native-Linux Docker or Daytona, where the bridge IP is
bindable from the host.

**So where do the real lift numbers come from?** Two organizer-run channels that
sidestep the local limitation entirely:
1. the **Kaggle public leaderboard** (2 submissions/day, scores on the public
   corpus on the organizers' infra) — the authoritative local-iteration signal;
2. **final private-mix scoring** at close.
To reproduce the agent loop *locally*, run on **native Linux Docker** (e.g. a
Linux box, a cloud VM, or `docker.io` + `dockerd` inside the WSL distro rather
than Docker Desktop integration) — then `python3 lab/measure_lift.py …` works as
documented above.

## Budget

Groq free tier ≈ 1,000 requests/day. A paired `score` run is
`n_tasks × trials × 2 modes` bench runs, each spending several agent requests.
Start with `--limit` small, watch the daily quota, scale toward freeze.
