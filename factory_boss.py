import ollama
import os
import yaml
import json
import time
import subprocess
import sys
import re
from factory_boss_blackboard import FactoryBlackboard
from agent_code_reviewer import run_reviewer
from agent_code_optimizer import run_optimizer
from agent_frontend_developer import run_frontend_developer, extract_frontend_files
from prompt_library import (
    FACTORY_BOSS_L1_PROMPT, FACTORY_BOSS_L2_PROMPT, FACTORY_BOSS_L3_PROMPT,
    FACTORY_BOSS_L5_PROMPT, AUTO_DEBUGGER_PROMPT, get_factory_boss_l4_prompt
)

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
        # Fallback: if no blocks, try to clean based on known junk
        # But first, check if it looks like code at all
        if format_type == "python":
            # If it starts with conversational text and has no code structure, reject it
            if not any(k in text for k in ['def ', 'import ', 'class ', 'print(', 'if ']):
                 # It might be pure garbage text
                 pass
        
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
        "however", "please", "the following", "i've added", "corrected version",
        "na podstawie", "w oparciu", "poniżej" # Add Polish/common conversational prefixes
    )
    for line in lines:
        stripped = line.lower().strip()
        if any(stripped.startswith(p) for p in junk_prefixes) and not line.strip().startswith("#"):
            continue
        cleaned.append(line)
    return '\n'.join(cleaned).strip()

def ask_agent(role, system, message, format_type="python", blackboard=None, agent_name=None, module_name=None):
    print(f"[{role}] 🧠 Thinking...", end='', flush=True)
    full_response = ""
    try:
        stream = ollama.chat(model=MODEL, messages=[
            {'role': 'system', 'content': system},
            {'role': 'user', 'content': message}
        ], stream=True)
        
        for chunk in stream:
            content = chunk['message']['content']
            full_response += content
            print(".", end='', flush=True)
            
        print(" Done!")
        cleaned_response = super_clean(full_response, format_type)
        
        if blackboard and agent_name and module_name:
            try:
                blackboard.log_agent_attempt(
                    agent=agent_name,
                    module=module_name,
                    attempt_num=1,
                    input_data=message,
                    output=cleaned_response,
                    status="success"
                )
            except Exception as log_e:
                print(f"⚠️ Failed to log agent attempt: {log_e}")
        
        return cleaned_response
    except Exception as e:
        print(f"\n❌ Error: {e}")
        if blackboard and agent_name and module_name:
            try:
                blackboard.log_agent_attempt(
                    agent=agent_name,
                    module=module_name,
                    attempt_num=1,
                    input_data=message,
                    output="",
                    status="failure",
                    error=str(e)
                )
            except:
                pass
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
        'functools', 'secrets', 'io', 'shutil', 'pathlib', 'glob',
        'unittest', 'argparse', 'inspect', 'importlib', 'pkgutil',
        'traceback', 'platform', 'uuid', 'calendar', 'copy', 'dataclasses',
        'enum', 'ipaddress', 'itertools', 'socket', 'struct', 'tempfile',
        'textwrap', 'urllib', 'warnings', 'weakref', 'zipfile', 'concurrent',
        'contextlib', 'csv', 'decimal', 'statistics', 'string', 'tarfile',
        'xml', 'html', 'http', 'ftplib', 'gzip', 'bz2', 'lzma', 'mmap',
        'pickle', 'queue', 'selectors', 'signal', 'ssl', 'termios', 'tty',
        'venv', 'webbrowser', 'wsgiref', 'xmlrpc', 'zoneinfo'
    ]
    
    internal_service_patterns = ['_service', '_handler', '_manager', '_controller', '_factory']
    
    def is_internal_module(lib):
        return any(lib.endswith(pattern) for pattern in internal_service_patterns) or \
               '_' in lib and lib.split('_')[0] in local_modules
    
    fake_modules = ['your_database_module', 'your_api_module', 'email_validator', 'safe_dump', 
                    'validate_email', 'jsonschema', 'placeholder', 'mock_module', 'sample_module']
    
    to_install = [lib for lib in found_imports 
                  if lib not in std_lib 
                  and lib not in local_modules 
                  and lib != 'ollama' 
                  and lib != 'api_registry'
                  and lib not in fake_modules
                  and not is_internal_module(lib)]

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
def run_factory(idea, debug_mode=False):
    overall_start_time = time.time()
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    project_dir = f"output/project_{timestamp}"
    os.makedirs(project_dir, exist_ok=True)
    print(f"🚀 WORKSPACE CREATED: {project_dir}")

    bb = FactoryBlackboard(idea, project_dir)
    phase_times = {}

    # PHASE 1 & 2: L1 ANALYST & L2 AUDITOR LOOP
    phase1_start = time.time()
    print("\n======================================================================")
    print("PHASE 1 & 2: L1 ANALYST & L2 AUDITOR – STRATEGIC PLANNING")
    print("======================================================================")
    
    l1_sys = FACTORY_BOSS_L1_PROMPT
    l2_sys = FACTORY_BOSS_L2_PROMPT

    blueprint = None
    max_planning_retries = 3
    
    for i in range(max_planning_retries):
        print(f"\n--- Planning Iteration {i+1} ---")
        
        # L1: Generate
        if i == 0:
            prompt = f"App idea: {idea}"
        else:
            prompt = f"Previous plan was rejected. Improve it based on this feedback:\n{audit_feedback}\n\nOriginal Idea: {idea}"
            
        blueprint_raw = ask_agent("L1_ANALYST", l1_sys, prompt, "yaml")
        
        # Try to parse
        try:
            temp_blueprint = yaml.safe_load(blueprint_raw)
             # --- HEALING LOGIC ---
            if isinstance(temp_blueprint, dict) and "modules" in temp_blueprint:
                if isinstance(temp_blueprint["modules"], dict):
                    print("⚠️ Detected 'modules' as dict. converting to list...")
                    new_modules = []
                    for key, val in temp_blueprint["modules"].items():
                         if isinstance(val, dict):
                             if "name" not in val:
                                 val["name"] = key
                             new_modules.append(val)
                    temp_blueprint["modules"] = new_modules
            # ---------------------
        except Exception as e:
            print(f"❌ YAML Parsing Failed: {e}")
            audit_feedback = f"YAML Syntax Error: {e}"
            continue

        # L2: Audit
        audit_raw = ask_agent("L2_AUDITOR", l2_sys, f"Review this blueprint:\n{json.dumps(temp_blueprint, indent=2)}")
        
        if "VERDICT: PASSED" in audit_raw:
            print("✅ Auditor approved the plan.")
            blueprint = temp_blueprint
            break
        else:
            print(f"⚠️ Auditor rejected the plan. Reason:\n{audit_raw}")
            audit_feedback = audit_raw

    if not blueprint:
        print("❌ Failed to generate a valid plan after retries. Exiting.")
        return

    phase1_duration = time.time() - phase1_start
    phase_times["Planning (L1+L2)"] = phase1_duration
    
    bb.set_architecture(blueprint)
    print(f"📐 Blueprint accepted and saved. (⏱️ {phase1_duration:.1f}s)")
    print(json.dumps(blueprint, indent=2))

    # PHASE 2 & 3: L3 ARCHITECT & L4 DEVELOPER
    phase2_start = time.time()
    print("\n======================================================================")
    print("PHASE 3: L3 ARCHITECT & L4 DEVELOPER – IMPLEMENTATION")
    print("======================================================================")
    for module in blueprint['modules']:
        m_name = module['name'].lower().replace(" ", "_")
        filename = f"{m_name}.py"
        module_type = module.get('module_type', 'service')
        
        # L3: API spec
        l3_sys = FACTORY_BOSS_L3_PROMPT
        l3_context = f"MODULE_TYPE: {module_type}\n\nModule Details:\n{yaml.dump(module)}"
        spec_raw = ask_agent(f"L3_{m_name}", l3_sys, l3_context, "yaml")
        
        # Parse L3 output to register API in Blackboard
        extracted_type = None
        try:
            l3_data = yaml.safe_load(spec_raw)
            if isinstance(l3_data, dict):
                # Extract module_type if present, fallback to what we passed in
                extracted_type = l3_data.get("module_type", module_type)
                
                if "api_spec" in l3_data:
                    bb.register_api(m_name, l3_data["api_spec"])
                    print(f"📝 Registered API contract for {m_name}")
                else:
                    # Fallback if model didn't follow YAML strict structure perfectly
                    bb.register_api(m_name, {"raw_spec": spec_raw})
            else:
                # Fallback if model didn't follow YAML strict structure perfectly
                bb.register_api(m_name, {"raw_spec": spec_raw})
        except Exception as e:
            print(f"⚠️ Failed to parse API spec for {m_name}: {e}")
            bb.register_api(m_name, {"raw_spec": spec_raw})
            extracted_type = module_type

        # Use extracted type (from architect) or fallback to input type
        final_module_type = extracted_type if extracted_type else module_type
        bb.register_module(m_name, filename, spec_raw, final_module_type)

        # L4: Developer
        l4_sys = get_factory_boss_l4_prompt(filename)
        l4_context = f"FILENAME: {filename}\nMODULE_TYPE: {final_module_type}\n\nSPECIFICATION:\n{spec_raw}"
        
        # RETRY LOOP FOR L4 GENERATION
        code = ""
        l4_success = False
        l4_attempts = 0
        l4_max_retries = 3
        
        while l4_attempts < l4_max_retries and not l4_success:
            l4_attempts += 1
            if l4_attempts > 1:
                print(f"⚠️ L4 Validation failed. Retrying ({l4_attempts}/{l4_max_retries})...")
                # Add "Previous Attempt Failed" context if retrying
                l4_context += f"\n\nIMPORTANT: Your previous attempt failed validation. ENSURE you include the root route @app.route('/') and render_template!"
            
            code = ask_agent(f"L4_{m_name}", l4_sys, l4_context, blackboard=bb, agent_name="developer", module_name=m_name)
        
            # ---------- L4 OUTPUT VALIDATION (WEB UI CONTRACT) ----------
            if final_module_type == "web_interface":
                validation_error = None
                if "render_template" not in code:
                    validation_error = f"{filename} does not render HTML (render_template missing)"
                
                # Regex check for root route to handle spaces: @app.route( ' / ' )
                if not re.search(r"@app\.route\(\s*['\"]/['\"]\s*\)", code):
                    validation_error = f"{filename} missing root '/' route"
                
                if validation_error:
                    print(f"❌ L4 Validation Error: {validation_error}")
                    if l4_attempts >= l4_max_retries:
                         raise RuntimeError(f"L4 validation failed after {l4_max_retries} attempts: {validation_error}")
                else:
                    l4_success = True
            else:
                l4_success = True
        # -----------------------------------------------------------

        # PHASE 3.5: L4.5 CODE REVIEWER
        print(f"\n📋 [L4.5_REVIEWER] Reviewing {filename}...")
        try:
            review_report = run_reviewer(code)
            quality_score = review_report.get("quality_score", 0)
            issues_list = review_report.get("issues", [])
            issues_count = len(issues_list)
            print(f"   Quality Score: {quality_score}/100, Issues Found: {issues_count}")
            if issues_list:
                print("   Issues identified:")
                for i, issue in enumerate(issues_list[:5], 1):
                    print(f"     {i}. {issue}")
            
            # PHASE 3.75: L4.75 CODE OPTIMIZER
            if quality_score < 85 or issues_count > 3:
                print(f"📝 [L4.75_OPTIMIZER] Optimizing {filename}...")
                optimized_code = run_optimizer(code, review_report)
                code = optimized_code
                optimizations_count = len(review_report.get("issues", []))
                print(f"   Applied {optimizations_count} optimizations")
                
                bb.log_quality_metrics(m_name, quality_score, issues_count, optimizations_count, review_report)
            else:
                print(f"   Code quality acceptable, skipping optimization")
                bb.log_quality_metrics(m_name, quality_score, issues_count, 0, review_report)
        except Exception as e:
            print(f"⚠️ Code review/optimization failed: {e}")
        
        file_path = os.path.join(project_dir, filename)
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(code)

        # PHASE 3.9: Frontend Generation for Web Modules
        is_web_module = any(
            keyword in m_name.lower() 
            for keyword in ["web", "interface", "ui", "frontend", "view"]
        )
        if is_web_module:
            print(f"\n🎨 [L4.5_FRONTEND_DEVELOPER] Generating UI for {m_name}...")
            try:
                # Generate frontend files
                frontend_code = run_frontend_developer(
                    idea, 
                    spec_raw,
                    blackboard=bb
                )
                
                # Extract HTML, CSS, JS files
                frontend_files = extract_frontend_files(frontend_code)
                
                if frontend_files:
                    # Create templates and static directories
                    templates_dir = os.path.join(project_dir, "templates")
                    static_dir = os.path.join(project_dir, "static")
                    os.makedirs(templates_dir, exist_ok=True)
                    os.makedirs(static_dir, exist_ok=True)
                    
                    # Save files with appropriate structure
                    for fname, content in frontend_files.items():
                        if fname.endswith('.html'):
                            target_path = os.path.join(templates_dir, fname)
                        elif fname.endswith('.css'):
                            target_path = os.path.join(static_dir, fname)
                        elif fname.endswith('.js'):
                            target_path = os.path.join(static_dir, fname)
                        else:
                            target_path = os.path.join(project_dir, fname)
                        
                        os.makedirs(os.path.dirname(target_path), exist_ok=True)
                        with open(target_path, "w", encoding="utf-8") as f:
                            f.write(content)
                        print(f"   ✅ Created {target_path}")
                    
                    # Update blackboard to track frontend files
                    bb.state.setdefault("frontend_files", []).extend(frontend_files.keys())
                else:
                    print(f"   ⚠️ No frontend files extracted")
            except Exception as e:
                print(f"   ⚠️ Frontend generation failed: {e}")

    phase2_duration = time.time() - phase2_start
    phase_times["Development (L3+L4)"] = phase2_duration
    print(f"✅ Development complete. (⏱️ {phase2_duration:.1f}s)")
    
    # PHASE 4: L5 INTEGRATOR
    phase3_start = time.time()
    print("\n======================================================================")
    print("PHASE 4: L5 INTEGRATOR – ASSEMBLY")
    print("======================================================================")
    files_list = bb.state["files_created"]
    print(f"📦 Files: {files_list}")
    
    # Provide explicit module type mapping to integrator
    modules_info = "Module Types:\n"
    for mod_name, mod_data in bb.state["modules"].items():
        mod_type = mod_data.get("module_type", "unknown")
        filename = mod_data.get("filename", f"{mod_name}.py")
        modules_info += f"  - {filename}: module_type = {mod_type}\n"
    
    l5_sys = FACTORY_BOSS_L5_PROMPT
    integrator_input = f"Blackboard snapshot:\n{bb.snapshot()}\n\n{modules_info}\n\nIdea: {idea}"
    
    l5_attempts = 0
    l5_max_retries = 3
    l5_success = False
    main_code = ""

    while l5_attempts < l5_max_retries and not l5_success:
        l5_attempts += 1
        if l5_attempts > 1:
             print(f"⚠️ L5 Generation failed validation. Retrying ({l5_attempts}/{l5_max_retries})...")
             integrator_input += "\n\nIMPORTANT: Your previous output was rejected. You MUST output ONLY valid Python code. Do not summarize or explain."

        main_code = ask_agent("L5_INTEGRATOR", l5_sys, integrator_input)
        
        # Validate main.py quality
        validation_error = None
        main_code_stripped = main_code.strip()
        
        # 1. Check for empty code
        if len(main_code_stripped) < 50:
            validation_error = "main.py is too short (likely utility-only)"
        
        # 2. Check for missing entry point
        elif "if __name__" not in main_code and "app.run" not in main_code and "from" not in main_code.split('\n')[0:5]:
             validation_error = "main.py may not have proper entry point or imports"

        # 3. Check for obvious conversational text
        elif main_code_stripped.startswith("The system") or \
             "consists of" in main_code_stripped[:200] or \
             "Here is the" in main_code_stripped[:100]:
             validation_error = "main.py contains textual description instead of code"
        
        # 4. Check if it's NOT python code (heuristics)
        elif not any(keyword in main_code for keyword in ["import ", "from ", "def ", "class ", "if __name__"]):
             validation_error = "main.py does not appear to be valid Python code"
        
        # 5. Check for utility function confusion
        elif "def format_" in main_code or "def validate_" in main_code or "def log_" in main_code:
            # Only flag this if it doesn't ALSO have the entry point
            if "if __name__" not in main_code:
                validation_error = "main.py contains utility functions instead of entry point"
        
        if validation_error:
             print(f"❌ L5 Validation Error: {validation_error}")
             if l5_attempts >= l5_max_retries:
                  print("⚠️ L5 failed after max retries. Saving last attempt anyway.")
                  l5_success = True 
        else:
             l5_success = True

    main_path = os.path.join(project_dir, "main.py")
    with open(main_path, "w", encoding="utf-8") as f:
        f.write(main_code)

    phase3_duration = time.time() - phase3_start
    phase_times["Integration (L5)"] = phase3_duration
    print(f"✅ Integration complete. (⏱️ {phase3_duration:.1f}s)")
    
    # DEPENDENCIES
    manage_dependencies(project_dir)

    # PHASE 5: AUTO-DEBUG LOOP
    phase4_start = time.time()
    print("\n======================================================================")
    print("PHASE 5: L6 AUTO-DEBUG LOOP")
    print("======================================================================")
    l6_sys = AUTO_DEBUGGER_PROMPT
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
            
            # Robust parsing
            lines = fix_raw.strip().split('\n')
            target_file = None
            code_lines = []
            
            for i, line in enumerate(lines):
                if line.startswith("FILE:"):
                    target_file = line.replace("FILE:", "").strip()
                    code_lines = lines[i+1:]
                    break
            
            if target_file:
                new_code = '\n'.join(code_lines).strip()
                new_code = super_clean(new_code) # Extra cleanup
                
                target_path = os.path.join(project_dir, target_file)
                os.makedirs(os.path.dirname(target_path), exist_ok=True)
                with open(target_path, "w", encoding="utf-8") as f:
                    f.write(new_code)
                print(f"🔧 Applied fix to {target_file}")
            else:
                # SMART FALLBACK: Infer target file from content
                new_code = super_clean(fix_raw)
                print("⚠️ Debugger did not specify FILE. Attempting to infer target...")
                
                inferred_file = None
                
                # 1. Check for Class Definitions
                class_match = re.search(r"class\s+(\w+)", new_code)
                if class_match:
                    class_name = class_match.group(1)
                    # Search modules for this class
                    for mod_name, mod_data in bb.state["modules"].items():
                        mod_filename = mod_data.get("filename", f"{mod_name}.py")
                        # Heuristic: Check if class name is contained in filename (e.g. UserService -> userservice.py)
                        if class_name.lower() in mod_filename.lower().replace("_", ""):
                            inferred_file = mod_filename
                            print(f"   👉 Inferred target file '{inferred_file}' from class '{class_name}'")
                            break
                
                # 2. Check for Script indicators (main.py)
                if not inferred_file:
                    if "if __name__" in new_code or "app.run" in new_code or "from" in new_code.split('\n')[0]:
                         # If it imports 'app' or has main block, likely main.py
                         if "from " in new_code and " import app" in new_code:
                             inferred_file = "main.py"
                             print("   👉 Inferred target file 'main.py' (looks like entry point)")

                if inferred_file:
                    target_path = os.path.join(project_dir, inferred_file)
                    with open(target_path, "w", encoding="utf-8") as f:
                        f.write(new_code)
                    print(f"🔧 Applied fix to {inferred_file} (inferred)")
                else:
                    print("❌ Could not identify target file. Aborting fix to prevent corruption.")
    
    phase4_duration = time.time() - phase4_start
    phase_times["Debugging (L6)"] = phase4_duration
    
    overall_duration = time.time() - overall_start_time
    
    metrics_summary = bb.metrics.get_summary()
    
    print("\n======================================================================")
    print("🎉 BUILD COMPLETE!")
    print("======================================================================")
    print("\n⏱️ TIMING BREAKDOWN:")
    for phase_name, duration in phase_times.items():
        print(f"  {phase_name:<30} {duration:>8.1f}s")
    print(f"  {'─' * 30} {'─' * 10}")
    print(f"  {'TOTAL BUILD TIME':<30} {overall_duration:>8.1f}s")
    
    if metrics_summary["modules_reviewed"] > 0:
        print("\n📊 CODE QUALITY SUMMARY:")
        print(f"  Modules reviewed: {metrics_summary['modules_reviewed']}")
        print(f"  Average quality score: {metrics_summary['average_score']:.1f}/100")
        print(f"  Total issues found: {metrics_summary['total_issues']}")
        print(f"  Total optimizations applied: {metrics_summary['total_optimizations']}")
    
    print(f"\n📍 Project directory: {project_dir}")
    print(f"📄 Blackboard: blackboard.json")
    print(f"📈 Metrics: metrics.json")

    if debug_mode:
        report_path = os.path.join(project_dir, "debug_report.md")
        bb.generate_debug_report(report_path)
        print(f"🐞 Debug Report: debug_report.md")

    print("=" * 70)

import argparse
import agent_analyst

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AgentFactory - AI Software Generator")
    parser.add_argument("--idea", type=str, help="The software idea to build")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode (generates detailed report)")
    args = parser.parse_args()

    if not os.path.exists("output"):
        os.makedirs("output")
        
    if args.idea:
        print(f"🚀 Starting Factory with idea: {args.idea}")
        run_factory(args.idea, debug_mode=args.debug)
    else:
        # Step 1: Gather Requirements via Interactive Analyst
        try:
            requirements = agent_analyst.interview_user()
            # Step 2: Run the Factory with the gathered context
            run_factory(requirements, debug_mode=args.debug)
        except KeyboardInterrupt:
            print("\n[Aborted]")
            sys.exit(0)
