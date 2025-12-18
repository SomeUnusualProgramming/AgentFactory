import ollama

integrator_prompt = """
You are the SYSTEM INTEGRATOR (Level 5).
Your job is to write the 'main.py' file that connects all developed modules into a working application.

RULES:
1. Import the classes/functions from the generated files.
2. Create the main execution loop or entry point.
3. Ensure that data flows correctly from UI to Logic to Database, according to the Blueprint.
4. Output ONLY the Python code. No explanations.
"""

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