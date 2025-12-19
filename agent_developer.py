import ollama
from prompt_library import DEVELOPER_PROMPT_WITH_COMMENTS

developer_prompt = DEVELOPER_PROMPT_WITH_COMMENTS

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