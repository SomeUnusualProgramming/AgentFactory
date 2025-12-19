#!/usr/bin/env python3
"""
Code Quality Verification Script
Checks generated code for quality metrics and common issues
"""

import sys
import os
import ast
import argparse
from pathlib import Path


def analyze_code_quality(code: str) -> dict:
    """
    Analyzes Python code for quality metrics
    """
    metrics = {
        "lines_of_code": 0,
        "functions": 0,
        "classes": 0,
        "has_docstrings": False,
        "has_type_hints": False,
        "has_error_handling": False,
        "imports": [],
        "issues": []
    }
    
    try:
        tree = ast.parse(code)
        
        metrics["lines_of_code"] = len(code.split('\n'))
        metrics["has_error_handling"] = "try:" in code or "except" in code
        metrics["has_docstrings"] = '"""' in code or "'''" in code
        metrics["has_type_hints"] = "->" in code or ": " in code
        
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                metrics["functions"] += 1
            elif isinstance(node, ast.ClassDef):
                metrics["classes"] += 1
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    metrics["imports"].append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    metrics["imports"].append(node.module)
        
        if metrics["lines_of_code"] > 500 and not metrics["has_type_hints"]:
            metrics["issues"].append("Large file without type hints")
        
        if metrics["functions"] > 20 and not metrics["has_docstrings"]:
            metrics["issues"].append("Many functions without docstrings")
            
    except SyntaxError as e:
        metrics["issues"].append(f"Syntax error: {e}")
    
    return metrics


def check_code_file(filepath: str) -> dict:
    """
    Checks a Python file for quality
    """
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            code = f.read()
        
        return analyze_code_quality(code)
    except Exception as e:
        return {"error": str(e)}


def main():
    parser = argparse.ArgumentParser(description='Verify code quality')
    parser.add_argument('--code', type=str, help='Python code to analyze')
    parser.add_argument('--file', type=str, help='Python file to analyze')
    parser.add_argument('--dir', type=str, help='Directory to analyze')
    parser.add_argument('--verbose', action='store_true', help='Verbose output')
    
    args = parser.parse_args()
    
    if args.code:
        metrics = analyze_code_quality(args.code)
    elif args.file:
        metrics = check_code_file(args.file)
    elif args.dir:
        all_metrics = {}
        for py_file in Path(args.dir).glob('**/*.py'):
            all_metrics[str(py_file)] = check_code_file(str(py_file))
        metrics = all_metrics
    else:
        print("Please provide --code, --file, or --dir")
        sys.exit(1)
    
    if args.verbose:
        import json
        print(json.dumps(metrics, indent=2))
    else:
        if isinstance(metrics, dict) and "lines_of_code" in metrics:
            print(f"✓ LOC: {metrics['lines_of_code']}")
            print(f"  Functions: {metrics['functions']}, Classes: {metrics['classes']}")
            print(f"  Type hints: {'Yes' if metrics['has_type_hints'] else 'No'}")
            print(f"  Error handling: {'Yes' if metrics['has_error_handling'] else 'No'}")
            if metrics['issues']:
                print(f"  Issues: {', '.join(metrics['issues'])}")
        else:
            print(metrics)


if __name__ == "__main__":
    main()
