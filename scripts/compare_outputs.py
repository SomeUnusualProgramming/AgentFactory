#!/usr/bin/env python3
"""
Compare Pre- and Post-Improvement Outputs
Analyzes quality metrics improvements between different generation runs
"""

import json
import os
from pathlib import Path
from collections import defaultdict


def extract_metrics_from_blackboard(blackboard_path: str) -> dict:
    """
    Extracts quality metrics from a blackboard.json file
    """
    try:
        with open(blackboard_path, 'r', encoding='utf-8') as f:
            bb = json.load(f)
        
        metrics = {
            "project_name": bb.get("project_info", {}).get("idea", "Unknown"),
            "status": bb.get("project_info", {}).get("status", "Unknown"),
            "modules_count": len(bb.get("architecture", {}).get("modules", [])),
            "files_created": len(bb.get("files_created", [])),
            "code_quality_metrics": bb.get("code_quality_metrics", {}),
            "agent_reasoning_count": len(bb.get("agent_reasoning", [])),
            "agent_attempts_count": len(bb.get("agent_attempts", [])),
        }
        
        return metrics
    except Exception as e:
        return {"error": str(e)}


def calculate_quality_score(metrics: dict) -> float:
    """
    Calculates overall quality score from metrics
    """
    if "code_quality_metrics" not in metrics:
        return 0
    
    code_metrics = metrics["code_quality_metrics"]
    if not code_metrics:
        return 0
    
    scores = [m.get("reviewer_score", 0) for m in code_metrics.values()]
    return sum(scores) / len(scores) if scores else 0


def compare_projects(baseline_dir: str, improved_dir: str):
    """
    Compares two project outputs
    """
    print("=" * 70)
    print("CODE GENERATION QUALITY COMPARISON")
    print("=" * 70)
    
    baseline_bb = None
    improved_bb = None
    
    for bb_file in Path(baseline_dir).glob('*/blackboard.json'):
        baseline_bb = extract_metrics_from_blackboard(str(bb_file))
        baseline_name = bb_file.parent.name
        break
    
    for bb_file in Path(improved_dir).glob('*/blackboard.json'):
        improved_bb = extract_metrics_from_blackboard(str(bb_file))
        improved_name = bb_file.parent.name
        break
    
    if not baseline_bb or not improved_bb:
        print("❌ Could not find blackboard files in one or both directories")
        return
    
    print(f"\n📊 BASELINE: {baseline_name}")
    print(f"   Project: {baseline_bb.get('project_name')}")
    print(f"   Status: {baseline_bb.get('status')}")
    print(f"   Modules: {baseline_bb.get('modules_count')}")
    print(f"   Files: {baseline_bb.get('files_created')}")
    
    baseline_score = calculate_quality_score(baseline_bb)
    print(f"   Avg Quality Score: {baseline_score:.1f}/100")
    print(f"   Agent Reasoning Logs: {baseline_bb.get('agent_reasoning_count')}")
    print(f"   Agent Attempts: {baseline_bb.get('agent_attempts_count')}")
    
    print(f"\n📊 IMPROVED: {improved_name}")
    print(f"   Project: {improved_bb.get('project_name')}")
    print(f"   Status: {improved_bb.get('status')}")
    print(f"   Modules: {improved_bb.get('modules_count')}")
    print(f"   Files: {improved_bb.get('files_created')}")
    
    improved_score = calculate_quality_score(improved_bb)
    print(f"   Avg Quality Score: {improved_score:.1f}/100")
    print(f"   Agent Reasoning Logs: {improved_bb.get('agent_reasoning_count')}")
    print(f"   Agent Attempts: {improved_bb.get('agent_attempts_count')}")
    
    print(f"\n📈 IMPROVEMENTS")
    quality_improvement = improved_score - baseline_score
    print(f"   Quality Score Change: {quality_improvement:+.1f} points ({quality_improvement/baseline_score*100:+.1f}%)")
    
    baseline_metrics = baseline_bb.get("code_quality_metrics", {})
    improved_metrics = improved_bb.get("code_quality_metrics", {})
    
    if baseline_metrics and improved_metrics:
        baseline_issues = sum(m.get("issues_found", 0) for m in baseline_metrics.values())
        improved_issues = sum(m.get("issues_found", 0) for m in improved_metrics.values())
        print(f"   Total Issues Found: {improved_issues} (was {baseline_issues}, {improved_issues - baseline_issues:+d})")
        
        baseline_optimizations = sum(m.get("optimizations_applied", 0) for m in baseline_metrics.values())
        improved_optimizations = sum(m.get("optimizations_applied", 0) for m in improved_metrics.values())
        print(f"   Total Optimizations Applied: {improved_optimizations} (was {baseline_optimizations}, {improved_optimizations - baseline_optimizations:+d})")
    
    reasoning_improvement = improved_bb.get('agent_reasoning_count') - baseline_bb.get('agent_reasoning_count')
    print(f"   Agent Reasoning Logs: {reasoning_improvement:+d} more (for better debugging)")
    
    print("\n" + "=" * 70)


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Compare project outputs')
    parser.add_argument('--baseline', type=str, required=True, help='Baseline output directory')
    parser.add_argument('--improved', type=str, required=True, help='Improved output directory')
    
    args = parser.parse_args()
    
    compare_projects(args.baseline, args.improved)


if __name__ == "__main__":
    main()
