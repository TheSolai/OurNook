#!/bin/bash
# Run all OurNook tests. Assumes the FastAPI server is already running on port 18765.
#   cd /Users/amre/.minimax/agents/mavis/workspace/nook && bash tests/run_all.sh
set -e
cd "$(dirname "$0")/.."
VENV=~/.nook-venv/bin/python3

echo "════════════════════════════════════════════════════════════"
echo "  OurNook test suite — io_flows + quality"
echo "════════════════════════════════════════════════════════════"
echo
echo "── io_flows.py (smoke + I/O) ──"
$VENV tests/test_io_flows.py
echo
echo "── test_quality.py (regressions + edge cases) ──"
$VENV tests/test_quality.py
echo
echo "════════════════════════════════════════════════════════════"
echo "  ✓ All test suites passed"
echo "════════════════════════════════════════════════════════════"
