import ollama
from utils.prompt_library import AUDITOR_PROMPT

auditor_prompt = AUDITOR_PROMPT

def run_auditor():
    print("--- AGENT: LOGIC AUDITOR (L2) ---")

    try:
        with open("draft_plan.yaml", "r", encoding="utf-8") as f:
            blueprint = f.read()
    except FileNotFoundError:
        print("Error: draft_plan.yaml not found!")
        return

    print("[System] Auditing the blueprint for logic errors...\n")

    response = ollama.chat(model='llama3.1', messages=[
        {'role': 'system', 'content': auditor_prompt},
        {'role': 'user', 'content': f"Review this blueprint:\n\n{blueprint}"},
    ])

    verdict = response['message']['content']

    print("-" * 20 + " AUDIT REPORT " + "-" * 20)
    print(verdict)
    print("-" * 50)

    if "PASSED" in verdict:
        print(">> Logic verified. Ready for Module Architects.")
    else:
        print(">> Logic rejected. Improvements needed.")

if __name__ == "__main__":
    run_auditor()
