import ollama
import os
import yaml
import json
import time
import subprocess
import sys
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
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
    Fixes common YAML syntax errors in agent output.
    Removes invalid lines and quotes values containing special characters.
    """
    lines = text.split('\n')
    fixed_lines = []
    
    for i, line in enumerate(lines):
        original_line = line
        
        # Skip empty lines or comments
        if not line.strip() or line.strip().startswith('#'):
            fixed_lines.append(line)
            continue
        
        # Get indentation level
        indent = len(line) - len(line.lstrip())
        stripped = line.strip()
        
        # Lines starting with '-' are list items
        if stripped.startswith('-'):
            # List item line - keep it
            fixed_lines.append(line)
            continue
        
        # Check for key: value pattern (must have a colon)
        if ':' not in stripped:
            # No colon - this line doesn't fit YAML structure
            # Only keep if it's indented (continuation) and previous line didn't end with colon
            if i > 0 and indent > 0:
                prev_stripped = lines[i-1].strip()
                # Check if previous line expects a value (ends with |, >, or has key: pattern)
                if prev_stripped.endswith(('|', '>', '|-', '>-', '[', '{')):
                    fixed_lines.append(line)
                    continue
            # Skip this line - it's orphaned text
            continue
        
        # Has a colon - parse it
        colon_idx = stripped.find(':')
        key = stripped[:colon_idx].strip()
        val = stripped[colon_idx+1:].strip()
        
        # Validate key format (should be word characters, spaces, or dashes)
        if not re.match(r'^[\w\s-]+$', key):
            # Invalid key format
            continue
        
        # Handle empty or special values
        if not val or val in ['|', '>', '|-', '>-', '{', '[']:
            fixed_lines.append(line)
            continue
        
        # If value is already quoted or is a number/boolean, leave it
        if (val.startswith('"') and val.endswith('"')) or \
           (val.startswith("'") and val.endswith("'")):
            fixed_lines.append(line)
            continue
        
        if val.lower() in ['true', 'false', 'yes', 'no', 'null'] or val.replace('.', '', 1).isdigit():
            fixed_lines.append(line)
            continue
        
        # Check if value is a list or dict literal
        if val.startswith('[') and val.endswith(']'):
            # It's a JSON-style list, keep it as-is
            fixed_lines.append(line)
            continue
        
        if val.startswith('{') and val.endswith('}'):
            # It's a JSON-style dict, keep it as-is
            fixed_lines.append(line)
            continue
        
        # Quote if value contains special characters or is long
        if ':' in val or '{{' in val or '"' in val or "'" in val or len(val) > 50:
            val_escaped = val.replace('\\', '\\\\').replace('"', '\\"')
            indent_str = ' ' * indent
            new_line = f'{indent_str}{key}: "{val_escaped}"'
            fixed_lines.append(new_line)
        else:
            fixed_lines.append(original_line)
    
    return '\n'.join(fixed_lines)

def super_clean(text, format_type="python"):
    blocks = re.findall(r'```(?:python|py|yaml|yml|json)?\s*(.*?)\s*```', text, re.DOTALL | re.IGNORECASE)
    if blocks:
        text = "\n".join(blocks)
    else:
        text = text.replace('```python', '').replace('```yaml', '').replace('```yml', '').replace('```json', '').replace('```', '')

    if format_type == "yaml":
        # Remove SQL statements and comments that break YAML parsing
        text = re.sub(r'^--.*$', '', text, flags=re.MULTILINE)
        text = re.sub(r'^(CREATE|ALTER|DROP|SELECT|INSERT|UPDATE|DELETE|PRAGMA)\s+.*?(?:;|$)', '', text, flags=re.MULTILINE | re.IGNORECASE | re.DOTALL)
        
        # Remove YAML document separators
        text = re.sub(r'^---\s*$', '', text, flags=re.MULTILINE).strip()
        
        # Find the start of the YAML structure
        match = re.search(r'^(modules|glossary|api_spec|blueprint):', text, re.MULTILINE)
        if match:
            text = text[match.start():]
        
        text = text.strip()
        
        # Clean lines that don't fit YAML structure
        lines = text.split('\n')
        min_indent = float('inf')
        
        # Find minimum indentation to establish baseline
        for line in lines:
            if line.strip() and not line.strip().startswith('#'):
                indent = len(line) - len(line.lstrip())
                if ':' in line or line.strip().startswith('-'):
                    min_indent = min(min_indent, indent)
        
        if min_indent == float('inf'):
            min_indent = 0
        
        # Process lines with context
        cleaned_lines = []
        for i, line in enumerate(lines):
            stripped = line.strip()
            
            # Empty or comment lines are OK
            if not stripped or stripped.startswith('#'):
                cleaned_lines.append(line)
                continue
            
            # Get indentation
            indent = len(line) - len(line.lstrip())
            
            # List items and key-value pairs are OK
            if stripped.startswith('-') or ':' in stripped:
                cleaned_lines.append(line)
                continue
            
            # Check if this could be a continuation line
            if i > 0 and indent > min_indent:
                prev_line = lines[i-1].strip()
                # If previous line ends with |, >, {, or [ - this is a continuation
                if prev_line.endswith(('|', '>', '|-', '>-', '{', '[')):
                    cleaned_lines.append(line)
                    continue
            
            # Orphaned text with no colon at root/base level - skip it
            if indent <= min_indent and ':' not in stripped:
                continue
            
            cleaned_lines.append(line)
        
        text = '\n'.join(cleaned_lines).strip()
        return fix_yaml_content(text)

    lines = text.split('\n')
    cleaned = []
    junk_prefixes = (
        "here is", "sure", "note:", "this script", "i have",
        "however", "please", "the following", "i've added", "corrected version",
        "na podstawie", "w oparciu", "poniżej"
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

def extract_audit_issues(audit_text):
    """
    Extract structured issues from auditor feedback.
    Parses the audit report and returns a list of actionable issues.
    """
    issues = []
    
    lines = audit_text.split('\n')
    for line in lines:
        line = line.strip()
        
        if not line or line.startswith('VERDICT:') or line.startswith('---') or line.startswith('['):
            continue
        
        line_lower = line.lower()
        
        if 'circular' in line_lower and 'dependency' in line_lower:
            issues.append(f"ARCHITECTURE: Remove circular dependencies - {line[:120]}")
        
        elif 'missing' in line_lower and 'responsibility' in line_lower:
            issues.append(f"COMPLETENESS: Add clear responsibility description to all modules - {line[:80]}")
        
        elif 'missing' in line_lower and 'field' in line_lower:
            issues.append(f"STRUCTURE: Ensure all modules have required fields (name, filename, type, responsibility, requires)")
        
        elif 'tight coupling' in line_lower:
            issues.append(f"COUPLING: Reduce dependencies between modules for loose coupling")
        
        elif ('duplication' in line_lower or 'duplicate' in line_lower or 'overlapping' in line_lower) and 'responsibility' in line_lower:
            issues.append(f"DESIGN: Consolidate modules with overlapping responsibilities")
        
        elif 'unclear' in line_lower:
            issues.append(f"CLARITY: Make module responsibilities clearer and more specific")
    
    if not issues and 'FAILED' in audit_text.upper():
        issues.append("GENERAL: Review architecture for violations of separation of concerns")
    
    return issues

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
    accumulated_issues = []
    
    for i in range(max_planning_retries):
        print(f"\n--- Planning Iteration {i+1} ---")
        
        # L1: Generate
        if i == 0:
            prompt = f"App idea: {idea}"
            print("  📝 L1 ANALYST: Analyzing app idea and creating architecture...")
        else:
            issues_context = "ISSUES TO FIX FROM PREVIOUS ATTEMPTS:\n"
            for j, issue in enumerate(accumulated_issues, 1):
                issues_context += f"{j}. {issue}\n"
            prompt = f"{issues_context}\nOriginal Idea: {idea}\n\nCreate a completely new architecture that addresses all the issues listed above."
            print(f"  📝 L1 ANALYST: Fixing {len(accumulated_issues)} issues from previous attempt...")
            
        blueprint_raw = ask_agent("L1_ANALYST", l1_sys, prompt, "yaml")
        
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
            accumulated_issues.append(f"YAML Syntax: {str(e)[:80]}")
            continue

        # L2: Audit
        print(f"  🔍 L2 AUDITOR: Reviewing architecture ({len(temp_blueprint.get('modules', []))} modules)...")
        audit_raw = ask_agent("L2_AUDITOR", l2_sys, f"Review this blueprint:\n{json.dumps(temp_blueprint, indent=2)}")
        
        if "VERDICT: PASSED" in audit_raw:
            print(f"✅ Auditor approved! Architecture includes {len(temp_blueprint.get('modules', []))} modules:")
            for mod in temp_blueprint.get('modules', []):
                print(f"    • {mod.get('name')}: {mod.get('responsibility')[:60]}...")
            blueprint = temp_blueprint
            break
        else:
            print(f"⚠️ Auditor rejected the plan. Issues found:")
            structured_issues = extract_audit_issues(audit_raw)
            for issue in structured_issues[:3]:
                print(f"    • {issue[:70]}...")
                if issue not in accumulated_issues:
                    accumulated_issues.append(issue)

    if not blueprint:
        print("❌ Failed to generate a valid plan after retries. Exiting.")
        return

    phase1_duration = time.time() - phase1_start
    phase_times["Planning (L1+L2)"] = phase1_duration
    
    bb.set_architecture(blueprint)
    print(f"📐 Blueprint accepted and saved. (⏱️ {phase1_duration:.1f}s)")
    print(json.dumps(blueprint, indent=2))
    
    # LOG PLANNING ATTEMPTS
    for i, issue in enumerate(accumulated_issues, 1):
        bb.log_agent_attempt(
            agent="L1_ANALYST+L2_AUDITOR",
            module="planning",
            attempt_num=i,
            input_data=f"Iteration {i}",
            output=f"Resolved: {issue}",
            status="success"
        )

    # PHASE 2 & 3: L3 ARCHITECT & L4 DEVELOPER – PARALLEL EXECUTION
    phase2_start = time.time()
    print("\n======================================================================")
    print("PHASE 3: L3 ARCHITECT & L4 DEVELOPER – PARALLEL IMPLEMENTATION")
    print("======================================================================")
    print(f"🚀 Launching {len(blueprint['modules'])} parallel module generations...")
    
    # Use ThreadPoolExecutor for parallel module generation
    max_workers = min(4, len(blueprint['modules']))  # Max 4 parallel workers
    results = {}
    
    def _generate_single_module(module):
        """Generate a single module in parallel"""
        m_name = module['name'].lower().replace(" ", "_")
        filename = f"{m_name}.py"
        module_type = module.get('module_type', 'service')
        
        print(f"  ▶ [{m_name}] Starting L3+L4 generation...")
        print(f"    📋 L3 ARCHITECT: Designing {module_type} with API specification...")
        
        # L3: API spec
        l3_sys = FACTORY_BOSS_L3_PROMPT
        l3_context = f"MODULE_TYPE: {module_type}\n\nModule Details:\n{yaml.dump(module)}"
        spec_raw = ask_agent(f"L3_{m_name}", l3_sys, l3_context, "yaml", 
                           blackboard=bb, agent_name="architect", module_name=m_name)
        
        # Parse L3 output to register API in Blackboard
        extracted_type = None
        try:
            l3_data = yaml.safe_load(spec_raw)
            if isinstance(l3_data, dict):
                extracted_type = l3_data.get("module_type", module_type)
                if "api_spec" in l3_data:
                    bb.register_api(m_name, l3_data["api_spec"])
                else:
                    bb.register_api(m_name, {"raw_spec": spec_raw})
            else:
                bb.register_api(m_name, {"raw_spec": spec_raw})
        except Exception as e:
            print(f"    ⚠️ Failed to parse API spec for {m_name}: {e}")
            bb.register_api(m_name, {"raw_spec": spec_raw})
            extracted_type = module_type

        final_module_type = extracted_type if extracted_type else module_type
        bb.register_module(m_name, filename, spec_raw, final_module_type)

        # L4: Developer
        print(f"    💻 L4 DEVELOPER: Implementing {final_module_type} module...")
        l4_sys = get_factory_boss_l4_prompt(filename, module_type=final_module_type)
        l4_context = f"FILENAME: {filename}\nMODULE_TYPE: {final_module_type}\n\nSPECIFICATION:\n{spec_raw}"
        
        code = ""
        l4_success = False
        l4_attempts = 0
        l4_max_retries = 3
        
        while l4_attempts < l4_max_retries and not l4_success:
            l4_attempts += 1
            if l4_attempts > 1:
                print(f"    ⚠️ L4 Validation failed. Retrying ({l4_attempts}/{l4_max_retries})...")
                l4_context += f"\n\nIMPORTANT: Your previous attempt failed validation. ENSURE you include the root route @app.route('/') and render_template!"
            
            code = ask_agent(f"L4_{m_name}", l4_sys, l4_context, blackboard=bb, agent_name="developer", module_name=m_name)
        
            if final_module_type == "web_interface":
                validation_error = None
                if "render_template" not in code:
                    validation_error = f"{filename} does not render HTML"
                if not re.search(r"@app\.route\(\s*['\"]/['\"]\s*\)", code):
                    validation_error = f"{filename} missing root '/' route"
                
                if validation_error:
                    print(f"    ❌ L4 Validation Error: {validation_error}")
                    if l4_attempts >= l4_max_retries:
                        raise RuntimeError(f"L4 validation failed: {validation_error}")
                else:
                    l4_success = True
            else:
                l4_success = True

        # L4.5 Code Review (with strict quality standards)
        try:
            print(f"    🔎 CODE REVIEW: Analyzing code quality (type: {final_module_type})...")
            review_report = run_reviewer(
                code=code,
                module_name=m_name,
                module_type=final_module_type,
                filename=filename
            )
            quality_score = review_report.get("quality_score", 0)
            issues_count = len(review_report.get("issues", []))
            verdict = review_report.get("verdict", "PENDING")
            
            if issues_count > 0:
                print(f"      Quality Score: {quality_score}/100, Issues: {issues_count}, Verdict: {verdict}")
            else:
                print(f"      Quality Score: {quality_score}/100 - No issues! Verdict: {verdict}")
            
            # Module must achieve 85+ score or REQUEST_CHANGES to proceed with optimization
            if quality_score < 85 and verdict in ["REQUEST_CHANGES", "REJECT"]:
                if quality_score < 70:
                    print(f"    ❌ Code quality critical ({quality_score}/100). Requesting re-generation...")
                    # Could retry L4 here with feedback
                    pass
                else:
                    print(f"    ⚡ OPTIMIZER: Applying improvements...")
                    code = run_optimizer(code, review_report)
                    bb.log_quality_metrics(m_name, quality_score, issues_count, issues_count, review_report)
                    print(f"      Optimizations applied!")
            else:
                bb.log_quality_metrics(m_name, quality_score, issues_count, 0, review_report)
                print(f"      ✅ Code meets quality standards!")
        except Exception as e:
            print(f"    ⚠️ Code review failed: {e}")
        
        # Save module file
        file_path = os.path.join(project_dir, filename)
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(code)
        print(f"  ✅ [{m_name}] Module generated successfully")
        
        return {"m_name": m_name, "filename": filename, "spec": spec_raw, "code": code}
    
    # Run module generation in parallel
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_generate_single_module, module): module for module in blueprint['modules']}
        for future in as_completed(futures):
            try:
                result = future.result()
                results[result['m_name']] = result
            except Exception as e:
                print(f"❌ Module generation failed: {e}")
    
    # Frontend generation (sequential after all modules done)
    print("\n🎨 Generating frontend files...")
    for m_name in results:
        result = results[m_name]
        is_web_module = any(kw in m_name.lower() for kw in ["web", "interface", "ui", "frontend", "view"])
        
        if is_web_module:
            try:
                print(f"  🎨 L4.5 FRONTEND DEVELOPER: Creating UI for '{m_name}'...")
                frontend_code = run_frontend_developer(idea, result['spec'], blackboard=bb)
                frontend_files = extract_frontend_files(frontend_code)
                
                if frontend_files:
                    templates_dir = os.path.join(project_dir, "templates")
                    static_dir = os.path.join(project_dir, "static")
                    os.makedirs(templates_dir, exist_ok=True)
                    os.makedirs(static_dir, exist_ok=True)
                    
                    html_files = []
                    css_files = []
                    js_files = []
                    
                    for fname, content in frontend_files.items():
                        if fname.endswith('.html'):
                            target_path = os.path.join(templates_dir, fname)
                            html_files.append(fname)
                        elif fname.endswith('.css'):
                            target_path = os.path.join(static_dir, fname)
                            css_files.append(fname)
                        elif fname.endswith('.js'):
                            target_path = os.path.join(static_dir, fname)
                            js_files.append(fname)
                        else:
                            target_path = os.path.join(project_dir, fname)
                        
                        os.makedirs(os.path.dirname(target_path), exist_ok=True)
                        with open(target_path, "w", encoding="utf-8") as f:
                            f.write(content)
                    
                    bb.state.setdefault("frontend_files", []).extend(frontend_files.keys())
                    if html_files:
                        print(f"    ✅ HTML files: {', '.join(html_files)}")
                    if css_files:
                        print(f"    ✅ CSS files: {', '.join(css_files)}")
                    if js_files:
                        print(f"    ✅ JS files: {', '.join(js_files)}")
            except Exception as e:
                print(f"  ⚠️ Frontend generation failed: {e}")

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
    
    print(f"  🔗 L5 INTEGRATOR: Creating main.py with {len(bb.state['modules'])} module imports...")
    
    l5_attempts = 0
    l5_max_retries = 3
    l5_success = False
    main_code = ""

    while l5_attempts < l5_max_retries and not l5_success:
        l5_attempts += 1
        if l5_attempts > 1:
             print(f"    ⚠️ L5 Validation failed. Retrying ({l5_attempts}/{l5_max_retries})...")
             integrator_input += "\n\nIMPORTANT: Your previous output was rejected. You MUST output ONLY valid Python code. Do not summarize or explain."

        main_code = ask_agent("L5_INTEGRATOR", l5_sys, integrator_input,
                            blackboard=bb, agent_name="integrator", module_name="main")
        
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
             print(f"    ❌ Validation Error: {validation_error}")
             if l5_attempts >= l5_max_retries:
                  print("    ⚠️ L5 failed after max retries. Saving last attempt anyway.")
                  l5_success = True 
        else:
             print(f"    ✅ Validation passed! main.py created successfully")
             l5_success = True

    main_path = os.path.join(project_dir, "main.py")
    with open(main_path, "w", encoding="utf-8") as f:
        f.write(main_code)
    
    imports_count = main_code.count("import ")
    routes_count = main_code.count("@app.route") + main_code.count("@router.")
    print(f"    📊 main.py stats: {imports_count} imports, {routes_count} routes defined")

    phase3_duration = time.time() - phase3_start
    phase_times["Integration (L5)"] = phase3_duration
    print(f"✅ Integration complete. (⏱️ {phase3_duration:.1f}s)")
    
    # DEPENDENCIES
    manage_dependencies(project_dir)

    # PHASE 5: AUTO-DEBUG LOOP
    phase4_start = time.time()
    print("\n======================================================================")
    print("PHASE 5: L6 AUTO-DEBUG LOOP – TESTING & FIXING")
    print("======================================================================")
    l6_sys = AUTO_DEBUGGER_PROMPT
    for attempt in range(MAX_RETRIES):
        print(f"\n▶ Attempt {attempt+1}")
        print(f"  🧪 L6 DEBUGGER: Testing application...")
        
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

            print(f"    🔍 Analyzing error: {error_msg.split(chr(10))[0][:80]}...")
            
            context = ""
            for fname in bb.state["files_created"]:
                with open(os.path.join(project_dir, fname), "r") as f:
                    context += f"\n--- {fname} ---\n{f.read()}\n"
            debug_msg = f"ERROR:\n{error_msg}\n\nPROJECT FILES:\n{context}"
            print(f"    🧠 L6 DEBUGGER: Generating fix...")
            fix_raw = ask_agent("L6_DEBUGGER", l6_sys, debug_msg,
                              blackboard=bb, agent_name="debugger", module_name="debug")
            
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
                new_code = super_clean(new_code)
                
                target_path = os.path.join(project_dir, target_file)
                os.makedirs(os.path.dirname(target_path), exist_ok=True)
                with open(target_path, "w", encoding="utf-8") as f:
                    f.write(new_code)
                print(f"    ✅ Applied fix to {target_file}")
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

    # Always generate debug report (can disable with --no-debug if needed)
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
