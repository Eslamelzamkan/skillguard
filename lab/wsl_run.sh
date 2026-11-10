#!/usr/bin/env bash
# Reproducible entry point for local lift measurement on Windows-via-WSL.
#
# Why this exists: `bench eval run` cannot run on native Windows (a sandbox
# path-lockdown normalizes "/oracle" -> "\oracle" and aborts). It must run under
# WSL/Linux, from a NATIVE WSL working directory (a /mnt/c cwd makes BenchFlow's
# LiteLLM provider proxy fail with "failed to make path absolute"). This script
# encodes the working setup so the exact command is one artifact, not tribal
# knowledge. See lab/README.md for the full rationale.
#
# Run from inside WSL:  bash lab/wsl_run.sh <tasks-dir> [measure_lift args...]
# Example:
#   bash lab/wsl_run.sh /mnt/c/.../skillsbench/tasks \
#       score --skills-dir /mnt/c/.../lab/frozen_library --split-name holdout
set -euo pipefail

REPO_WIN="$(cd "$(dirname "$0")/.." && pwd)"          # this repo, as a /mnt/c path
TASKS_DIR="${1:?usage: wsl_run.sh <tasks-dir> [measure_lift args...]}"; shift

export PATH="$HOME/.local/bin:$PATH"                   # uv-installed bench
# Groq key: prefer the environment, else read it out of the repo's .env
: "${GROQ_API_KEY:=$(grep -oE 'gsk_[A-Za-z0-9]+' "$REPO_WIN/.env" 2>/dev/null | head -1 || true)}"
export GROQ_API_KEY

# Run from a native-WSL cwd so the provider proxy's path resolution works.
JOBS_NATIVE="$HOME/sf-jobs"
mkdir -p "$JOBS_NATIVE"
cd "$JOBS_NATIVE"

# measure_lift.py is stdlib-only -> runs on WSL system python3, no install.
exec python3 "$REPO_WIN/lab/measure_lift.py" \
    --tasks-dir "$TASKS_DIR" \
    --jobs-dir "$JOBS_NATIVE/out" \
    --groq-key "$GROQ_API_KEY" \
    "$@"
