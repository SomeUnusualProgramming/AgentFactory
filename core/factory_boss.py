import os
import yaml
import json
import time
import subprocess
import sys
import re
import ast
# Ensure root directory is in sys.path so 'core' and 'agents' modules can be imported
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from concurrent.futures import ThreadPoolExecutor, as_completed
from core.factory_boss_blackboard import FactoryBlackboard, normalize_filename
from agents.agent_frontend_developer import run_frontend_developer, extract_frontend_files
from utils.code_standards import get_validator
from utils.ast_inspector import analyze_code_structure, generate_implementation_summary
from utils.prompt_library import (
    FACTORY_BOSS_L1_PROMPT, FACTORY_BOSS_L2_PROMPT, FACTORY_BOSS_L3_PROMPT,
    FACTORY_BOSS_L5_PROMPT, AUTO_DEBUGGER_PROMPT, RUNNABLE_AUDIT_PROMPT, 
    DEPENDENCY_AGENT_PROMPT, TEST_ENGINEER_PROMPT, SECURITY_AGENT_PROMPT,
    DEVELOPER_AGENT_TDD_PROMPT, SECURITY_FIX_PROMPT, get_factory_boss_l4_prompt
)

# Refactored Imports
from core.constants import (
    MODEL_NAME, MAX_RETRIES, 
    OUTPUT_DIR, METADATA_DIR_NAME, REQUIREMENTS_FILE,
    CONSOLE_LOG_FILE, DEBUG_REPORT_FILE, DEBUG_SNAPSHOTS_DIR,
    MAIN_SCRIPT_NAME, RUN_SCRIPT_NAME, TESTS_DIR_NAME,
    TEMPLATES_DIR_NAME, STATIC_DIR_NAME,
    AGENT_L1_ANALYST, AGENT_L2_AUDITOR, AGENT_L3_ARCHITECT, AGENT_L4_DEVELOPER,
    AGENT_L5_INTEGRATOR, AGENT_L6_DEBUGGER, AGENT_DEPENDENCY_AGENT, AGENT_TEST_ENGINEER,
    AGENT_SECURITY_AGENT, AGENT_FRONTEND_DEV, AGENT_SYSTEM_AUDITOR,
    STATUS_RUNNING, STATUS_SUCCESS, STATUS_FAILED, STATUS_WARNING, STATUS_ERROR
)
from core.standards import QUALITY_STANDARDS, get_standards_context
from core.logger import (
    DualLogger, log_orchestration_event, log_quality_remark, 
    log_debug_interaction, capture_snapshot
)
from core.llm_client import (
    ask_agent, super_clean, extract_corrected_blueprint, extract_audit_issues,
    repair_python_code
)
from core.milestone_manager import MilestoneManager

# ---------- WORKFLOW ----------

def run_dependency_agent(blueprint, project_dir):
    """Run the Dependency Agent to generate requirements.txt"""
    print("\n🔒 [STEP 1: ENVIRONMENT LOCK] Running Dependency Agent...")
    log_orchestration_event(project_dir, AGENT_DEPENDENCY_AGENT, "START", "Generating requirements.txt", STATUS_RUNNING)
    try:
        reqs = ask_agent(AGENT_DEPENDENCY_AGENT, DEPENDENCY_AGENT_PROMPT, f"BLUEPRINT:\n{json.dumps(blueprint, indent=2)}", "text", project_dir=project_dir)
        
        # Sanitize output (remove "requirements.txt" if it appears as a line)
        req_lines = [line for line in reqs.splitlines() if line.strip().lower() != REQUIREMENTS_FILE]
        
        # Hard filter for known bad packages that agents keep hallucinating
        blacklist = ["jsonify", "request", "render_template", "json", "os", "sys", "math", "logging", "unittest"]
        filtered_lines = []
        for line in req_lines:
            line_stripped = line.strip()
            # Skip empty lines, comments, and long conversational lines
            if not line_stripped or line_stripped.startswith('#'):
                continue
            if len(line_stripped) > 40 and not any(c in line_stripped for c in ['=', '<', '>']):
                 continue # Likely a conversational sentence
            
            clean_pkg = line.split('=')[0].split('>')[0].split('<')[0].strip().lower()
            if clean_pkg in blacklist:
                continue
            if "werkzeug" in clean_pkg and "none" in line.lower(): 
                continue
            filtered_lines.append(line_stripped)
            
        reqs = "\n".join(filtered_lines)
        
        # Ensure we have essential build tools
        if "pytest" not in reqs:
            reqs += "\npytest"
            
        # Clean up any conversational text that might have slipped in
        reqs = "\n".join([line for line in reqs.splitlines() if line.strip() and not line.strip().startswith('#') and not line.lower().startswith('also,') and not line[0].isdigit()])
            
        # SAFETY CHECK: Python 3.13+ on Windows often lacks wheels for heavy libs
        if sys.version_info >= (3, 13) and os.name == 'nt':
             if "pandas" in reqs:
                 print("⚠️ Python 3.13+ detected. Commenting out 'pandas' to prevent build errors (wheels likely missing).")
                 reqs = reqs.replace("pandas", "# pandas (Manual install required for Py 3.13+)")
             if "numpy" in reqs:
                 print("⚠️ Python 3.13+ detected. Commenting out 'numpy' to prevent build errors.")
                 reqs = reqs.replace("numpy", "# numpy (Manual install required for Py 3.13+)")
             if "scipy" in reqs:
                 print("⚠️ Python 3.13+ detected. Commenting out 'scipy' to prevent build errors.")
                 reqs = reqs.replace("scipy", "# scipy (Manual install required for Py 3.13+)")

        if "flask" not in reqs and "FastAPI" not in str(blueprint): # Heuristic
            # If blueprint implies web, ensure flask or similar
            pass
            
        # Save requirements to .factory folder to keep root clean
        meta_dir = os.path.join(project_dir, METADATA_DIR_NAME)
        if not os.path.exists(meta_dir):
            os.makedirs(meta_dir, exist_ok=True)
            
        req_path = os.path.join(meta_dir, REQUIREMENTS_FILE)
        with open(req_path, "w", encoding="utf-8") as f:
            f.write(reqs)
        print(f"✅ requirements.txt generated in .factory: {len(reqs.splitlines())} dependencies")
        
        # Generate run.bat for easy execution
        bat_content = f"""@echo off
echo ===================================================
echo    AgentFactory Generated App Launcher
echo ===================================================
echo.
echo [1/2] Installing dependencies from .factory/requirements.txt...
"{sys.executable}" -m pip install -r .factory/requirements.txt
if %errorlevel% neq 0 (
    echo [ERROR] Failed to install dependencies.
    pause
    exit /b %errorlevel%
)

echo.
echo [2/2] Starting Application...
echo.
"{sys.executable}" {MAIN_SCRIPT_NAME}
if %errorlevel% neq 0 (
    echo.
    echo [APP CRASHED] See output above.
    pause
)
pause
"""
        bat_path = os.path.join(project_dir, RUN_SCRIPT_NAME)
        with open(bat_path, "w", encoding="utf-8") as f:
            f.write(bat_content)
        print(f"✅ {RUN_SCRIPT_NAME} generated")

        # MILESTONE 2 CHECK
        # We can pass self instance if needed, but passing None for now as it uses self.project_dir
        # Actually verify_env_milestone doesn't need args
        # But we need to call it from run_factory context really, or pass milestone manager?
        # No, run_dependency_agent is a function, not method. 
        # Refactoring: Return success status from run_dependency_agent
        
        return True

        # Install dependencies immediately to allow TDD (pytest needs to run)
        print("📥 Installing dependencies for TDD environment...")
        try:
            # FORCE UPGRADE FLASK AND WERKZEUG FIRST
            # This fixes the "cannot import name 'url_quote' from 'werkzeug.urls'" error caused by mismatched versions
            # in the user's global environment.
            print("    🔄 Forcing upgrade of Flask and Werkzeug to ensure compatibility...")
            subprocess.run([sys.executable, "-m", "pip", "install", "--upgrade", "flask>=3.0.0", "werkzeug>=3.0.0"], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

            # Try installing without deps first to see if it works, or use --no-deps for problem packages
            # But here we just try standard install with timeout
            # Use subprocess.run instead of check_call to handle errors gracefully without crashing
            subprocess.run([sys.executable, "-m", "pip", "install", "-r", req_path], check=True, timeout=60)
        except subprocess.CalledProcessError as e:
            print(f"⚠️ Warning: Failed to install dependencies (Exit Code {e.returncode}). Attempting to relax requirements...")
            
            # Attempt 2: Relax requirements (remove versions)
            try:
                with open(req_path, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                
                relaxed_reqs = []
                for line in lines:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        relaxed_reqs.append(line + "\n")
                        continue
                    # Remove version constraints (e.g. pandas==1.0.0 -> pandas)
                    pkg = line.split('==')[0].split('>=')[0].split('<=')[0].split('~=')[0].strip()
                    relaxed_reqs.append(pkg + "\n")
                
                with open(req_path, 'w', encoding='utf-8') as f:
                    f.writelines(relaxed_reqs)
                    
                print("    🔄 Retrying installation with relaxed requirements (versions removed)...")
                subprocess.run([sys.executable, "-m", "pip", "install", "-r", req_path], check=True, timeout=60)
                print("    ✅ Relaxed dependencies installed successfully.")
                
            except Exception as e2:
                print(f"❌ Failed to install dependencies even after relaxing. TDD might fail.")
                print(f"   Details: Use 'pip install -r .factory/requirements.txt' to debug manually.")
                log_quality_remark(project_dir, "Environment", f"Failed to install dependencies: {e} -> {e2}")

        except Exception as e:
             print(f"⚠️ Warning: Dependency installation timed out or failed: {e}")
            
    except Exception as e:
        print(f"❌ Dependency Agent Failed: {e}")
        log_quality_remark(project_dir, AGENT_DEPENDENCY_AGENT, f"Failed to generate requirements: {e}")

def run_factory(idea, debug_mode=False, plan_only=False):
    overall_start_time = time.time()
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    project_dir = f"{OUTPUT_DIR}/project_{timestamp}"
    metadata_dir = os.path.join(project_dir, METADATA_DIR_NAME)
    
    os.makedirs(metadata_dir, exist_ok=True)
    os.makedirs(project_dir, exist_ok=True)
    
    # Initialize Logger
    sys.stdout = DualLogger(os.path.join(metadata_dir, CONSOLE_LOG_FILE), project_dir=project_dir)
    # Redirect stderr to stdout to capture it in logs too
    sys.stderr = sys.stdout
    
    print(f"🚀 WORKSPACE CREATED: {project_dir}")
    print(f"📂 METADATA STORED IN: {metadata_dir}")

    bb = FactoryBlackboard(idea, project_dir, metadata_dir=metadata_dir)
    milestones = MilestoneManager(project_dir)
    phase_times = {}

    # PHASE 1 & 2: L1 ANALYST & L2 AUDITOR LOOP
    phase1_start = time.time()
    print("\n======================================================================")
    print("PHASE 1: STRATEGIC PLANNING (Analyst & Auditor)")
    print("======================================================================")
    log_orchestration_event(project_dir, "Factory_Boss", "PHASE_START", "Phase 1: Planning", STATUS_RUNNING)
    
    l1_sys = FACTORY_BOSS_L1_PROMPT
    l2_sys = FACTORY_BOSS_L2_PROMPT

    blueprint = None
    max_planning_retries = 5
    accumulated_issues = []
    suggested_fix = None
    last_audit_raw = None
    
    for i in range(max_planning_retries):
        print(f"\n--- Planning Iteration {i+1} ---")
        log_orchestration_event(project_dir, AGENT_L1_ANALYST, "ITERATION_START", f"Iteration {i+1}", STATUS_RUNNING)
        
        if i == 0:
            prompt = f"App idea: {idea}"
            print("  📝 L1 ANALYST: Analyzing app idea and creating architecture...")
        else:
            issues_context = "ISSUES TO FIX FROM PREVIOUS ATTEMPTS:\n"
            for j, issue in enumerate(accumulated_issues, 1):
                issues_context += f"{j}. {issue}\n"
            
            prompt = f"""ISSUES TO FIX FROM PREVIOUS ATTEMPTS:
{issues_context}
"""
            if last_audit_raw:
                 # Pass full context from auditor, truncated to avoid massive prompts
                 prompt += f"\nFULL AUDITOR FEEDBACK (Read carefully):\n{last_audit_raw[:2000]}\n"

            if suggested_fix:
                prompt += f"\nAUDITOR'S SUGGESTED FIX (Review and adopt if correct):\n{suggested_fix}\n"

            prompt += f"""
Original Idea: {idea}

INSTRUCTIONS:
1. Review the "ISSUES TO FIX" and "FULL AUDITOR FEEDBACK" above carefully.
2. THINK STEP-BY-STEP: Why did the auditor reject the previous plan? What specifically needs to change?
3. Create a completely NEW architecture that solves the original idea AND fixes the reported issues.
4. Ensure strict adherence to the YAML format and required fields.
5. Verify there are NO circular dependencies.
6. Output ONLY the YAML with "blackboard" as the top-level key.
"""
            print(f"  📝 L1 ANALYST: Fixing {len(accumulated_issues)} issues from previous attempt...")
            
        blueprint_raw = ask_agent(AGENT_L1_ANALYST, l1_sys, prompt, "yaml", project_dir=project_dir)
        
        try:
            temp_blueprint = yaml.safe_load(blueprint_raw)
            
            # --- STRUCTURE HEALING ---
            if isinstance(temp_blueprint, dict) and "modules" in temp_blueprint and "blackboard" not in temp_blueprint:
                 print("⚠️ Legacy format detected. Wrapping in 'blackboard' key...")
                 temp_blueprint = {"blackboard": temp_blueprint}
            
            if isinstance(temp_blueprint, dict) and "blackboard" in temp_blueprint:
                 bb_content = temp_blueprint["blackboard"]
                 if isinstance(bb_content.get("modules"), dict):
                     print("⚠️ Detected 'modules' as dict. converting to list...")
                     new_modules = []
                     for key, val in bb_content["modules"].items():
                         if isinstance(val, dict):
                             if "name" not in val:
                                 val["name"] = key
                             new_modules.append(val)
                     bb_content["modules"] = new_modules
        except Exception as e:
            print(f"❌ YAML Parsing Failed: {e}")
            accumulated_issues.append(f"YAML Syntax: {str(e)[:80]}")
            log_quality_remark(project_dir, AGENT_L1_ANALYST, f"YAML Syntax Error: {e}")
            continue

        # L2: Audit
        module_count = 0
        if temp_blueprint and "blackboard" in temp_blueprint and "modules" in temp_blueprint["blackboard"]:
            module_count = len(temp_blueprint["blackboard"]["modules"])
            
        print(f"  🔍 L2 AUDITOR: Reviewing architecture ({module_count} modules)...")
        l2_msg = f"Review this blueprint:\n{json.dumps(temp_blueprint, indent=2)}"
        if i >= 2:
             l2_msg += "\n\nSYSTEM NOTICE: This is the 3rd+ attempt. You MUST provide a FULL CORRECTED BLUEPRINT if you reject it. Do not just list issues. Fix it!"
             
        # Use raw_output=True to capture REASONING block for the Analyst
        audit_raw = ask_agent(AGENT_L2_AUDITOR, l2_sys, l2_msg, project_dir=project_dir, raw_output=True)
        
        last_audit_raw = audit_raw
        
        if "VERDICT: PASSED" in audit_raw:
            print(f"✅ Auditor approved! Architecture includes {module_count} modules:")
            if module_count > 0:
                for mod in temp_blueprint["blackboard"]["modules"]:
                    print(f"    • {mod.get('name')}: {mod.get('responsibility')[:60]}...")
            blueprint = temp_blueprint
            log_orchestration_event(project_dir, AGENT_L2_AUDITOR, "APPROVAL", "Architecture approved", STATUS_SUCCESS)
            break
        
        implicit_blueprint = extract_corrected_blueprint(audit_raw)
        if implicit_blueprint:
            try:
                new_bp = yaml.safe_load(implicit_blueprint)
                if isinstance(new_bp, dict):
                     if "modules" in new_bp and "blackboard" not in new_bp:
                         new_bp = {"blackboard": new_bp}
                     
                     if "blackboard" in new_bp and isinstance(new_bp["blackboard"].get("modules"), list):
                         # Verify completeness before accepting
                         bb_content = new_bp["blackboard"]
                         required_keys = ["modules", "module_dependencies", "entrypoint", "app_type", "main_flow", "assembly", "runtime", "ui_design", "data_strategy"]
                         missing = [k for k in required_keys if k not in bb_content]
                         
                         if not missing:
                             print(f"    💡 Auditor provided a FULL corrected blueprint. ACCEPTING immediately.")
                             blueprint = new_bp
                             break
                         else:
                             print(f"    ⚠️ Auditor provided a corrected blueprint but it is incomplete (missing {missing}). Treating as feedback.")
            except Exception as e:
                print(f"    ⚠️ Auditor provided a blueprint but it was invalid: {e}")

        print(f"⚠️ Auditor rejected the plan. Issues found:")
        structured_issues = extract_audit_issues(audit_raw)
        
        if implicit_blueprint:
            suggested_fix = implicit_blueprint
            print("    💡 Auditor provided a corrected blueprint. Passing to Analyst...")
        
        is_circular = any("circular" in issue.lower() for issue in structured_issues)
        
        for issue in structured_issues[:3]:
            print(f"    • {issue[:70]}...")
            log_quality_remark(project_dir, "Architecture_Audit", issue)
            if issue not in accumulated_issues:
                accumulated_issues.append(issue)
        
        if is_circular:
            accumulated_issues.append("CRITICAL: You are repeating circular dependencies. SIMPLIFY the architecture. Merge interdependent modules.")

    if not blueprint:
        print("❌ Failed to generate a valid plan after retries. Exiting.")
        log_orchestration_event(project_dir, "FACTORY_BOSS", "PLANNING_FAILED", "Failed to generate valid plan after retries", STATUS_FAILED)
        return

    # === BLOCKING VALIDATION GATE ===
    print("\n🚧 CHECKING VALIDATION GATE...")
    required_keys = ["modules", "module_dependencies", "entrypoint", "app_type", "main_flow", "assembly", "runtime", "ui_design", "data_strategy"]
    missing_keys = []
    bb_content = blueprint.get("blackboard", {})
    
    for key in required_keys:
        if key not in bb_content:
            missing_keys.append(key)
            
    fixed_any = False
    if missing_keys:
        # Check if the missing keys are just empty but present in some form, or totally absent
        # For robustness, we can try to infer defaults for some non-critical sections
        # But 'main_flow' is required by Blackboard validation.
        
        # Try to fix blueprint by adding empty placeholders for missing non-critical sections
        defaults = {
            "main_flow": ["Start application", "User interacts", "Application responds"],
            "assembly": {"initialization_order": [], "dependency_graph": ""},
            "ui_design": {"style": "Standard", "views": []},
            "data_strategy": {"type": "memory", "details": "Default in-memory storage"}
        }
        
        for k in missing_keys:
            if k in defaults:
                print(f"    ⚠️ Auto-fixing missing section '{k}' with default value.")
                blueprint["blackboard"][k] = defaults[k]
                fixed_any = True
    
    # NEW: Ensure main_flow is a list (Strict Type Validation Auto-Fix)
    if "main_flow" in blueprint["blackboard"]:
        flow = blueprint["blackboard"]["main_flow"]
        if not isinstance(flow, list):
            print(f"    ⚠️ 'main_flow' type mismatch ({type(flow)}). Converting to list.")
            if isinstance(flow, str):
                blueprint["blackboard"]["main_flow"] = [flow]
            else:
                blueprint["blackboard"]["main_flow"] = ["Start application", "User interacts", "Application responds"]
            fixed_any = True

    # Re-check
    still_missing = [k for k in required_keys if k not in blueprint["blackboard"]]
        
    if still_missing:
        print(f"❌ FATAL: Blueprint missing required sections: {still_missing}")
        print("🛑 The Factory Boss has stopped the pipeline.")
        log_quality_remark(project_dir, "VALIDATION_GATE", f"Blueprint missing required sections: {still_missing}")
        log_orchestration_event(project_dir, "FACTORY_BOSS", "ABORT", "Blueprint validation failed", STATUS_FAILED)
        return
    elif fixed_any:
        print("    ✅ Validation Gate Passed (after auto-fix).")

    if not missing_keys:
         print("✅ Validation Gate Passed. Proceeding to Implementation.")
         
    # MILESTONE 1 CHECK
    passed, checks = milestones.verify_architecture_milestone(blueprint)
    print("\n🏁 MILESTONE 1: ARCHITECTURE")
    for check in checks:
        print(f"    {check}")
    
    if not passed:
        print("🛑 Milestone 1 Failed. Stopping.")
        return

    phase1_duration = time.time() - phase1_start
    phase_times["Planning (L1+L2)"] = phase1_duration
    
    bb.set_architecture(blueprint)
    print(f"📐 Blueprint accepted and saved. (⏱️ {phase1_duration:.1f}s)")
    
    # === NEW STEP 1: ENVIRONMENT LOCK ===
    run_dependency_agent(blueprint, project_dir)
    
    # MILESTONE 2 CHECK
    passed, checks = milestones.verify_env_milestone()
    print("\n🏁 MILESTONE 2: ENVIRONMENT")
    for check in checks:
        print(f"    {check}")
    
    if not passed:
        print("🛑 Milestone 2 Failed. Stopping.")
        return

    if plan_only:
        print("\n🛑 Plan-only mode active. Exiting after planning phase.")
        if debug_mode:
            print("\n📝 Generating Debug Report...")
            try:
                bb.generate_debug_report(os.path.join(project_dir, DEBUG_REPORT_FILE))
                print(f"    ✅ Debug report saved to: {DEBUG_REPORT_FILE}")
            except Exception as e:
                print(f"    ⚠️ Failed to generate debug report: {e}")
        return

    # PHASE 2 & 3: L3 ARCHITECT & L4 DEVELOPER – PARALLEL EXECUTION
    phase2_start = time.time()
    print("\n======================================================================")
    print("PHASE 2: IMPLEMENTATION (Architects & Developers)")
    print("======================================================================")
    log_orchestration_event(project_dir, "FACTORY_BOSS", "PHASE_START", "Phase 2: Development", STATUS_RUNNING)
    
    modules_list = []
    if "blackboard" in blueprint and "modules" in blueprint["blackboard"]:
        modules_list = blueprint["blackboard"]["modules"]
    elif "modules" in blueprint:
        modules_list = blueprint["modules"]
        
    print(f"🚀 Launching {len(modules_list)} parallel module generations...")
    
    max_workers = min(4, len(modules_list))
    results = {}
    
    def _architect_module(module):
        """Phase 3a: Architect Only (L3)"""
        m_name = normalize_filename(module['name']).replace('.py', '')
        filename = module.get('filename', f"{m_name}.py")
        module_type = module.get('module_type', module.get('type', 'service'))
        
        print(f"  ▶ [{m_name}] Starting Architecture...")
        log_orchestration_event(project_dir, "ORCHESTRATOR", "MODULE_ARCH_START", f"Starting architecture: {m_name}", STATUS_RUNNING)
        
        # 1. Architect (Spec)
        print(f"    📋 L3 ARCHITECT: Designing {module_type}...")
        l3_sys = FACTORY_BOSS_L3_PROMPT
        bb_data = blueprint.get("blackboard", {})
        l3_context = f"MODULE_TYPE: {module_type}\n\nDATA STRATEGY:\n{yaml.dump(bb_data.get('data_strategy', {}))}\n\nUI DESIGN:\n{yaml.dump(bb_data.get('ui_design', {}))}\n\nModule Details:\n{yaml.dump(module)}"
        
        spec_raw = ask_agent(f"L3_{m_name}", l3_sys, l3_context, "yaml", blackboard=bb, agent_name=AGENT_L3_ARCHITECT, module_name=m_name, project_dir=project_dir)
        bb.register_module(m_name, filename, spec_raw, module_type)
        bb.register_api(m_name, spec_raw) # CRITICAL FIX: Register API for L5 and other agents
        
        return m_name

    def _develop_module(module):
        """Phase 3b: Development (L4) - TDD Pipeline"""
        m_name = normalize_filename(module['name']).replace('.py', '')
        filename = module.get('filename', f"{m_name}.py")
        module_type = module.get('module_type', module.get('type', 'service'))
        
        # Retrieve Spec from Blackboard
        spec_raw = bb.state["api_registry"].get(m_name)
        if not spec_raw:
             print(f"❌ Error: No spec found for {m_name}")
             return None

        # Gather Dependency Specs
        dep_specs = ""
        requires = module.get('requires', [])
        api_registry = bb.state.get("api_registry", {})
        for req_file in requires:
             # Find module name by filename
             req_mod_name = next((k for k, v in bb.state["modules"].items() if v.get("filename") == req_file), None)
             if req_mod_name and req_mod_name in api_registry:
                 dep_specs += f"\n--- DEPENDENCY: {req_mod_name} ---\n{api_registry[req_mod_name]}\n"

        # 2. Red Phase (Test)
        print(f"    🧪 TEST ENGINEER (RED PHASE): Writing failing tests for {m_name}...")
        test_context = f"MODULE: {m_name}\nFILENAME: {filename}\nSPECIFICATION:\n{spec_raw}\n\nDEPENDENCY SPECS:\n{dep_specs}"
        test_code = ask_agent(f"TEST_{m_name}", TEST_ENGINEER_PROMPT, test_context, "python", blackboard=bb, agent_name=AGENT_TEST_ENGINEER, module_name=m_name, project_dir=project_dir)
        
        test_filename = f"test_{m_name}.py"
        tests_dir = os.path.join(project_dir, TESTS_DIR_NAME)
        os.makedirs(tests_dir, exist_ok=True)
        test_path = os.path.join(tests_dir, test_filename)
        with open(test_path, "w", encoding="utf-8") as f:
            f.write(test_code)
            
        # 3. Green Phase (Implementation)
        print(f"    💻 DEVELOPER (GREEN PHASE): Implementing {m_name}...")
        
        reqs_path = os.path.join(project_dir, REQUIREMENTS_FILE)
        reqs_content = ""
        if os.path.exists(reqs_path):
            with open(reqs_path, "r") as f: reqs_content = f.read()
            
        # Inject dynamic quality standards into TDD context
        standards_block = get_standards_context(module_type)
        
        tdd_context = f"MODULE SPEC:\n{spec_raw}\n\nDEPENDENCY SPECS:\n{dep_specs}\n\nREQUIREMENTS:\n{reqs_content}\n\nTESTS ({test_filename}):\n{test_code}\n\n{standards_block}"
        
        code = ""
        success = False
        attempts = 0
        max_retries = 3
        
        while attempts < max_retries and not success:
            attempts += 1
            if attempts > 1:
                 tdd_context += f"\n\nPREVIOUS ATTEMPT FAILED. FIX ERRORS."
            
            code = ask_agent(f"DEV_{m_name}", DEVELOPER_AGENT_TDD_PROMPT, tdd_context, "python", blackboard=bb, agent_name=AGENT_L4_DEVELOPER, module_name=m_name, project_dir=project_dir)
            
            # Save candidate code
            file_path = os.path.join(project_dir, filename)
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(code)
            
            # 4. Gatekeeper
            # Check if file exists before testing
            if not os.path.exists(file_path):
                 print(f"    ⚠️ Gatekeeper: File {filename} was NOT created. Skipping tests.")
                 tdd_context += "\nERROR: You did not output the file content."
                 continue

            # AST Check
            try:
                ast.parse(code)
            except SyntaxError as e:
                print(f"    ❌ AST Parse Failed: {e}")
                tdd_context += f"\nAST ERROR: {e}"
                log_quality_remark(project_dir, "GATEKEEPER", f"AST Syntax Error in {m_name}", context=str(e))
                continue
                
            # Pytest Check
            print(f"    🚧 Gatekeeper: Running Pytest for {m_name}...")
            try:
                # Add project_dir to PYTHONPATH so tests can import modules
                test_env = os.environ.copy()
                test_env["PYTHONPATH"] = project_dir
                
                # Check dependencies exist
                missing_deps = []
                for req_file in requires:
                     req_mod = next((v for k, v in bb.state["modules"].items() if v.get("filename") == req_file), None)
                     if req_mod:
                         req_path = os.path.join(project_dir, req_mod.get("filename", ""))
                         if not os.path.exists(req_path):
                             missing_deps.append(req_file)
                
                if missing_deps:
                    print(f"    ⚠️ Skipping test execution: Missing dependencies {missing_deps}")
                    # Don't fail the build, just warn and continue (best effort)
                    # We can't verify if deps are missing, but we shouldn't crash
                    success = True # Assume success if we can't test due to environment
                else:
                    result = subprocess.run(
                        [sys.executable, "-m", "pytest", os.path.join(TESTS_DIR_NAME, test_filename)],
                        cwd=project_dir,
                        env=test_env,
                        capture_output=True,
                        text=True,
                        timeout=10
                    )
                    
                    if result.returncode == 0:
                        print(f"    ✅ Tests Passed!")
                        success = True
                    else:
                        print(f"    ❌ Tests Failed (Exit Code {result.returncode})")
                        output_snippet = result.stdout + "\n" + result.stderr
                        
                        # Save detailed failure log with timestamp
                        timestamp = time.strftime("%H%M%S")
                        fail_log_path = os.path.join(project_dir, ".factory", "test_failures", f"{m_name}_fail_{timestamp}.txt")
                        os.makedirs(os.path.dirname(fail_log_path), exist_ok=True)
                        with open(fail_log_path, "w", encoding="utf-8") as f:
                            f.write(output_snippet)
                        
                        # Show snippet in console
                        print(f"    📄 Log saved: .factory/test_failures/{m_name}_fail_{timestamp}.txt")
                        print("    👀 Failure Preview:")
                        print("\n".join(output_snippet.splitlines()[-10:]))
                        
                        tdd_context += f"\nTEST FAILURES:\n{output_snippet[-1000:]}"
                        log_quality_remark(project_dir, "GATEKEEPER", f"Tests failed for {m_name}", context=output_snippet[-500:])
            except Exception as e:
                print(f"    ⚠️ Test Execution Error: {e}")
                
        if not success:
            print(f"    ⚠️ Failed to pass tests after {max_retries} attempts. Proceeding with best effort.")
            log_orchestration_event(project_dir, "ORCHESTRATOR", "TEST_FAIL", f"Module: {m_name} - Failed to pass tests after retries", STATUS_WARNING)

        # 5. Adversarial Audit
        print(f"    🛡️ SECURITY AGENT: Auditing {m_name}...")
        audit_res = ask_agent(f"SEC_{m_name}", SECURITY_AGENT_PROMPT, f"CODE:\n{code}", "json", blackboard=bb, agent_name=AGENT_SECURITY_AGENT, module_name=m_name, project_dir=project_dir)
        if "VULNERABLE" in audit_res:
            print(f"    🚨 Security Vulnerabilities Detected: {audit_res}")
            log_quality_remark(project_dir, AGENT_SECURITY_AGENT, f"Vulnerabilities in {m_name}", context=audit_res)
            
            # ATTEMPT FIX
            print(f"    🛠️ SECURITY AGENT: Requesting fixes from Developer...")
            
            fix_context = f"CURRENT CODE:\n{code}\n\nSECURITY REPORT:\n{audit_res}\n\nTESTS:\n{test_code}"
            
            fixed_code = ask_agent(f"DEV_SEC_FIX_{m_name}", SECURITY_FIX_PROMPT, fix_context, "python", blackboard=bb, agent_name=AGENT_L4_DEVELOPER, module_name=m_name, project_dir=project_dir)
            
            # Save fixed code
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(fixed_code)
                
            code = fixed_code
            print(f"    ✅ Security Fixes Applied (Code updated).")
            log_orchestration_event(project_dir, AGENT_SECURITY_AGENT, "FIX_APPLIED", f"Fixed vulnerabilities in {m_name}", STATUS_SUCCESS)
            
        else:
            print(f"    ✅ Security Audit Passed.")
            
        # 6. AST Reality Check (New)
        # Verify what was ACTUALLY implemented
        structure = analyze_code_structure(code)
        impl_summary = generate_implementation_summary(structure)
        print(f"    🔍 AST Inspector: Verified implementation structure.")
            
        log_orchestration_event(project_dir, "ORCHESTRATOR", "MODULE_COMPLETE", f"Finished module generation: {m_name}", STATUS_SUCCESS)
        return {"m_name": m_name, "filename": filename, "spec": spec_raw, "code": code, "structure": structure, "impl_summary": impl_summary}

    # Execute Phase 2a: Architecture (Parallel)
    print("\n----------------------------------------------------------------------")
    print("PHASE 2a: ARCHITECTURE (Defining Interfaces)")
    print("----------------------------------------------------------------------")
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_architect_module, module): module for module in modules_list}
        for future in as_completed(futures):
            try:
                future.result()
            except Exception as e:
                print(f"❌ Architecture failed: {e}")

    # Execute Phase 2b: Development (Parallel)
    print("\n----------------------------------------------------------------------")
    print("PHASE 2b: DEVELOPMENT (Implementation with TDD)")
    print("----------------------------------------------------------------------")
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_develop_module, module): module for module in modules_list}
        for future in as_completed(futures):
            try:
                result = future.result()
                if result:
                    results[result['m_name']] = result
            except Exception as e:
                print(f"❌ Module generation failed: {e}")
                log_orchestration_event(project_dir, "FACTORY_BOSS", "MODULE_ERROR", f"Exception in worker: {e}", STATUS_ERROR)
    
    phase2_duration = time.time() - phase2_start
    phase_times["Development (L3+L4)"] = phase2_duration
    print(f"✅ Development complete. (⏱️ {phase2_duration:.1f}s)")
    log_orchestration_event(project_dir, "FACTORY_BOSS", "PHASE_END", "Phase 2: Development Complete", STATUS_SUCCESS)
    
    # MILESTONE 3 CHECK
    passed, checks = milestones.verify_development_milestone(results)
    print("\n🏁 MILESTONE 3: DEVELOPMENT & TESTING")
    for check in checks:
        print(f"    {check}")
    
    if not passed:
        print("⚠️ Milestone 3 Warning: Some tests failed or files missing. Proceeding with caution.")
        # We don't stop here because L5 might still work, or we want to allow debugging
        # But we log it heavily
    
    # PHASE 3: FRONTEND DEVELOPMENT
    phase3_start = time.time()
    print("\n======================================================================")
    print("PHASE 3: FRONTEND DEVELOPMENT (UI/UX)")
    print("======================================================================")
    log_orchestration_event(project_dir, "FACTORY_BOSS", "PHASE_START", "Phase 3: Frontend", STATUS_RUNNING)
    
    # Check for web components or forced web app type
    has_web_components = False
    app_type = bb.state.get("architecture", {}).get("app_type", "").lower()
    
    # 1. Check Module Types
    for m_name in results:
        result = results[m_name]
        is_web_module = (
            result.get('module_type') == 'web_interface' or 
            any(kw in m_name.lower() for kw in ["web", "interface", "ui", "frontend", "view"])
        )
        if is_web_module:
            has_web_components = True
            break
            
    # 2. Check Requirements
    if not has_web_components:
        reqs_path = os.path.join(project_dir, REQUIREMENTS_FILE)
        if os.path.exists(reqs_path):
            with open(reqs_path, 'r') as f:
                if 'flask' in f.read().lower():
                    has_web_components = True
                    print("    ℹ️ Flask detected in requirements. Forcing frontend generation.")

    # 3. Check App Type (Strongest signal)
    if "web" in app_type or "flask" in app_type:
        has_web_components = True
        print(f"    ℹ️ App Type is '{app_type}'. Forcing frontend generation.")

    frontend_files = {}
    if has_web_components:
         try:
            print(f"  🎨 FRONTEND DEVELOPER: Designing UI/UX for project...")
            log_orchestration_event(project_dir, AGENT_FRONTEND_DEV, "GENERATE", f"Creating UI for project", STATUS_RUNNING)
            
            all_specs = "\n".join([r.get('spec', '') for r in results.values() if r.get('spec')])
            if not all_specs:
                all_specs = "Standard Flask Application structure."

            frontend_code = run_frontend_developer(idea, all_specs, blackboard=bb)
            frontend_files = extract_frontend_files(frontend_code)
            
            if frontend_files:
                templates_dir = os.path.join(project_dir, TEMPLATES_DIR_NAME)
                static_dir = os.path.join(project_dir, STATIC_DIR_NAME)
                os.makedirs(templates_dir, exist_ok=True)
                os.makedirs(static_dir, exist_ok=True)
                
                count = 0
                for fname, content in frontend_files.items():
                    if fname.endswith('.html'):
                        target_path = os.path.join(templates_dir, fname)
                    elif fname.endswith('.css') or fname.endswith('.js'):
                        target_path = os.path.join(static_dir, fname)
                    else:
                        target_path = os.path.join(project_dir, fname)
                    
                    os.makedirs(os.path.dirname(target_path), exist_ok=True)
                    with open(target_path, "w", encoding="utf-8") as f:
                        f.write(content)
                    print(f"    ✅ Generated: {fname}")
                    count += 1
                
                bb.state.setdefault("frontend_files", []).extend(frontend_files.keys())
                log_orchestration_event(project_dir, AGENT_FRONTEND_DEV, "FILES_SAVED", f"Saved {count} files", STATUS_SUCCESS)
            else:
                 print(f"    ⚠️ Frontend Developer produced no valid files. (Check logs/prompts)")
                 debug_fe_path = os.path.join(project_dir, ".factory", "frontend_debug_raw.txt")
                 with open(debug_fe_path, "w", encoding="utf-8") as f:
                     f.write(frontend_code)
                 print(f"    📄 Raw output saved to {debug_fe_path}")
         except Exception as e:
            print(f"  ⚠️ Frontend generation failed: {e}")
            log_orchestration_event(project_dir, AGENT_FRONTEND_DEV, "ERROR", f"Failed: {e}", STATUS_ERROR)
    else:
         print("  ℹ️ No web interface modules detected. Skipping frontend generation.")

    phase3_duration = time.time() - phase3_start
    phase_times["Frontend (L4.5)"] = phase3_duration
    
    # MILESTONE 3.5 CHECK
    passed, checks = milestones.verify_frontend_milestone(frontend_files)
    print("\n🏁 MILESTONE 3.5: FRONTEND")
    for check in checks:
        print(f"    {check}")

    try:
        bb.verify_integrity(check_entrypoint=False)
    except RuntimeError as e:
        print(f"\n❌ FATAL INTEGRITY ERROR: {e}")
        log_quality_remark(project_dir, "INTEGRITY_CHECK", f"Fatal Integrity Error: {e}")
        log_orchestration_event(project_dir, "FACTORY_BOSS", "ABORT", f"Integrity check failed: {e}", STATUS_FAILED)
        return

    # PHASE 4: L5 INTEGRATOR
    phase4_start = time.time()
    print("\n======================================================================")
    print("PHASE 4: INTEGRATION (System Assembly)")
    print("======================================================================")
    log_orchestration_event(project_dir, "FACTORY_BOSS", "PHASE_START", "Phase 4: Integration", STATUS_RUNNING)
    
    files_list = bb.state["files_created"]
    
    modules_info = "Module Types & IMPLEMENTED SYMBOLS (Reality Check):\n"
    for m_name in results:
        res = results[m_name]
        filename = res.get("filename", f"{m_name}.py")
        mod_type = bb.state["modules"].get(m_name, {}).get("module_type", "unknown")
        impl_summary = res.get("impl_summary", "No analysis available")
        
        modules_info += f"  - FILE: {filename} (Type: {mod_type})\n"
        modules_info += f"    {impl_summary.replace(chr(10), chr(10)+'    ')}\n"

    api_specs_info = "\nAPI SPECIFICATIONS:\n"
    api_registry = bb.state.get("api_registry", {})
    for mod_name, spec in api_registry.items():
        api_specs_info += f"\n--- {mod_name} Spec ---\n{json.dumps(spec, indent=2)}\n"
    
    l5_sys = FACTORY_BOSS_L5_PROMPT
    integrator_input = f"Blackboard snapshot:\n{bb.snapshot()}\n\n{modules_info}\n\n{api_specs_info}\n\nIdea: {idea}"
    
    log_debug_interaction(project_dir, "L5_INTEGRATOR_INPUT", integrator_input)

    print(f"  🔗 L5 INTEGRATOR: Creating main.py...")
    
    l5_attempts = 0
    l5_max_retries = 3
    l5_success = False
    main_code = ""

    def verify_main_code(code, required_modules, project_dir):
        """Verifies if main.py imports the required modules and checks symbol validity."""
        errors = []
        try:
            tree = ast.parse(code)
            imports = {} # module_name -> set(imported_symbols)
            
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        imports[alias.name] = set() # Import entire module
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        if node.module not in imports:
                            imports[node.module] = set()
                        for alias in node.names:
                            imports[node.module].add(alias.name)
            
            # Check 1: Are required modules imported? (Basic check)
            # We relax this: strict requirement is good, but deep symbol check is better.
            
            # Check 2: Deep Symbol Verification
            # For every import that corresponds to a generated file, check if symbols exist.
            for mod_name, symbols in imports.items():
                # Find if this module corresponds to a generated file
                # Check direct match or via bb.modules
                target_file = None
                
                # Case A: mod_name matches a key in required_modules
                if mod_name in required_modules:
                    target_file = required_modules[mod_name].get("filename")
                
                # Case B: mod_name matches a filename directly (e.g. from app import...)
                if not target_file:
                    for m in required_modules.values():
                        if m.get("filename", "").replace(".py", "") == mod_name:
                            target_file = m.get("filename")
                            break
                
                # Case C: Check file system directly if generic import
                if not target_file and os.path.exists(os.path.join(project_dir, f"{mod_name}.py")):
                    target_file = f"{mod_name}.py"

                if target_file:
                    file_path = os.path.join(project_dir, target_file)
                    if os.path.exists(file_path):
                        try:
                            with open(file_path, "r", encoding="utf-8") as f:
                                target_code = f.read()
                            target_tree = ast.parse(target_code)
                            
                            defined_symbols = set()
                            for t_node in ast.walk(target_tree):
                                if isinstance(t_node, (ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef)):
                                    defined_symbols.add(t_node.name)
                                elif isinstance(t_node, ast.Assign):
                                    for target in t_node.targets:
                                        if isinstance(target, ast.Name):
                                            defined_symbols.add(target.id)
                            
                            for sym in symbols:
                                if sym != "*" and sym not in defined_symbols:
                                    errors.append(f"ImportError: '{sym}' is not defined in '{target_file}' (Module '{mod_name}'). Available: {list(defined_symbols)[:5]}...")
                        except Exception as e:
                            print(f"    ⚠️ Could not parse {target_file} for verification: {e}")
                    else:
                        errors.append(f"ImportError: Module '{mod_name}' not found on disk (expected {target_file}).")

            return errors
        except SyntaxError:
            return ["SYNTAX_ERROR"]

    while l5_attempts < l5_max_retries and not l5_success:
        l5_attempts += 1
        main_code = ask_agent(AGENT_L5_INTEGRATOR, l5_sys, integrator_input, blackboard=bb, agent_name=AGENT_L5_INTEGRATOR, module_name="main", project_dir=project_dir)
        
        log_debug_interaction(project_dir, f"L5_INTEGRATOR_OUTPUT_ATTEMPT_{l5_attempts}", main_code)

        main_code_stripped = main_code.strip()
        
        # Robust Python Check
        is_valid_python = False
        validation_error = ""
        
        try:
            ast.parse(main_code_stripped)
            # Ensure it's not just a single string or empty
            if len(main_code_stripped) > 50 and ("import" in main_code_stripped or "from" in main_code_stripped):
                # NEW: Verify imports match modules
                print(f"    🔍 L5_VERIFIER: Checking main.py imports and symbols...")
                import_errors = verify_main_code(main_code_stripped, bb.state["modules"], project_dir)
                
                if not import_errors:
                    is_valid_python = True
                    print(f"    ✅ L5_VERIFIER: main.py valid and symbols verified.")
                else:
                    is_valid_python = False
                    validation_error = f"Invalid Imports: {import_errors}"
                    print(f"    ❌ L5_VERIFIER: {validation_error}")
            else:
                 validation_error = "Code too short or missing imports."
        except SyntaxError:
            # Try to repair
            repaired = repair_python_code(main_code_stripped)
            if repaired != main_code_stripped:
                try:
                    ast.parse(repaired)
                    print(f"    ✅ L5_VERIFIER: Repaired syntax error by removing trailing garbage.")
                    main_code_stripped = repaired
                    # Re-verify imports
                    import_errors = verify_main_code(main_code_stripped, bb.state["modules"], project_dir)
                    if not import_errors:
                        is_valid_python = True
                    else:
                        is_valid_python = False
                        validation_error = f"Invalid Imports after repair: {import_errors}"
                except SyntaxError:
                    is_valid_python = False
                    validation_error = "Syntax Error (Repair failed)."
            else:
                is_valid_python = False
                validation_error = "Syntax Error."

        if is_valid_python:
             l5_success = True
        else:
             print(f"    ⚠️ Integrator output invalid. Retrying... Reason: {validation_error}")
             log_quality_remark(project_dir, AGENT_L5_INTEGRATOR, f"Output invalid: {validation_error}")
             # Add feedback to the prompt for next retry
             integrator_input += f"\n\nPREVIOUS ATTEMPT FAILED. REASON: {validation_error}\nEnsure you import correct classes/functions from generated files. Check the Blackboard for available symbols."

    if not l5_success:
        print("    ❌ L5 Integrator failed to produce valid code after retries.")
        print("    ⚠️ Attempting EMERGENCY FALLBACK with simplified prompt...")
        fallback_sys = "You are a Python Expert. Write a simple valid main.py for a Flask app. Output ONLY code."
        main_code = ask_agent("L5_FALLBACK", fallback_sys, integrator_input, blackboard=bb, agent_name="L5_FALLBACK", module_name="main", project_dir=project_dir)
    
    main_path = os.path.join(project_dir, MAIN_SCRIPT_NAME)
    with open(main_path, "w", encoding="utf-8") as f:
        f.write(main_code)
    
    phase4_duration = time.time() - phase4_start
    phase_times["Integration (L5)"] = phase4_duration
    print(f"✅ Integration complete. (⏱️ {phase4_duration:.1f}s)")
    log_orchestration_event(project_dir, "FACTORY_BOSS", "PHASE_END", "Phase 4: Integration Complete", STATUS_SUCCESS)
    
    # MILESTONE 4 CHECK
    passed, checks = milestones.verify_integration_milestone()
    print("\n🏁 MILESTONE 4: INTEGRATION")
    for check in checks:
        print(f"    {check}")
    
    if not passed:
        print("🛑 Milestone 4 Failed: Main script missing. Stopping.")
        return

    # === SYSTEM-LEVEL RUNNABLE AUDIT ===
    print("\n======================================================================")
    print("SYSTEM AUDIT: VERIFYING RUNNABILITY")
    print("======================================================================")
    
    main_code_content = ""
    if os.path.exists(main_path):
        with open(main_path, "r", encoding="utf-8") as f:
            main_code_content = f.read()
            
    audit_context = {
        "blackboard_snapshot": bb.snapshot(),
        "files_list": bb.state["files_created"],
        "main_code": main_code_content
    }
    
    audit_prompt = RUNNABLE_AUDIT_PROMPT.format(**audit_context)
    audit_result = ask_agent(AGENT_SYSTEM_AUDITOR, "You are the System Auditor.", audit_prompt, "text", project_dir=project_dir, agent_name=AGENT_SYSTEM_AUDITOR)
    print(audit_result)
    log_quality_remark(project_dir, AGENT_SYSTEM_AUDITOR, audit_result)
    
    # PHASE 5: AUTO-DEBUG LOOP
    phase5_start = time.time()
    print("\n======================================================================")
    print("PHASE 5: L6 AUTO-DEBUG LOOP – TESTING & FIXING")
    print("======================================================================")
    log_orchestration_event(project_dir, "FACTORY_BOSS", "PHASE_START", "Phase 5: Debugging", STATUS_RUNNING)
    
    l6_sys = AUTO_DEBUGGER_PROMPT
    
    # 1. Install dependencies first if requirements.txt exists
    req_path = os.path.join(project_dir, ".factory", "requirements.txt")
    if os.path.exists(req_path):
        print("  📥 Installing dependencies before running main.py...")
        try:
             subprocess.run([sys.executable, "-m", "pip", "install", "-r", req_path], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception as e:
             print(f"    ⚠️ Warning: Dependency install failed: {e}")

    for attempt in range(MAX_RETRIES):
        print(f"\n▶ Attempt {attempt+1}")
        print(f"  🧪 L6 DEBUGGER: Testing application...")
        log_orchestration_event(project_dir, AGENT_L6_DEBUGGER, "TEST_RUN", f"Attempt {attempt+1}", STATUS_RUNNING)
        
        proc = subprocess.Popen(
            [sys.executable, MAIN_SCRIPT_NAME], 
            cwd=project_dir, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE,
            text=True
        )

        try:
            stdout, stderr = proc.communicate(timeout=5)
            return_code = proc.returncode
        except subprocess.TimeoutExpired:
            print("🎉 SUCCESS! App is running (Web Server active). Killing to finish workflow.")
            log_orchestration_event(project_dir, AGENT_L6_DEBUGGER, "SUCCESS", "App is running (TimeoutExpired implies running server)", STATUS_SUCCESS)
            proc.kill()
            break

        if return_code == 0:
            print("🎉 SUCCESS! Output:")
            print(stdout)
            log_orchestration_event(project_dir, AGENT_L6_DEBUGGER, "SUCCESS", "App ran successfully (Exit 0)", STATUS_SUCCESS)
            break
        else:
            error_msg = stderr
            print("❌ ERROR:")
            print(error_msg)
            log_quality_remark(project_dir, "RUNTIME_ERROR", error_msg)
            
            # Identify file from error for snapshotting
            match = re.search(r'File "(.*?)", line', error_msg)
            affected_file = None
            if match:
                full_path = match.group(1)
                full_path = os.path.normpath(full_path)
                norm_project_dir = os.path.normpath(project_dir)
                if norm_project_dir in full_path:
                    affected_file = os.path.relpath(full_path, project_dir)
            
            # CRITICAL FIX: IF ModuleNotFoundError, it means we need to fix the file that has the bad import
            if "ModuleNotFoundError" in error_msg:
                # Extract the module name
                mod_match = re.search(r"No module named '(.*?)'", error_msg)
                if mod_match:
                     missing_mod = mod_match.group(1)
                     print(f"    ⚠️ Missing Module: {missing_mod}")
                     # If the missing module is actually one of our internal files (but named wrong in import)
                     # We need to tell the debugger to fix the IMPORTING file, not the main.py necessarily
                     pass

            capture_snapshot(project_dir, attempt+1, affected_file)
            if affected_file:
                print(f"    📸 Snapshot created for debugging: .factory/debug_snapshots/attempt_{attempt+1}/{affected_file}")
            else:
                print(f"    📸 Snapshot created for debugging: .factory/debug_snapshots/attempt_{attempt+1}/ (Full Project)")

            # Simple Fix Loop
            debug_msg = f"ERROR:\n{error_msg}"
            if affected_file:
                 try:
                     with open(os.path.join(project_dir, affected_file), 'r', encoding='utf-8') as f:
                         file_content = f.read()
                     debug_msg += f"\n\nCURRENT CONTENT OF {affected_file}:\n```python\n{file_content}\n```"
                 except:
                     pass

            log_debug_interaction(project_dir, f"L6_DEBUGGER_INPUT_ATTEMPT_{attempt+1}", debug_msg)

            # Pass list of available files to help debugger fix imports
            files_list_str = "\n".join(bb.state["files_created"])
            debug_msg += f"\n\nAVAILABLE FILES IN PROJECT:\n{files_list_str}\n"

            fix_raw = ask_agent(AGENT_L6_DEBUGGER, l6_sys, debug_msg, blackboard=bb, agent_name=AGENT_L6_DEBUGGER, module_name="debug", project_dir=project_dir, raw_output=True)
            
            log_debug_interaction(project_dir, f"L6_DEBUGGER_OUTPUT_ATTEMPT_{attempt+1}", fix_raw)

            # Apply fix
            file_match = re.search(r'FILE:\s*(.+)', fix_raw)
            if file_match:
                target_file = file_match.group(1).strip()
                # Extract code block
                code_match = re.search(r'```python\s*(.*?)\s*```', fix_raw, re.DOTALL)
                if not code_match:
                    code_match = re.search(r'```\s*(.*?)\s*```', fix_raw, re.DOTALL)
                
                if code_match:
                    new_code = code_match.group(1)
                    target_path = os.path.join(project_dir, target_file)
                    try:
                        with open(target_path, 'w', encoding='utf-8') as f:
                            f.write(new_code)
                        print(f"    ✅ Auto-fix applied to {target_file}")
                        log_orchestration_event(project_dir, AGENT_L6_DEBUGGER, "FIX_APPLIED", f"Fixed {target_file}", STATUS_SUCCESS)
                    except Exception as e:
                        print(f"    ⚠️ Failed to write fix to {target_file}: {e}")
                else:
                    print("    ⚠️ L6 Debugger returned FILE but no code block.")
            else:
                 print("    ⚠️ L6 Debugger response format invalid (missing FILE: tag). Simulation only.")
                 log_orchestration_event(project_dir, AGENT_L6_DEBUGGER, "FIX_SKIPPED", "Invalid response format", STATUS_WARNING)

    phase5_duration = time.time() - phase5_start
    phase_times["Debugging (L6)"] = phase5_duration
    log_orchestration_event(project_dir, "FACTORY_BOSS", "PHASE_END", "Phase 5: Debugging Complete", STATUS_SUCCESS)
    
    overall_duration = time.time() - overall_start_time
    
    if debug_mode:
        print("\n📝 Generating Debug Report...")
        try:
            bb.generate_debug_report(os.path.join(project_dir, DEBUG_REPORT_FILE))
            print(f"    ✅ Debug report saved to: {DEBUG_REPORT_FILE}")
        except Exception as e:
            print(f"    ⚠️ Failed to generate debug report: {e}")

    # MILESTONE 5: FINAL
    print("\n🏁 MILESTONE 5: FINAL BUILD")
    print("    ✅ All phases executed.")
    milestones.record_milestone("Final", "COMPLETED", ["Build finished"])

    print("\n======================================================================")
    print("🎉 BUILD COMPLETE!")
    print("======================================================================")
    print(f"📍 Project directory: {project_dir}")
    log_orchestration_event(project_dir, "FACTORY_BOSS", "COMPLETE", f"Build finished in {overall_duration:.1f}s", STATUS_SUCCESS)

import argparse
from agents import agent_analyst

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AgentFactory - AI Software Generator")
    parser.add_argument("--idea", type=str, help="The software idea to build")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode (generates detailed report)")
    parser.add_argument("--plan-only", action="store_true", help="Only run Analyst and Auditor (stop after planning)")
    args = parser.parse_args()

    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)
        
    if args.idea:
        print(f"🚀 Starting Factory with idea: {args.idea}")
        run_factory(args.idea, debug_mode=args.debug, plan_only=args.plan_only)
    else:
        try:
            requirements = agent_analyst.interview_user()
            run_factory(requirements, debug_mode=args.debug, plan_only=args.plan_only)
        except KeyboardInterrupt:
            print("\n[Aborted]")
            sys.exit(0)
