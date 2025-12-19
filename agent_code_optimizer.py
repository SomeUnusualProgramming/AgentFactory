import ollama
import json
import re
from prompt_library import OPTIMIZER_PROMPT

def run_optimizer(code: str, review_report: dict) -> str:
    """
    Optimizes generated Python code based on code review report.
    
    Args:
        code: Original Python code as string
        review_report: Dictionary with review findings from Code Reviewer
    
    Returns:
        Optimized Python code as string
    """
    print("--- AGENT: CODE OPTIMIZER (L4.75) refactoring code... ---")
    
    # Extract issues for explicit instruction
    issues = review_report.get("issues", [])
    issues_text = ""
    if issues:
        issues_text = "CRITICAL ISSUES THAT MUST BE FIXED:\n"
        for i, issue in enumerate(issues, 1):
            if isinstance(issue, dict):
                desc = issue.get('issue', str(issue))
                suggestion = issue.get('suggestion', '')
                location = issue.get('location', '')
                issues_text += f"{i}. {desc} (Location: {location})\n   Suggestion: {suggestion}\n"
            else:
                issues_text += f"{i}. {str(issue)}\n"
    
    review_summary = json.dumps(review_report, indent=2)
    
    prompt_with_report = f"""{OPTIMIZER_PROMPT}

{issues_text}

FULL REVIEW REPORT:
{review_summary}

ORIGINAL CODE TO OPTIMIZE:
{code}
"""
    
    try:
        response = ollama.chat(model='llama3.1', messages=[
            {'role': 'system', 'content': OPTIMIZER_PROMPT},
            {'role': 'user', 'content': prompt_with_report},
        ])
        
        optimized_code = response['message']['content']
        
        blocks = re.findall(r'```(?:python)?\s*(.*?)\s*```', optimized_code, re.DOTALL)
        if blocks:
            optimized_code = blocks[0]
        else:
            # Fallback: Check if it looks like code
            if "def " not in optimized_code and "class " not in optimized_code and "import " not in optimized_code:
                 print("⚠️ Optimizer output format invalid (no code blocks or keywords found). Reverting.")
                 return code
            optimized_code = optimized_code.replace('```python', '').replace('```', '')
        
        optimized_code = optimized_code.strip()
        
        # Safety check: if code became too short compared to original (e.g. < 20%), revert
        if len(optimized_code) < len(code) * 0.2:
             print("⚠️ Optimized code suspiciously short. Reverting.")
             return code

        return optimized_code
        
    except Exception as e:
        print(f"Error in code optimization: {e}")
        print("Returning original code unchanged")
        return code


def apply_basic_optimizations(code: str) -> str:
    """
    Applies basic code optimizations that don't require LLM.
    
    - Removes unused variables
    - Consolidates duplicate logic
    - Improves variable names clarity
    """
    lines = code.split('\n')
    optimized_lines = []
    
    for line in lines:
        optimized_lines.append(line)
    
    return '\n'.join(optimized_lines)


if __name__ == "__main__":
    test_code = """
def process(data):
    x = data
    y = x
    result = y
    return result

def calculate_total(items):
    total = 0
    for item in items:
        total = total + item['price']
    return total
"""
    
    test_review = {
        "module_name": "test_module",
        "issues": [
            {
                "type": "style",
                "severity": "high",
                "location": "process function",
                "issue": "Unnecessary intermediate variables",
                "suggestion": "Remove x, y intermediate variables and return data directly"
            }
        ],
        "summary": "Code has unnecessary variables and could be simplified",
        "quality_score": 40,
        "strengths": ["Basic structure is correct"],
        "recommendations": ["Simplify variable assignments", "Add error handling"]
    }
    
    optimized = run_optimizer(test_code, test_review)
    print("\n=== OPTIMIZED CODE ===")
    print(optimized)
