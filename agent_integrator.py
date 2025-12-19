import ollama
from prompt_library import INTEGRATOR_PROMPT

integrator_prompt = INTEGRATOR_PROMPT

def run_integrator(blueprint, modules_code):
    print("--- AGENT: INTEGRATOR (L5) is assembling the app... ---")

    prompt_content = f"Blueprint:\n{blueprint}\n\nModules Code:\n{modules_code}"

    response = ollama.chat(model='llama3.1', messages=[
        {'role': 'system', 'content': integrator_prompt},
        {'role': 'user', 'content': prompt_content},
    ])

    return response['message']['content']

if __name__ == "__main__":
    blueprint_example = "Application: Expense Tracker. Flow: UI -> CoreLogic -> DatabaseHandler"

    database_code = """# (Kod klasy DatabaseHandler, który wygenerowałeś wcześniej)"""

    main_code = run_integrator(blueprint_example, database_code)

    with open("main.py", "w", encoding="utf-8") as f:
        clean_code = main_code.replace("```python", "").replace("```", "").strip()
        f.write(clean_code)

    print(">> Application assembled in 'main.py'!")