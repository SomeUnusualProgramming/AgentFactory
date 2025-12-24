#!/usr/bin/env python3
"""
Integration Test for Agent Pipeline
Tests that all agents work together correctly
"""

import sys
import os
import json
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.factory_boss_blackboard import FactoryBlackboard
from agents.agent_architect import run_architect
from agents.agent_developer import run_developer
from agents.agent_code_reviewer import run_reviewer
from agents.agent_code_optimizer import run_optimizer


def test_blackboard():
    """Test blackboard initialization and logging"""
    print("\n🧪 TEST: Blackboard Creation & Logging")
    try:
        bb = FactoryBlackboard("Test App", "/tmp/test_bb")
        
        bb.log_agent_reasoning("architect", "TestModule", "Analyzing requirements", "Using Factory pattern")
        bb.log_agent_attempt("developer", "TestModule", 1, "spec", "code", "success")
        bb.log_quality_metrics("TestModule", 85, 2, 1)
        
        assert len(bb.state["agent_reasoning"]) > 0, "Reasoning log empty"
        assert len(bb.state["agent_attempts"]) > 0, "Attempts log empty"
        assert len(bb.state["code_quality_metrics"]) > 0, "Quality metrics empty"
        
        print("   ✓ Blackboard initialization")
        print("   ✓ Agent reasoning logging")
        print("   ✓ Agent attempt logging")
        print("   ✓ Quality metrics logging")
        return True
    except Exception as e:
        print(f"   ✗ FAILED: {e}")
        return False


def test_architect():
    """Test architect agent"""
    print("\n🧪 TEST: Architect Agent")
    try:
        module_data = {
            "name": "CalculatorModule",
            "responsibility": "Perform basic math calculations",
            "inputs": ["a", "b", "operation"],
            "outputs": ["result"]
        }
        
        spec = run_architect(module_data)
        
        assert spec, "Architect returned empty spec"
        assert len(spec) > 100, "Spec too short"
        
        print("   ✓ Architect specification generated")
        print(f"   ✓ Spec length: {len(spec)} chars")
        return True
    except Exception as e:
        print(f"   ✗ FAILED: {e}")
        return False


def test_developer():
    """Test developer agent"""
    print("\n🧪 TEST: Developer Agent")
    try:
        sample_spec = """
        MODULE: calculator
        FUNCTIONS:
          - add(a: float, b: float) -> float: Add two numbers
          - subtract(a: float, b: float) -> float: Subtract b from a
        
        DESIGN_PATTERN: Utility functions for arithmetic operations
        SAFETY: Validate inputs are numeric before processing
        """
        
        code = run_developer(sample_spec)
        
        assert code, "Developer returned empty code"
        assert len(code) > 100, "Code too short"
        assert "def " in code, "No functions defined"
        
        print("   ✓ Developer code generated")
        print(f"   ✓ Code length: {len(code)} chars")
        return True
    except Exception as e:
        print(f"   ✗ FAILED: {e}")
        return False


def test_reviewer():
    """Test code reviewer agent"""
    print("\n🧪 TEST: Code Reviewer Agent")
    try:
        sample_code = """
def add(a, b):
    return a + b

def subtract(a, b):
    x = a
    y = b
    z = x - y
    return z
"""
        
        review = run_reviewer(sample_code)
        
        assert review, "Reviewer returned empty report"
        assert "issues" in review, "No issues field in report"
        assert "quality_score" in review, "No quality_score in report"
        assert isinstance(review["quality_score"], (int, float)), "Invalid quality score type"
        
        print("   ✓ Code review completed")
        print(f"   ✓ Quality score: {review.get('quality_score')}/100")
        print(f"   ✓ Issues found: {len(review.get('issues', []))}")
        return True
    except Exception as e:
        print(f"   ✗ FAILED: {e}")
        return False


def test_optimizer():
    """Test code optimizer agent"""
    print("\n🧪 TEST: Code Optimizer Agent")
    try:
        sample_code = """
def calculate(a, b):
    x = a
    y = b
    z = x + y
    return z
"""
        
        sample_review = {
            "issues": [
                {
                    "type": "style",
                    "severity": "high",
                    "issue": "Unnecessary intermediate variables",
                    "suggestion": "Remove x, y, z and return directly"
                }
            ],
            "quality_score": 40
        }
        
        optimized = run_optimizer(sample_code, sample_review)
        
        assert optimized, "Optimizer returned empty code"
        assert len(optimized) > 0, "Optimized code is empty"
        
        print("   ✓ Code optimization completed")
        print(f"   ✓ Optimized code length: {len(optimized)} chars")
        return True
    except Exception as e:
        print(f"   ✗ FAILED: {e}")
        return False


def run_all_tests(verbose=False):
    """Run all integration tests"""
    print("=" * 70)
    print("AGENT FACTORY INTEGRATION TEST SUITE")
    print("=" * 70)
    
    tests = [
        ("Blackboard", test_blackboard),
        ("Architect", test_architect),
        ("Developer", test_developer),
        ("Reviewer", test_reviewer),
        ("Optimizer", test_optimizer),
    ]
    
    results = {}
    for test_name, test_func in tests:
        try:
            results[test_name] = test_func()
        except Exception as e:
            print(f"   ✗ Test setup failed: {e}")
            results[test_name] = False
    
    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for test_name, result in results.items():
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"  {status}: {test_name}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 All integration tests passed!")
        return 0
    else:
        print(f"\n⚠️ {total - passed} test(s) failed")
        return 1


def main():
    parser = argparse.ArgumentParser(description='Run integration tests')
    parser.add_argument('--verbose', action='store_true', help='Verbose output')
    
    args = parser.parse_args()
    
    sys.exit(run_all_tests(verbose=args.verbose))


if __name__ == "__main__":
    main()
