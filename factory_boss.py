import ollama
import os
import yaml
import json
import time
import subprocess
import sys
import re
from factory_boss_blackboard import FactoryBlackboard

MODEL = 'llama3.1'
MAX_RETRIES = 3

# ---------- UTILS ----------
def super_clean(text, format_type="python"):
    blocks = re.findall(r'```(?:python|yaml)?\s*(.*?)\s*```', text, re.DOTALL)
    if blocks:
        text = "\n".join(blocks)
    else:
        text = text.replace('```python', '').replace('```yaml', '').replace('```', '')

    if format_type == "yaml":
        return text.strip()

    lines = text.split('\n')
    cleaned = []
    junk_prefixes = (
        "here is", "sure", "note:", "this script", "i have",
        "however", "please", "the following", "i've added", "corrected version"
    )
    for line in lines:
        stripped = line.lower().strip()
        if any(stripped.startswith(p) for p in junk_prefixes) and not line.strip().startswith("#"):
            continue
        cleaned.append(line)
    return '\n'.join(cleaned).strip()

def ask_agent(role, system, message, format_type="python"):
    print(f"[{role}] 🧠 Thinking...")
    try:
        res = ollama.chat(model=MODEL, messages=[
            {'role': 'system', 'content': system},
            {'role': 'user', 'content': message}
        ])
        return super_clean(res['message']['content'], format_type)
    except Exception as e:
        print(f"❌ Błąd Ollama: {e}")
        return ""

def manage_dependencies(project_dir):
    print("\n📦 [DEPENDENCY MANAGER] Sprawdzanie bibliotek...")
    local_modules = [f.replace('.py', '') for f in os.listdir(project_dir) if f.endswith('.py')]
    found_imports = set()
    for fname in os.listdir(project_dir):
        if fname.endswith('.py'):
            with open(os.path.join(project_dir, fname), 'r', encoding='utf-8') as f:
                content = f.read()
                matches = re.findall(r'^(?:import|from)\s+([a-zA-Z0-9_]+)', content, re.MULTILINE)
                found_imports.update(matches)
    std_lib = [
        'os', 'sys', 're', 'time', 'json', 'yaml', 'math', 'subprocess',
        'datetime', 'random', 'collections', 'sqlite3', 'typing',
        'smtplib', 'email', 'hashlib', 'logging'
    ]
    to_install = [lib for lib in found_imports if lib not in std_lib and lib not in local_modules and lib != 'ollama']
    if to_install:
        print(f"📥 Installing pip dependencies: {to_install}")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", *to_install])
            with open(os.path.join(project_dir, "requirements.txt"), "w") as f:
                f.write("\n".join(to_install))
        except Exception as e:
            print(f"⚠️ Błąd podczas pip install: {e}")

# ---------- WORKFLOW ----------
def run_factory(idea):
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    project_dir = f"output/project_{timestamp}"
    os.makedirs(project_dir, exist_ok=True)
    print(f"🚀 WORKSPACE CREATED: {project_dir}")

    bb = FactoryBlackboard(idea, project_dir)

    # PHASE 1: L1 ANALYST
    print("\n======================================================================")
    print("PHASE 1: L1 ANALYST – STRATEGIC PLANNING")
    print("======================================================================")
    l1_sys = "You are a CTO. Output ONLY valid YAML. Define modules with {name, responsibility}."
    blueprint_raw = ask_agent("L1_ANALYST", l1_sys, f"App idea: {idea}", "yaml")
    try:
        blueprint = yaml.safe_load(blueprint_raw)
        bb.set_architecture(blueprint)
        print("📐 Blueprint accepted:")
        print(json.dumps(blueprint, indent=2))
    except Exception as e:
        print(f"❌ Błąd YAML: {e}")
        return

    # PHASE 2 & 3: L3 ARCHITECT & L4 DEVELOPER
    for module in blueprint['modules']:
        m_name = module['name'].lower().replace(" ", "_")
        filename = f"{m_name}.py"
        # L3: API spec
        l3_sys = "You are an Architect. Define strictly the API (functions/params) for this module. No code."
        spec = ask_agent(f"L3_{m_name}", l3_sys, f"Module: {module}")
        bb.register_module(m_name, filename, spec)
        # L4: Developer
        l4_sys = f"Senior Python Developer. Write ONLY Python code for {filename}. Use spec."
        code = ask_agent(f"L4_{m_name}", l4_sys, spec)
        with open(os.path.join(project_dir, filename), "w", encoding="utf-8") as f:
            f.write(code)

    # PHASE 4: L5 INTEGRATOR
    print("\n======================================================================")
    print("PHASE 4: L5 INTEGRATOR – ASSEMBLY")
    print("======================================================================")
    files_list = bb.state["files_created"]
    print(f"📦 Files: {files_list}")
    l5_sys = "You are a Lead Integrator. Write main.py to run the app. Use exact filenames for imports."
    main_code = ask_agent("L5_INTEGRATOR", l5_sys, f"Blackboard snapshot:\n{bb.snapshot()}\nIdea: {idea}")
    main_path = os.path.join(project_dir, "main.py")
    with open(main_path, "w", encoding="utf-8") as f:
        f.write(main_code)

    # DEPENDENCIES
    manage_dependencies(project_dir)

    # PHASE 5: AUTO-DEBUG LOOP
    print("\n======================================================================")
    print("PHASE 5: L6 AUTO-DEBUG LOOP")
    print("======================================================================")
    l6_sys = """You are a Maintenance Engineer. Fix the code.
1. Identify the broken file based on the traceback.
2. Output ONLY the fixed code.
3. Start response with 'FILE: filename.py' then the code.
"""
    for attempt in range(MAX_RETRIES):
        print(f"\n▶ Attempt {attempt+1}")
        proc = subprocess.run([sys.executable, "main.py"], cwd=project_dir, capture_output=True, text=True)
        if proc.returncode == 0:
            print("🎉 SUCCESS! Output:")
            print(proc.stdout)
            break
        else:
            error_msg = proc.stderr
            print("❌ ERROR:")
            print(error_msg)
            context = ""
            for fname in bb.state["files_created"]:
                with open(os.path.join(project_dir, fname), "r") as f:
                    context += f"\n--- {fname} ---\n{f.read()}\n"
            debug_msg = f"ERROR:\n{error_msg}\n\nPROJECT FILES:\n{context}"
            fix_raw = ask_agent("L6_DEBUGGER", l6_sys, debug_msg)
            match = re.search(r'FILE:\s*([\w\.]+)', fix_raw)
            if match:
                target_file = match.group(1)
                new_code = fix_raw.split(target_file)[-1].strip()
                with open(os.path.join(project_dir, target_file), "w", encoding="utf-8") as f:
                    f.write(super_clean(new_code))
                print(f"🔧 Applied fix to {target_file}")
            else:
                with open(main_path, "w", encoding="utf-8") as f:
                    f.write(super_clean(fix_raw))
                print("🔧 Applied fix to main.py (fallback)")

if __name__ == "__main__":
    if not os.path.exists("output"):
        os.makedirs("output")
    run_factory(input("What to build? "))
