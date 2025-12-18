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
def fix_yaml_content(text):
    """
    Attempts to fix common YAML syntax errors in agent output,
    specifically unquoted strings containing colons or braces.
    """
    lines = text.split('\n')
    fixed_lines = []
    
    for line in lines:
        # Skip empty lines or comments
        if not line.strip() or line.strip().startswith('#'):
            fixed_lines.append(line)
            continue
            
        # Check for key: value pattern
        # This regex looks for: indent + optional dash + key + colon + space + value
        match = re.match(r'^(\s*(?:-\s+)?)([\w\s]+):\s+(.+)$', line)
        
        if match:
            prefix = match.group(1)
            key = match.group(2)
            val = match.group(3).strip()
            
            # If the value is already quoted, leave it alone
            if (val.startswith('"') and val.endswith('"')) or \
               (val.startswith("'") and val.endswith("'")):
                fixed_lines.append(line)
                continue
                
            # If value looks like a list or object start, skip
            if val in ['|', '>', '|-', '>-', '{', '[']:
                fixed_lines.append(line)
                continue
            
            # If value is just a number or boolean, skip
            if val.lower() in ['true', 'false', 'yes', 'no', 'null'] or val.replace('.', '', 1).isdigit():
                fixed_lines.append(line)
                continue

            # Heuristic: If value contains ':' or '{{', it MUST be quoted
            # Also quote if it's a long string description to be safe
            if ':' in val or '{{' in val or len(val) > 20:
                val_escaped = val.replace('"', '\\"')
                # Reconstruct the line
                new_line = f'{prefix}{key}: "{val_escaped}"'
                fixed_lines.append(new_line)
                continue
                
        fixed_lines.append(line)
        
    return '\n'.join(fixed_lines)

def super_clean(text, format_type="python"):
    blocks = re.findall(r'```(?:python|yaml)?\s*(.*?)\s*```', text, re.DOTALL)
    if blocks:
        text = "\n".join(blocks)
    else:
        text = text.replace('```python', '').replace('```yaml', '').replace('```', '')

    if format_type == "yaml":
        # Attempt to find the start of the YAML structure if it's mixed with text
        match = re.search(r'^(modules|glossary|api_spec):', text, re.MULTILINE)
        if match:
            text = text[match.start():]
        text = text.strip()
        return fix_yaml_content(text)

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
    print("\n📦 [DEPENDENCY MANAGER] Checking libraries...")
    local_modules = [f.replace('.py', '') for f in os.listdir(project_dir) if f.endswith('.py')]
    found_imports = set()
    
    # Scan all Python files for imports (recursively)
    for root, _, files in os.walk(project_dir):
        for fname in files:
            if fname.endswith('.py'):
                local_modules.append(fname.replace('.py', ''))
                with open(os.path.join(root, fname), 'r', encoding='utf-8') as f:
                    content = f.read()
                    matches = re.findall(r'^(?:import|from)\s+([a-zA-Z0-9_]+)', content, re.MULTILINE)
                    found_imports.update(matches)
    
    std_lib = [
        'os', 'sys', 're', 'time', 'json', 'yaml', 'math', 'subprocess',
        'datetime', 'random', 'collections', 'sqlite3', 'typing',
        'smtplib', 'email', 'hashlib', 'logging', 'threading', 'abc',
        'functools'
    ]
    
    # Filter out standard libs and local modules
    to_install = [lib for lib in found_imports if lib not in std_lib and lib not in local_modules and lib != 'ollama']

    # Explicitly check for implicit dependencies (FastAPI extras)
    if "fastapi" in to_install or "fastapi" in found_imports:
        if "python-multipart" not in to_install:
            to_install.append("python-multipart")
        if "uvicorn" not in to_install:
            to_install.append("uvicorn")
            
    if to_install:
        print(f"📥 Installing pip dependencies: {to_install}")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", *to_install])
            with open(os.path.join(project_dir, "requirements.txt"), "w") as f:
                f.write("\n".join(to_install))
        except Exception as e:
            print(f"⚠️ Error during pip install: {e}")

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
    l1_sys = """You are a CTO and Systems Architect. 
Your goal is to design a robust, modular Python Web Application.
Prefer using Flask or FastAPI.
The architecture MUST include:
1. A clear separation of concerns (Routes, Logic, Data).
2. A 'web_interface' module that handles HTTP routes and rendering.
3. Service modules for core logic.
Output ONLY valid YAML. 
Do NOT use Markdown code blocks.
Do NOT include any introductory text.
Start the output immediately with the "modules" key.
IMPORTANT: Any strings containing placeholders like {{ VARIABLE }} MUST be enclosed in double quotes.

Example format:
modules:
  - name: WebInterface
    responsibility: "Handles HTTP routes and HTML rendering using Flask. API Key: {{ API_KEY }}"
  - name: CoreLogic
    responsibility: Business logic.
"""
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
        l3_sys = """You are a Senior Architect. 
Define strictly the API (functions/params) for this module.
If this is a Web/UI module, define the Flask/FastAPI routes and the HTML templates (conceptually).
If this is a Logic module, define the functions and return types.

IMPORTANT:
1. Output MUST be valid YAML only.
2. DO NOT write any Python code, imports, or implementation details.
3. DO NOT use markdown code blocks like ```python.
4. Structure the output as follows:
api_spec:
  [function_name]:
    signature: "[name]([params]) -> [return_type]"
    description: "[description]"
    validation_rules:
      - "[rule 1]"
      - "[rule 2]"

Example:
api_spec:
  calculate_tax:
    signature: "calculate_tax(amount: float, rate: float) -> float"
    description: "Calculates tax based on rate."
    validation_rules:
      - "amount must be non-negative"
      - "rate must be between 0 and 1"
"""
        spec_raw = ask_agent(f"L3_{m_name}", l3_sys, f"Module: {module}", "yaml")
        
        # Parse L3 output to register API in Blackboard
        try:
            l3_data = yaml.safe_load(spec_raw)
            if isinstance(l3_data, dict) and "api_spec" in l3_data:
                bb.register_api(m_name, l3_data["api_spec"])
                print(f"📝 Registered API contract for {m_name}")
            else:
                # Fallback if model didn't follow YAML strict structure perfectly
                bb.register_api(m_name, {"raw_spec": spec_raw})
        except Exception as e:
            print(f"⚠️ Failed to parse API spec for {m_name}: {e}")
            bb.register_api(m_name, {"raw_spec": spec_raw})

        bb.register_module(m_name, filename, spec_raw)

        # L4: Developer
        l4_sys = f"""Senior Python Developer. 
Write ONLY Python code for {filename}.
Follow the specification exactly.
If this is a Web/UI module:
- Use Flask or FastAPI as implied by the spec.
- You MAY embed HTML in the Python file using multi-line strings (e.g., render_template_string).
- Ensure the code is self-contained and runnable.

STRICT CONTRACT ENFORCEMENT:
- Implement ONLY the functions defined in the API Spec.
- Include comments explaining the validation rules.
"""
        code = ask_agent(f"L4_{m_name}", l4_sys, spec_raw)
        file_path = os.path.join(project_dir, filename)
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(code)

    # PHASE 4: L5 INTEGRATOR
    print("\n======================================================================")
    print("PHASE 4: L5 INTEGRATOR – ASSEMBLY")
    print("======================================================================")
    files_list = bb.state["files_created"]
    print(f"📦 Files: {files_list}")
    l5_sys = """You are a Lead Integrator. 
Write main.py to run the application.
If the application is a Web App (Flask/FastAPI), ensure:
1. The web server is started (e.g., app.run(debug=True, port=5000)).
2. All routes are registered.
Use exact filenames for imports.
Output ONLY the Python code.
Do NOT include any Markdown, explanations, or route lists outside of comments.
Do NOT include any introductory text.

IMPORTANT: Check the "api_registry" in the Blackboard snapshot.
Only import and use functions/classes that are explicitly defined in the API Registry.
"""
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
    l6_sys = """You are a Maintenance Engineer. 
Your goal is to fix the Python code based on the provided Traceback and Project Files.

RULES:
1. Analyze the Traceback to find the root cause (e.g., ImportError, IndentationError, NameError).
2. Look at the "PROJECT FILES" to see the context of the error.
3. If the error is an ImportError, check if the module name matches the filename or if the class/function exists.
4. If the error is an IndentationError, fix the indentation of the specific block.
5. If the error is a NameError, ensure the variable or function is defined or imported.
6. Output ONLY the fixed code for the single file that needs correction.
7. Start your response with 'FILE: [filename]' on the first line, followed by the full corrected code.
8. DO NOT write any conversational text, explanations, or summaries. ONLY CODE.

Example Response:
FILE: main.py
import os
... (rest of the corrected code) ...
"""
    for attempt in range(MAX_RETRIES):
        print(f"\n▶ Attempt {attempt+1}")
        
        # Use Popen to handle potential Web Servers (long-running)
        proc = subprocess.Popen(
            [sys.executable, "main.py"], 
            cwd=project_dir, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE,
            text=True
        )

        try:
            # Wait 5 seconds to see if it crashes
            stdout, stderr = proc.communicate(timeout=5)
            return_code = proc.returncode
        except subprocess.TimeoutExpired:
            # Still running = Success (Web Server)
            print("🎉 SUCCESS! App is running (Web Server active). Killing to finish workflow.")
            proc.kill()
            break

        if return_code == 0:
            print("🎉 SUCCESS! Output:")
            print(stdout)
            break
        else:
            error_msg = stderr
            print("❌ ERROR:")
            print(error_msg)
            
            # --- AUTO-INSTALL MISSING PACKAGES ---
            # Check for "ModuleNotFoundError" or explicit "requires '...'" messages
            missing_pkg_match = re.search(r"ModuleNotFoundError: No module named '([\w\-]+)'", error_msg)
            multipart_match = re.search(r'requires "([\w\-]+)"', error_msg)
            
            pkg_to_install = None
            if missing_pkg_match:
                pkg_to_install = missing_pkg_match.group(1)
            elif multipart_match:
                pkg_to_install = multipart_match.group(1)

            if pkg_to_install:
                print(f"📦 Auto-Debug detected missing package: {pkg_to_install}. Installing...")
                try:
                    subprocess.check_call([sys.executable, "-m", "pip", "install", pkg_to_install])
                    print("✅ Package installed. Retrying...")
                    continue # Skip the AI Agent fix and try running again immediately
                except Exception as e:
                    print(f"⚠️ Failed to auto-install {pkg_to_install}: {e}")
            # -------------------------------------

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
                target_path = os.path.join(project_dir, target_file)
                os.makedirs(os.path.dirname(target_path), exist_ok=True)
                with open(target_path, "w", encoding="utf-8") as f:
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
