import ollama
from prompt_library import ARCHITECT_PROMPT_SOLID

architect_prompt = ARCHITECT_PROMPT_SOLID

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
