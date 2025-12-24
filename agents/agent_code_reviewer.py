import ollama
import json
from utils.code_standards import CodeValidator, get_validator, format_report_for_display
from utils.prompt_library import REVIEWER_PROMPT

def run_reviewer(code: str, module_name: str = "unknown", module_type: str = "service", filename: str = "unknown.py") -> dict:
    """
    Comprehensive code review with strict quality standards.
    
    Uses both static analysis (code_standards.py) and LLM-based review.
    
    Args:
        code: Python code as string to review
        module_name: Human-readable module name
        module_type: Type of module (web_interface, service, utility)
        filename: Python filename
    
    Returns:
        Dictionary with comprehensive review report including:
        - module_name: name of reviewed module
        - module_type: type of module
        - issues: list of issues found (with severity)
        - summary: overall assessment
        - quality_score: 0-100 score
        - verdict: APPROVE, REQUEST_CHANGES, or REJECT
        - static_analysis: Results from code_standards validator
    """
    print(f"--- AGENT: CODE REVIEWER (L4.5) analyzing {filename} ({module_type})... ---")
    
    # Phase 1: Static Analysis using code_standards
    print("   Phase 1: Running static analysis...")
    static_validator = get_validator(module_type, filename)
    static_report = static_validator.validate(code, module_name)
    
    print(f"   ✓ Static analysis complete: {static_report.quality_score}/100")
    print(format_report_for_display(static_report))
    
    # Phase 2: If static analysis fails critically, return immediately
    if static_report.quality_score < 50:
        print(f"   ✗ Code quality too low ({static_report.quality_score}/100) - rejecting without LLM review")
        return {
            "module_name": module_name,
            "module_type": module_type,
            "filename": filename,
            "issues": [issue.to_dict() for issue in static_report.issues],
            "summary": f"Code quality below acceptable threshold ({static_report.quality_score}/100)",
            "quality_score": static_report.quality_score,
            "verdict": "REJECT",
            "static_analysis": static_report.to_dict(),
            "llm_review": None,
        }
    
    # Phase 3: LLM-based detailed review
    print("   Phase 2: Running LLM-based code review...")
    try:
        prompt = f"""Review this {module_type} module code for:
1. ARCHITECTURE: Does it follow {module_type} module rules?
2. STYLE: PEP 8 compliance, type hints, naming
3. SECURITY: No hardcoded secrets, proper error handling
4. LOGIC: Any obvious bugs or inefficiencies?

COMMON PITFALLS TO CHECK FOR:
- `string.contains('x')` (Should be `'x' in string`)
- `response.json()` used on RSS/XML feeds (Should use XML parser)
- Importing non-existent "Interface" modules
- Missing `__init__` arguments for dependency injection
- Mutable default arguments `def f(x=[])`

Module type rules:
- web_interface: Flask routes, app instance, no business logic
- service: Business logic, type hints, error handling, no Flask, explicit __init__ deps
- utility: Pure functions, no state, no API/DB calls

Code:
```python
{code}
```

OUTPUT EXACTLY IN JSON:
{{
  "specific_issues": [
    {{"line": "line_number or 'N/A'", "issue": "description", "severity": "critical|high|medium|low"}}
  ],
  "strengths": ["list of good things"],
  "recommendations": ["top 3 improvements"],
  "verdict": "APPROVE|REQUEST_CHANGES|REJECT"
}}
"""
        
        response = ollama.chat(model='llama3.1', messages=[
            {'role': 'system', 'content': REVIEWER_PROMPT},
            {'role': 'user', 'content': prompt},
        ])
        
        review_text = response['message']['content']
        
        # Extract JSON from response
        try:
            json_start = review_text.find('{')
            json_end = review_text.rfind('}') + 1
            
            if json_start >= 0 and json_end > json_start:
                json_str = review_text[json_start:json_end]
                llm_review = json.loads(json_str)
            else:
                llm_review = {
                    "specific_issues": [],
                    "strengths": [],
                    "recommendations": [review_text[:200]],
                    "verdict": "REQUEST_CHANGES"
                }
        except json.JSONDecodeError:
            llm_review = {
                "specific_issues": [],
                "strengths": [],
                "recommendations": [review_text[:200]],
                "verdict": "REQUEST_CHANGES"
            }
        
        print(f"   ✓ LLM review complete: {llm_review.get('verdict', 'UNKNOWN')}")
        
    except Exception as e:
        print(f"   ⚠️ LLM review failed: {e}")
        llm_review = {
            "specific_issues": [],
            "strengths": [],
            "recommendations": [f"LLM review failed: {str(e)}"],
            "verdict": "REQUEST_CHANGES"
        }
    
    # Phase 4: Merge results and determine final verdict
    merged_issues = [issue.to_dict() for issue in static_report.issues]
    
    # Add LLM-specific issues if they have high/critical severity
    for issue in llm_review.get("specific_issues", []):
        if issue.get("severity") in ["critical", "high"]:
            merged_issues.append(issue)
    
    # Combine scores: 70% static, 30% LLM
    static_score = static_report.quality_score
    llm_adjustment = 0
    if llm_review.get("verdict") == "REJECT":
        llm_adjustment = -20
    elif llm_review.get("verdict") == "REQUEST_CHANGES":
        llm_adjustment = -10
    
    final_score = max(0, static_score + llm_adjustment)
    
    # Determine final verdict
    final_verdict = "APPROVE" if final_score >= 85 else ("REQUEST_CHANGES" if final_score >= 70 else "REJECT")
    
    return {
        "module_name": module_name,
        "module_type": module_type,
        "filename": filename,
        "quality_score": final_score,
        "issues": merged_issues,
        "summary": f"Static: {static_score}/100, LLM: {llm_review.get('verdict')}",
        "strengths": llm_review.get("strengths", []),
        "recommendations": llm_review.get("recommendations", []),
        "verdict": final_verdict,
        "static_analysis": static_report.to_dict(),
        "llm_review": llm_review,
    }


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
    
    review = run_reviewer(test_code)
    print("\n=== CODE REVIEW REPORT ===")
    print(json.dumps(review, indent=2))
