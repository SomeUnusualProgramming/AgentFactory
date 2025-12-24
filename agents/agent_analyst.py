import time
import sys
import os

# Add root to path if running directly
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.prompt_library import ANALYST_INTERVIEW_PROMPT, ANALYST_PROMPT
from core.constants import AGENT_L1_ANALYST, MODEL_NAME
from core.llm_client import chat_with_agent, ask_agent

CRITICAL_QUESTIONS = [
    "Main purpose of the product",
    "Target audience and usage context",
    "Top 1-3 user tasks",
    "Essential screens/views at launch",
    "Login/Roles requirements",
    "Data types to be stored",
    "Actions on data (create/edit/delete/export)",
    "Default language and date/time format"
]

def interview_user():
    print(f"--- AGENT: {AGENT_L1_ANALYST} ---")
    
    # 1. Select Mode
    print("Select Analysis Mode:")
    print("1. Abstract (Fast, infers details)")
    print("2. Precise (Thorough, asks all questions)")
    mode_choice = input("Choice (1/2): ").strip()
    mode_str = "Precise" if mode_choice == "2" else "Abstract"
    print(f"Mode selected: {mode_str}")

    # 2. Initial Idea
    user_idea = input("\nEnter your app idea (in English): ")
    
    # 3. Interview Loop
    print(f"\n[System] Analyzing request and gathering requirements ({mode_str} Mode)...\n")
    
    messages = [{'role': 'system', 'content': ANALYST_INTERVIEW_PROMPT.format(mode=mode_str)}]
    messages.append({'role': 'user', 'content': user_idea})
    
    gathered_context = ""
    
    while True:
        # Use chat_with_agent for interactive session
        content = chat_with_agent(AGENT_L1_ANALYST, messages)
        
        if "[[READY]]" in content:
            gathered_context = content.replace("[[READY]]", "").strip()
            print("\n" + "-"*40)
            print("[System] Requirements gathering complete.")
            print("-"*40)
            break
            
        print(f"\n[{AGENT_L1_ANALYST}]: {content}")
        answer = input("\n[You]: ")
        
        messages.append({'role': 'assistant', 'content': content})
        messages.append({'role': 'user', 'content': answer})
        
    return gathered_context

def run_analyst():
    gathered_context = interview_user()

    # 4. Generate YAML
    print(f"\n[System] Generating technical blueprint...\n")
    start_time = time.time()

    # Use ask_agent for the final blueprint generation
    # We pass the requirements as the user message
    result = ask_agent(
        AGENT_L1_ANALYST,
        ANALYST_PROMPT,
        f"Project Requirements:\n{gathered_context}\n\nGenerate the YAML blueprint.",
        format_type="yaml" # Use 'yaml' to auto-clean
    )

    print("-" * 20 + " ANALYSIS RESULT " + "-" * 20)
    print(result)
    print("-" * 60)

    filename = "draft_plan.yaml"
    with open(filename, "w", encoding="utf-8") as f:
        f.write(result)

    elapsed = time.time() - start_time
    print(f">> Blueprint saved to '{filename}' (Time: {elapsed:.2f}s)")

if __name__ == "__main__":
    run_analyst()
