import ollama
import time

analyst_prompt = """
You are the LEAD SYSTEM ANALYST (Level 1).
Your goal is to convert a user's abstract idea into a strict technical architecture in YAML format.

RULES:
1. Do NOT use Markdown code blocks.
2. Output must be valid YAML.
3. Break the application into independent modules (Logic, Data, UI, Services).
4. Module names should be **CamelCase**.
5. Filenames should be lowercase with underscores only (e.g., WeatherService → weather_service.py).
6. Do NOT create modules that require installing external pip packages. Use only standard Python libraries.
7. Each module must have a start() or run() method.
8. Define inputs, outputs, and key data types in a 'glossary' section.
"""

def run_analyst():
    print("--- AGENT: LEAD ANALYST (L1) ---")
    user_idea = input("Enter your app idea (in English): ")
    print(f"\n[System] Analyzing request: '{user_idea}'...\n")
    start_time = time.time()

    response = ollama.chat(model='llama3.1', messages=[
        {'role': 'system', 'content': analyst_prompt},
        {'role': 'user', 'content': f"Project Idea: {user_idea}. Generate the YAML blueprint."},
    ])

    result = response['message']['content']
    clean_result = result.replace("```yaml", "").replace("```", "").strip()

    print("-" * 20 + " ANALYSIS RESULT " + "-" * 20)
    print(clean_result)
    print("-" * 60)

    filename = "draft_plan.yaml"
    with open(filename, "w", encoding="utf-8") as f:
        f.write(clean_result)

    elapsed = time.time() - start_time
    print(f">> Blueprint saved to '{filename}' (Time: {elapsed:.2f}s)")

if __name__ == "__main__":
    run_analyst()
