import ollama

architect_prompt = """
You are the MODULE ARCHITECT (Level 3).
Your job is to take ONE module definition from the Blueprint and create a precise TECHNICAL SPECIFICATION.

RULES:
1. Define clear function names.
2. Specify data types (string, integer, list, dict).
3. Provide a Mock Example of the input data.
4. Include safety instructions: use dict.get() for JSON/dict, try/except for external API calls.
5. Module filenames must be lowercase with underscores only (replace spaces, hyphens, or special characters with underscores). 
6. Class names must match the module responsibility exactly, in CamelCase.
7. Each module must have a start() or run() method for execution.
8. All functions must handle missing or invalid data safely.
9. Do not write actual code—only specification.
10. Do NOT include pip dependencies for local modules.
11. Output filename explicitly: filename: [module_name].py
"""

def run_architect(module_data):
    print(f"--- AGENT: MODULE ARCHITECT (L3) for {module_data['name']} ---")

    response = ollama.chat(model='llama3.1', messages=[
        {'role': 'system', 'content': architect_prompt},
        {'role': 'user', 'content': f"Architect this module: {module_data}"},
    ])

    return response['message']['content']

if __name__ == "__main__":
    test_module = {
        "name": "WeatherService",
        "responsibility": "Fetch weather data and process it",
        "inputs": ["location"],
        "outputs": ["temperature", "humidity", "condition"]
    }
    spec = run_architect(test_module)
    print(spec)
