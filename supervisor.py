import ollama
import time

# --- CONFIGURATION ---
MODEL = 'llama3.1'

def call_ai(system_prompt, user_message):
    response = ollama.chat(model=MODEL, messages=[
        {'role': 'system', 'content': system_prompt},
        {'role': 'user', 'content': user_message},
    ])
    return response['message']['content']

def run_production_cycle(user_idea):
    print(f"\n[SUPERVISOR] Starting production for: {user_idea}")

    # --- PROMPTS ---
    analyst_prompt = "You are a Lead Analyst. Output ONLY raw YAML based on user ideas."
    auditor_prompt = "You are a Logic Auditor. Review YAML. Start with 'VERDICT: PASSED' or 'VERDICT: FAILED' with reasons."

    current_blueprint = ""
    iteration = 1
    max_iterations = 3 # Zabezpieczenie przed nieskończoną pętlą

    while iteration <= max_iterations:
        print(f"\n--- ITERATION {iteration} ---")

        # 1. ANALYST PHASE
        print("[L1] Analyst is working...")
        if iteration == 1:
            current_blueprint = call_ai(analyst_prompt, f"Create a YAML blueprint for: {user_idea}")
        else:
            current_blueprint = call_ai(analyst_prompt, f"Your previous YAML failed. Fix it using this audit report: {audit_report}\n\nPrevious YAML:\n{current_blueprint}")

        # 2. AUDITOR PHASE
        print("[L2] Auditor is reviewing...")
        audit_report = call_ai(auditor_prompt, f"Review this YAML:\n{current_blueprint}")

        print(f"\n[AUDITOR REPORT]:\n{audit_report}")

        # 3. DECISION
        if "VERDICT: PASSED" in audit_report.upper():
            print("\n[SUCCESS] Blueprint verified! Saving final_plan.yaml")
            with open("final_plan.yaml", "w", encoding="utf-8") as f:
                f.write(current_blueprint)
            break
        else:
            print("\n[REJECTED] Sending back to Analyst for corrections...")
            iteration += 1

    if iteration > max_iterations:
        print("\n[TIMEOUT] Could not reach a perfect blueprint in 3 tries.")

if __name__ == "__main__":
    idea = "A simple expense tracker that saves receipts to a local text file."
    run_production_cycle(idea)