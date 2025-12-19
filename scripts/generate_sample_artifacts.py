#!/usr/bin/env python3
"""
Generate Sample Artifacts for Testing
Creates sample input artifacts needed for verification
"""

import json
import os
from pathlib import Path


def generate_sample_module_definition() -> dict:
    """Generate sample module definition for Architect testing"""
    return {
        "name": "PaymentProcessor",
        "responsibility": "Process and validate payment transactions securely",
        "inputs": {
            "transaction_id": "str",
            "amount": "float",
            "payment_method": "str",
            "user_id": "str"
        },
        "outputs": {
            "success": "bool",
            "transaction_receipt": "dict",
            "error_message": "str or None"
        }
    }


def generate_sample_technical_spec() -> str:
    """Generate sample technical specification for Developer testing"""
    return """
MODULE_NAME: payment_processor

DESIGN_PATTERN: Strategy (for different payment methods)

SOLID_PRINCIPLES_APPLIED:
  - Single Responsibility: Only handles payment processing
  - Dependency Inversion: Accepts PaymentProvider interface

INTERFACES:
  class PaymentProcessor:
    def process_payment(transaction_id: str, amount: float, method: str) -> dict
    def validate_amount(amount: float) -> bool
    def log_transaction(transaction_id: str, status: str) -> None

MOCK_INPUT:
  {
    "transaction_id": "TXN_123456",
    "amount": 99.99,
    "payment_method": "credit_card",
    "user_id": "USER_789"
  }

MOCK_OUTPUT:
  {
    "success": true,
    "transaction_receipt": {
      "id": "TXN_123456",
      "amount": 99.99,
      "timestamp": "2024-12-19T10:30:00Z",
      "status": "completed"
    },
    "error_message": null
  }

DEPENDENCIES: None (standard library only)

RATIONALE: Using Strategy pattern allows adding new payment methods (PayPal, Stripe, etc.)
without changing core processor logic. Follows SOLID principles for maintainability.
"""


def generate_sample_code() -> str:
    """Generate sample Python code for Reviewer testing"""
    return '''def process_transaction(transaction_id, amount, method):
    """Process a payment transaction"""
    x = transaction_id
    y = amount
    z = method
    
    if not x:
        return False
    if not y:
        return False
    if not z:
        return False
    
    try:
        # Process payment
        result = {
            "id": x,
            "amount": y,
            "method": z
        }
        return result
    except Exception as e:
        print(f"Error: {e}")
        return None


def validate_payment(transaction_id, amount):
    """Validate payment details"""
    if amount <= 0:
        return False
    if not transaction_id:
        return False
    return True


def log_transaction(transaction_id, status):
    """Log transaction to file"""
    with open("transactions.log", "a") as f:
        f.write(f"{transaction_id},{status}\\n")
    return True
'''


def generate_sample_review_report() -> dict:
    """Generate sample code review report"""
    return {
        "module_name": "payment_processor",
        "issues": [
            {
                "type": "style",
                "severity": "high",
                "location": "process_transaction",
                "issue": "Unnecessary intermediate variables (x, y, z)",
                "suggestion": "Remove x, y, z and use parameters directly"
            },
            {
                "type": "architecture",
                "severity": "medium",
                "location": "log_transaction",
                "issue": "Hardcoded filename 'transactions.log' reduces testability",
                "suggestion": "Accept log file path as parameter or use environment variable"
            },
            {
                "type": "best_practice",
                "severity": "high",
                "location": "process_transaction",
                "issue": "Bare except clause catches all exceptions",
                "suggestion": "Catch specific exceptions (ValueError, IOError, etc.)"
            }
        ],
        "summary": "Code works but has style issues, hardcoded values, and loose error handling",
        "quality_score": 55,
        "strengths": [
            "Basic structure is sound",
            "Functions have docstrings",
            "Input validation is present"
        ],
        "recommendations": [
            "Remove unnecessary intermediate variables",
            "Parameterize file paths instead of hardcoding",
            "Use specific exception handling instead of bare except"
        ]
    }


def save_artifacts(output_dir: str = ".") -> dict:
    """Save all sample artifacts to files"""
    artifacts = {}
    
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    module_def = generate_sample_module_definition()
    module_file = output_path / "sample_module_definition.json"
    with open(module_file, "w") as f:
        json.dump(module_def, f, indent=2)
    artifacts["module_definition"] = str(module_file)
    
    spec = generate_sample_technical_spec()
    spec_file = output_path / "sample_technical_spec.txt"
    with open(spec_file, "w") as f:
        f.write(spec)
    artifacts["technical_spec"] = str(spec_file)
    
    code = generate_sample_code()
    code_file = output_path / "sample_code.py"
    with open(code_file, "w") as f:
        f.write(code)
    artifacts["code"] = str(code_file)
    
    review = generate_sample_review_report()
    review_file = output_path / "sample_review_report.json"
    with open(review_file, "w") as f:
        json.dump(review, f, indent=2)
    artifacts["review_report"] = str(review_file)
    
    return artifacts


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Generate sample test artifacts')
    parser.add_argument('--output', type=str, default=".", help='Output directory for artifacts')
    
    args = parser.parse_args()
    
    print("📝 Generating sample artifacts...")
    artifacts = save_artifacts(args.output)
    
    print("\n✓ Artifacts generated:")
    for artifact_type, filepath in artifacts.items():
        print(f"  - {artifact_type}: {filepath}")
    
    print("\nYou can now use these artifacts for testing:")
    print(f"  python scripts/verify_code_quality.py --file {artifacts['code']}")
    print(f"  python scripts/test_agent_integration.py")


if __name__ == "__main__":
    main()
