#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# Claude Code Context Management Benchmark
# ============================================================
# Run this from a normal terminal (NOT inside Claude Code).
#
# Usage:
#   ./run-benchmark.sh              # 5 reps, all strategies
#   ./run-benchmark.sh --reps 3     # 3 reps
#   ./run-benchmark.sh --reps 1 --strategies control,plain_compact  # quick test
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BENCHMARK_DIR="$SCRIPT_DIR/benchmark"
RUNNER_DIR="$BENCHMARK_DIR/runner"
RESULTS_DIR="$SCRIPT_DIR/results"
GRAPHS_DIR="$SCRIPT_DIR/graphs"

# Pass through all args to the runner
ARGS="$@"

echo "=== Claude Code Context Management Benchmark ==="
echo ""
echo "This will:"
echo "  1. Install dependencies"
echo "  2. Run the benchmark (4 strategies × N reps)"
echo "  3. Analyze results and generate graphs"
echo "  4. Generate ARTICLE.md and REPORT.md"
echo ""

# Check prerequisites
command -v node >/dev/null 2>&1 || { echo "Error: node not found. Install Node.js first."; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo "Error: python3 not found."; exit 1; }
command -v claude >/dev/null 2>&1 || { echo "Error: claude CLI not found. Install Claude Code first."; exit 1; }

# Check we're NOT inside Claude Code
if [ -n "${CLAUDECODE:-}" ]; then
    echo "Error: This script must be run from a normal terminal, NOT inside Claude Code."
    echo "Exit your current Claude Code session first, then run this script."
    exit 1
fi

echo "Node: $(node --version)"
echo "Python: $(python3 --version)"
echo "Claude: $(claude --version)"
echo ""

# --- Step 1: Install dependencies ---
echo "=== Step 1: Installing dependencies ==="

# Node deps for benchmark runner
cd "$RUNNER_DIR"
if [ ! -d "node_modules" ]; then
    echo "Installing Node.js dependencies..."
    npm install
else
    echo "Node dependencies already installed."
fi

# Python deps for analysis
echo "Checking Python dependencies..."
python3 -c "import matplotlib, pandas, numpy" 2>/dev/null || {
    echo "Installing Python analysis dependencies..."
    pip3 install matplotlib pandas numpy
}

# Python deps for seed project tests
python3 -c "import fastapi, pydantic, httpx" 2>/dev/null || {
    echo "Installing Python project dependencies..."
    pip3 install fastapi pydantic httpx pytest pytest-asyncio uvicorn ruff
}

echo ""

# --- Step 2: Run benchmark ---
echo "=== Step 2: Running benchmark ==="
echo "Args: ${ARGS:-default (5 reps, all strategies)}"
echo ""

cd "$RUNNER_DIR"
node --experimental-strip-types src/main.ts $ARGS

echo ""

# --- Step 3: Analyze results ---
echo "=== Step 3: Analyzing results and generating graphs ==="

cd "$BENCHMARK_DIR"
python3 analyze.py "$RESULTS_DIR"

echo ""

# --- Step 4: Generate article ---
echo "=== Step 4: Generating ARTICLE.md and REPORT.md ==="

python3 generate_article.py "$RESULTS_DIR"

echo ""
echo "=== Complete ==="
echo ""
echo "Deliverables:"
echo "  ARTICLE.md          — The publishable blog post"
echo "  REPORT.md           — Detailed technical report"
echo "  graphs/*.png        — Publication-quality graphs"
echo "  graphs/*.svg        — Vector graphs"
echo "  results/summary.csv — Summary data"
echo "  results/summary.json— Summary data (JSON)"
echo "  results/raw/        — Per-run raw results"
echo ""
echo "To view the article:"
echo "  cat ARTICLE.md"
echo ""
