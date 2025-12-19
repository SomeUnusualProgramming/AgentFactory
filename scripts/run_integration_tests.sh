#!/bin/bash

echo "=========================================================================="
echo "AGENT FACTORY INTEGRATION TEST SUITE"
echo "=========================================================================="

cd "$(dirname "$0")/.."

echo ""
echo "Step 1: Generating sample artifacts..."
python scripts/generate_sample_artifacts.py --output /tmp/test_artifacts

echo ""
echo "Step 2: Running agent integration tests..."
python scripts/test_agent_integration.py --verbose

echo ""
echo "Step 3: Verifying code quality on sample code..."
python scripts/verify_code_quality.py --file /tmp/test_artifacts/sample_code.py --verbose

echo ""
echo "=========================================================================="
echo "INTEGRATION TEST COMPLETED"
echo "=========================================================================="
echo ""
echo "To run full pipeline test (requires Ollama):"
echo "  python factory_boss.py --idea 'Simple TODO app'"
echo ""
echo "To compare outputs:"
echo "  python scripts/compare_outputs.py --baseline output/project_old --improved output/project_new"
