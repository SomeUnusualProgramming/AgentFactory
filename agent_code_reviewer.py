import ollama
import json
from prompt_library import REVIEWER_PROMPT

def run_reviewer(code: str) -> dict:
    """
    Reviews generated Python code for quality issues.
    
    Args:
        code: Python code as string to review
    
    Returns:
        Dictionary with review report containing:
        - module_name: name of reviewed module
        - issues: list of issues found
        - summary: overall assessment
        - quality_score: 0-100 score
        - strengths: list of strengths
        - recommendations: list of recommendations
    """
    print("--- AGENT: CODE REVIEWER (L4.5) analyzing code... ---")
    
    try:
        response = ollama.chat(model='llama3.1', messages=[
            {'role': 'system', 'content': REVIEWER_PROMPT},
            {'role': 'user', 'content': f"Review this Python code:\n\n{code}"},
        ])
        
        review_text = response['message']['content']
        
        try:
            json_start = review_text.find('{')
            json_end = review_text.rfind('}') + 1
            
            if json_start >= 0 and json_end > json_start:
                json_str = review_text[json_start:json_end]
                review_dict = json.loads(json_str)
            else:
                review_dict = {
                    "module_name": "unknown",
                    "issues": [],
                    "summary": review_text[:200],
                    "quality_score": 50,
                    "strengths": [],
                    "recommendations": []
                }
        except json.JSONDecodeError:
            review_dict = {
                "module_name": "unknown",
                "issues": [],
                "summary": review_text[:200],
                "quality_score": 50,
                "strengths": [],
                "recommendations": []
            }
        
        return review_dict
        
    except Exception as e:
        print(f"Error in code review: {e}")
        return {
            "module_name": "unknown",
            "issues": [],
            "summary": f"Review failed: {str(e)}",
            "quality_score": 0,
            "strengths": [],
            "recommendations": []
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
