import ollama

developer_prompt = """
You are a SENIOR PYTHON DEVELOPER (Level 4).
Your task is to implement a Python module based EXACTLY on the provided TECHNICAL SPECIFICATION.

RULES:
1. Use only standard Python libraries unless specified otherwise.
2. Ensure the code is clean, commented, and handles basic errors (try-except).
3. Output ONLY the Python code. No explanations.
4. Your code must match the function names and parameters from the specification.
"""

def run_developer(specification):
    print("--- AGENT: DEVELOPER (L4) is coding... ---")

    response = ollama.chat(model='llama3.1', messages=[
        {'role': 'system', 'content': developer_prompt},
        {'role': 'user', 'content': f"Implement this specification:\n{specification}"},
    ])

    return response['message']['content']

if __name__ == "__main__":
    spec_from_architect = """
    MODULE_NAME: DATABASE_HANDLER
    FUNCTIONS:
      - save_receipt(receipt_text: str) -> bool
        description: Saves to local directory.
      - check_directory() -> bool
        description: Checks if directory exists.
    MOCK_INPUT: {"receipt_text": "Hello World!", "directory_path": "./receipts"}
    """

    code = run_developer(spec_from_architect)

    filename = "database_handler.py"
    with open(filename, "w", encoding="utf-8") as f:
        clean_code = code.replace("```python", "").replace("```", "").strip()
        f.write(clean_code)

    print(f">> Module saved to '{filename}'")