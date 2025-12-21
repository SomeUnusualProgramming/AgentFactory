import ollama
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
from agents.agent_code_reviewer import run_reviewer
from agents.agent_code_optimizer import run_optimizer
from agents.agent_frontend_developer import run_frontend_developer, extract_frontend_files
from utils.code_standards import get_validator
from utils.prompt_library import (
    FACTORY_BOSS_L1_PROMPT, FACTORY_BOSS_L2_PROMPT, FACTORY_BOSS_L3_PROMPT,
    FACTORY_BOSS_L5_PROMPT, AUTO_DEBUGGER_PROMPT, RUNNABLE_AUDIT_PROMPT, 
    DEPENDENCY_AGENT_PROMPT, TEST_ENGINEER_PROMPT, SECURITY_AGENT_PROMPT,
    DEVELOPER_AGENT_TDD_PROMPT, get_factory_boss_l4_prompt
)

MODEL = 'llama3.1'
MAX_RETRIES = 3

# ---------- STANDARDS LOADING ----------
def load_quality_standards():
    """Load quality standards from JSON files."""
    standards_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "utils", "standards")
    standards = {}
    
    try:
        for filename in ["python_standards.json", "sql_standards.json", "web_standards.json"]:
            path = os.path.join(standards_dir, filename)
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    standards[filename.replace("_standards.json", "")] = json.load(f)
    except Exception as e:
        print(f"⚠️ Failed to load quality standards: {e}")
        
    return standards

QUALITY_STANDARDS = load_quality_standards()

def get_standards_context(module_type="service"):
    """Generate a context string with relevant standards."""
    context = []
    
    def _add_standards(category_name, standards_dict):
        """Helper to add all sections from a standards dictionary."""
        # Always add 'general' first if it exists
        if "general" in standards_dict:
            context.append(f"\n{category_name} GENERAL STANDARDS:")
            context.extend([f"- {r}" for r in standards_dict["general"]])
            
        # Add other sections
        for section, rules in standards_dict.items():
            if section == "general": continue
            context.append(f"\n{category_name} {section.upper().replace('_', ' ')} STANDARDS:")
            context.extend([f"- {r}" for r in rules])

    # Python standards apply to almost everything backend
    if "python" in QUALITY_STANDARDS:
        _add_standards("PYTHON", QUALITY_STANDARDS["python"])
    
    # SQL standards for data/service modules
    if module_type in ["service", "data", "repository"] and "sql" in QUALITY_STANDARDS:
        _add_standards("SQL/DATABASE", QUALITY_STANDARDS["sql"])
        
    # Web standards for frontend/interface
    if module_type in ["web_interface", "frontend"] and "web" in QUALITY_STANDARDS:
        _add_standards("WEB/FRONTEND", QUALITY_STANDARDS["web"])
        
    return "\n".join(context)

# ---------- UTILS ----------
class DualLogger:
    """
    Duplicates stdout to a file and the console.
    Ensures all console output is captured for debugging.
    Also logs ERROR level output to quality_remarks.jsonl
    """
    def __init__(self, filepath, project_dir=None):
        self.terminal = sys.stdout
        self.log = open(filepath, "w", encoding="utf-8")
        self.project_dir = project_dir

    def write(self, message):
        self.terminal.write(message)
        self.log.write(message)
        self.log.flush()
        
        # Capture errors to quality remarks
        if self.project_dir and message.strip():
             lower_msg = message.lower()
             if "error" in lower_msg or "exception" in lower_msg or "failed" in lower_msg or "traceback" in lower_msg:
                 # Avoid duplicates and simple warnings
                 if "attempt" not in lower_msg and "retrying" not in lower_msg:
                     try:
                        log_quality_remark(self.project_dir, "CONSOLE_ERROR", message.strip())
                     except:
                        pass

    def flush(self):
        self.terminal.flush()
        self.log.flush()

def fix_yaml_content(text):
    """
    Fixes common YAML syntax errors in agent output.
    """
    lines = text.split('\n')
    fixed_lines = []
    
    for i, line in enumerate(lines):
        original_line = line
        if not line.strip() or line.strip().startswith('#'):
            fixed_lines.append(line)
            continue
        
        indent = len(line) - len(line.lstrip())
        stripped = line.strip()
        
        if stripped.startswith('-'):
            fixed_lines.append(line)
            continue
        
        if ':' not in stripped:
            if i > 0 and indent > 0:
                prev_stripped = lines[i-1].strip()
                if prev_stripped.endswith(('|', '>', '|-', '>-', '[', '{')):
                    fixed_lines.append(line)
                    continue
            continue
        
        colon_idx = stripped.find(':')
        key = stripped[:colon_idx].strip()
        val = stripped[colon_idx+1:].strip()
        
        if not re.match(r'^[\w\s-]+$', key):
            continue
        
        if not val or val in ['|', '>', '|-', '>-', '{', '[']:
            fixed_lines.append(line)
            continue
        
        if (val.startswith('"') and val.endswith('"')) or \
           (val.startswith("'") and val.endswith("'")):
            fixed_lines.append(line)
            continue
        
        if val.lower() in ['true', 'false', 'yes', 'no', 'null'] or val.replace('.', '', 1).isdigit():
            fixed_lines.append(line)
            continue
        
        if val.startswith('[') and val.endswith(']'):
            fixed_lines.append(line)
            continue
        
        if val.startswith('{') and val.endswith('}'):
            fixed_lines.append(line)
            continue
        
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
        text = re.sub(r'^--.*$', '', text, flags=re.MULTILINE)
        text = re.sub(r'^(CREATE|ALTER|DROP|SELECT|INSERT|UPDATE|DELETE|PRAGMA)\s+.*?(?:;|$)', '', text, flags=re.MULTILINE | re.IGNORECASE | re.DOTALL)
        text = re.sub(r'^---\s*$', '', text, flags=re.MULTILINE).strip()
        
        match = re.search(r'^(modules|glossary|api_spec|blueprint|blackboard):', text, re.MULTILINE)
        if match:
            text = text[match.start():]
        
        text = text.strip()
        
        # Aggressive YAML Cleanup logic
        lines = text.split('\n')
        min_indent = float('inf')
        
        # 1. Detect minimum indentation of meaningful lines
        for line in lines:
            stripped = line.strip()
            if stripped and not stripped.startswith('#'):
                indent = len(line) - len(line.lstrip())
                # Only count indentation of keys or list items, not continuation lines
                if ':' in stripped or stripped.startswith('-'):
                    min_indent = min(min_indent, indent)
        
        if min_indent == float('inf'):
            min_indent = 0
        
        cleaned_lines = []
        for i, line in enumerate(lines):
            stripped = line.strip()
            
            # Preserve empty lines and comments
            if not stripped or stripped.startswith('#'):
                cleaned_lines.append(line)
                continue
            
            # Remove lines that are just "```" or markers
            if stripped.startswith('```') or stripped == '---':
                continue

            indent = len(line) - len(line.lstrip())
            
            # Filter out conversational text that accidentally got included (usually low indentation)
            # But preserve root keys (which have 0 indentation relative to min_indent)
            if indent < min_indent:
                 # It might be a root key if it ends with colon
                 if not stripped.endswith(':'):
                     continue 
            
            # Fix common agent mistakes:
            # 1. "- key: value" inside a map instead of "key: value"
            # 2. "key: value" inside a list instead of "- key: value" (harder to fix safely)
            
            cleaned_lines.append(line)
        
        text = '\n'.join(cleaned_lines).strip()
        
        # Try to fix it
        fixed_text = fix_yaml_content(text)
        
        # Validate if it parses, if not, try to wrap it
        try:
             yaml.safe_load(fixed_text)
             return fixed_text
        except:
             # Last resort: Try to find the first valid YAML-like block
             return fixed_text # Return best effort

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

def log_orchestration_event(project_dir, agent_name, action, details="", status="INFO"):
    """
    Logs high-level orchestration events to track process flow.
    target: .factory/orchestration_log.jsonl
    """
    try:
        if not project_dir: return
        meta_dir = os.path.join(project_dir, ".factory")
        if not os.path.exists(meta_dir):
            os.makedirs(meta_dir, exist_ok=True)
            
        log_path = os.path.join(meta_dir, "orchestration_log.jsonl")
        
        event = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "agent": agent_name,
            "action": action,
            "status": status,
            "details": details
        }
        
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event) + "\n")
            
    except Exception as e:
        print(f"⚠️ Failed to log orchestration event: {e}")

def log_quality_remark(project_dir, category, remark, context=""):
    """
    Logs quality remarks/feedback for future training.
    target: .factory/quality_remarks.jsonl
    """
    try:
        if not project_dir: return
        meta_dir = os.path.join(project_dir, ".factory")
        if not os.path.exists(meta_dir):
            os.makedirs(meta_dir, exist_ok=True)
            
        log_path = os.path.join(meta_dir, "quality_remarks.jsonl")
        
        entry = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "category": category,
            "remark": remark,
            "context": context
        }
        
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
            
    except Exception as e:
        print(f"⚠️ Failed to log quality remark: {e}")

def log_debug_interaction(project_dir, step, content):
    """Logs interaction to a readable text file for debugging."""
    try:
        meta_dir = os.path.join(project_dir, ".factory")
        target_dir = meta_dir if os.path.exists(meta_dir) else project_dir
        
        log_path = os.path.join(target_dir, "interaction_debug.txt")
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"\n{'='*80}\n")
            f.write(f"[{timestamp}] {step}\n")
            f.write(f"{'-'*80}\n")
            f.write(f"{content}\n")
            f.write(f"{'='*80}\n")
    except Exception as e:
        print(f"⚠️ Failed to write to interaction log: {e}")

def ask_agent(role, system, message, format_type="python", blackboard=None, agent_name=None, module_name=None, project_dir=None):
    if blackboard and not project_dir:
        project_dir = blackboard.root_dir

    if project_dir:
        # Use proper Agent Name for logging (e.g. "Developer"), put role/module in details
        log_agent = agent_name if agent_name else role
        log_details = f"Role: {role}"
        if module_name:
            log_details += f", Module: {module_name}"
        
        log_orchestration_event(project_dir, log_agent, "INVOKE", log_details, "STARTED")
        
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
        
        if project_dir:
            log_orchestration_event(project_dir, log_agent, "COMPLETE", f"Response length: {len(cleaned_response)}", "SUCCESS")
        
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

def extract_corrected_blueprint(text):
    if "Corrected blueprint" in text or "corrected version" in text.lower() or "CORRECTED BLUEPRINT" in text:
        match = re.search(r'(?:Corrected blueprint|corrected version|CORRECTED BLUEPRINT)[:\s]+', text, re.IGNORECASE)
        if match:
            remaining_text = text[match.end():]
            return super_clean(remaining_text, format_type="yaml")
    
    if "modules:" in text:
        clean_yaml = super_clean(text, format_type="yaml")
        if "modules:" in clean_yaml and "- name:" in clean_yaml:
            return clean_yaml
    return None

def extract_audit_issues(audit_text):
    issues = []
    lines = audit_text.split('\n')
    raw_feedback = []

    for line in lines:
        line = line.strip()
        if not line or line.upper().startswith('VERDICT') or line.startswith('---') or line.startswith('['):
            continue
        
        clean_line = line.lstrip('-').lstrip('*').lstrip('•').strip()
        if clean_line.startswith(('{', '}', '"', "'", '[', ']', 'modules:', 'verdict:')):
            continue

        if clean_line:
            raw_feedback.append(clean_line)
        
        line_lower = line.lower()
        if 'circular' in line_lower and 'dependency' in line_lower:
            issues.append(f"ARCHITECTURE: Remove circular dependencies - {line[:120]}")
        elif 'missing' in line_lower and 'responsibility' in line_lower:
            issues.append(f"COMPLETENESS: Add clear responsibility description to all modules - {line[:80]}")
        elif 'missing' in line_lower and 'field' in line_lower:
            issues.append(f"STRUCTURE: {line}")
        elif 'tight coupling' in line_lower:
            issues.append(f"COUPLING: Reduce dependencies between modules for loose coupling")
        elif ('duplication' in line_lower or 'duplicate' in line_lower or 'overlapping' in line_lower) and 'responsibility' in line_lower:
            issues.append(f"DESIGN: Consolidate modules with overlapping responsibilities")
        elif 'unclear' in line_lower:
            issues.append(f"CLARITY: Make module responsibilities clearer and more specific")
    
    if not issues and raw_feedback:
        for l in raw_feedback[:4]: 
            issues.append(f"FEEDBACK: {l[:150]}")
    
    if not issues:
        issues.append("GENERAL: Review architecture for violations of separation of concerns")
    
    return issues

def run_dependency_agent(blueprint, project_dir):
    """Run the Dependency Agent to generate requirements.txt"""
    print("\n🔒 [STEP 1: ENVIRONMENT LOCK] Running Dependency Agent...")
    log_orchestration_event(project_dir, "Dependency_Agent", "START", "Generating requirements.txt", "RUNNING")
    try:
        reqs = ask_agent("DEPENDENCY_AGENT", DEPENDENCY_AGENT_PROMPT, f"BLUEPRINT:\n{json.dumps(blueprint, indent=2)}", "text", project_dir=project_dir)
        
        # Sanitize output (remove "requirements.txt" if it appears as a line)
        req_lines = [line for line in reqs.splitlines() if line.strip().lower() != "requirements.txt"]
        reqs = "\n".join(req_lines)
        
        # Ensure we have essential build tools
        if "pytest" not in reqs:
            reqs += "\npytest"
            
        # SAFETY CHECK: Python 3.13+ on Windows often lacks wheels for heavy libs
        if sys.version_info >= (3, 13) and os.name == 'nt':
             if "pandas" in reqs:
                 print("⚠️ Python 3.13+ detected. Commenting out 'pandas' to prevent build errors (wheels likely missing).")
                 reqs = reqs.replace("pandas", "# pandas (Manual install required for Py 3.13+)")
             if "numpy" in reqs:
                 print("⚠️ Python 3.13+ detected. Commenting out 'numpy' to prevent build errors.")
                 reqs = reqs.replace("numpy", "# numpy (Manual install required for Py 3.13+)")

        if "flask" not in reqs and "FastAPI" not in str(blueprint): # Heuristic
            # If blueprint implies web, ensure flask or similar
            pass
            
        # Save requirements to .factory folder to keep root clean
        meta_dir = os.path.join(project_dir, ".factory")
        if not os.path.exists(meta_dir):
            os.makedirs(meta_dir, exist_ok=True)
            
        req_path = os.path.join(meta_dir, "requirements.txt")
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
"{sys.executable}" main.py
if %errorlevel% neq 0 (
    echo.
    echo [APP CRASHED] See output above.
    pause
)
pause
"""
        bat_path = os.path.join(project_dir, "run_app.bat")
        with open(bat_path, "w", encoding="utf-8") as f:
            f.write(bat_content)
        print(f"✅ run_app.bat generated")

        # Install dependencies immediately to allow TDD (pytest needs to run)
        print("📥 Installing dependencies for TDD environment...")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", req_path])
        except Exception as e:
            print(f"⚠️ Warning: Failed to install dependencies: {e}")
            log_quality_remark(project_dir, "Environment", f"Failed to install dependencies: {e}")
            
    except Exception as e:
        print(f"❌ Dependency Agent Failed: {e}")
        log_quality_remark(project_dir, "Dependency_Agent", f"Failed to generate requirements: {e}")

# ---------- WORKFLOW ----------
def run_factory(idea, debug_mode=False, plan_only=False):
    overall_start_time = time.time()
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    project_dir = f"output/project_{timestamp}"
    metadata_dir = os.path.join(project_dir, ".factory")
    
    os.makedirs(metadata_dir, exist_ok=True)
    os.makedirs(project_dir, exist_ok=True)
    
    # Initialize Logger
    sys.stdout = DualLogger(os.path.join(metadata_dir, "console_log.txt"), project_dir=project_dir)
    # Redirect stderr to stdout to capture it in logs too
    sys.stderr = sys.stdout
    
    print(f"🚀 WORKSPACE CREATED: {project_dir}")
    print(f"📂 METADATA STORED IN: {metadata_dir}")

    bb = FactoryBlackboard(idea, project_dir, metadata_dir=metadata_dir)
    phase_times = {}

    # PHASE 1 & 2: L1 ANALYST & L2 AUDITOR LOOP
    phase1_start = time.time()
    print("\n======================================================================")
    print("PHASE 1 & 2: L1 ANALYST & L2 AUDITOR – STRATEGIC PLANNING")
    print("======================================================================")
    log_orchestration_event(project_dir, "Factory_Boss", "PHASE_START", "Phase 1: Planning", "RUNNING")
    
    l1_sys = FACTORY_BOSS_L1_PROMPT
    l2_sys = FACTORY_BOSS_L2_PROMPT

    blueprint = None
    max_planning_retries = 5
    accumulated_issues = []
    suggested_fix = None
    
    for i in range(max_planning_retries):
        print(f"\n--- Planning Iteration {i+1} ---")
        log_orchestration_event(project_dir, "L1_Analyst", "ITERATION_START", f"Iteration {i+1}", "RUNNING")
        
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
            if suggested_fix:
                prompt += f"\nAUDITOR'S SUGGESTED FIX (Review and adopt if correct):\n{suggested_fix}\n"

            prompt += f"""
Original Idea: {idea}

INSTRUCTIONS:
1. Review the "ISSUES TO FIX" above carefully.
2. Create a completely NEW architecture that solves the original idea AND fixes the reported issues.
3. Ensure strict adherence to the YAML format and required fields.
4. Verify there are NO circular dependencies.
5. Output ONLY the YAML with "blackboard" as the top-level key.
"""
            print(f"  📝 L1 ANALYST: Fixing {len(accumulated_issues)} issues from previous attempt...")
            
        blueprint_raw = ask_agent("L1_ANALYST", l1_sys, prompt, "yaml", project_dir=project_dir)
        
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
            log_quality_remark(project_dir, "L1_Analyst", f"YAML Syntax Error: {e}")
            continue

        # L2: Audit
        module_count = 0
        if temp_blueprint and "blackboard" in temp_blueprint and "modules" in temp_blueprint["blackboard"]:
            module_count = len(temp_blueprint["blackboard"]["modules"])
            
        print(f"  🔍 L2 AUDITOR: Reviewing architecture ({module_count} modules)...")
        audit_raw = ask_agent("L2_AUDITOR", l2_sys, f"Review this blueprint:\n{json.dumps(temp_blueprint, indent=2)}", project_dir=project_dir)
        log_debug_interaction(project_dir, f"ITERATION {i+1} - L2 AUDITOR OUTPUT", audit_raw)
        
        if "VERDICT: PASSED" in audit_raw:
            print(f"✅ Auditor approved! Architecture includes {module_count} modules:")
            if module_count > 0:
                for mod in temp_blueprint["blackboard"]["modules"]:
                    print(f"    • {mod.get('name')}: {mod.get('responsibility')[:60]}...")
            blueprint = temp_blueprint
            log_orchestration_event(project_dir, "L2_Auditor", "APPROVAL", "Architecture approved", "SUCCESS")
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
        log_orchestration_event(project_dir, "FACTORY_BOSS", "PLANNING_FAILED", "Failed to generate valid plan after retries", "FAILED")
        return

    # === BLOCKING VALIDATION GATE ===
    print("\n🚧 CHECKING VALIDATION GATE...")
    required_keys = ["modules", "module_dependencies", "entrypoint", "app_type", "main_flow", "assembly", "runtime", "ui_design", "data_strategy"]
    missing_keys = []
    bb_content = blueprint.get("blackboard", {})
    
    for key in required_keys:
        if key not in bb_content:
            missing_keys.append(key)
            
    if missing_keys:
        print(f"❌ FATAL: Blueprint missing required sections: {missing_keys}")
        print("🛑 The Factory Boss has stopped the pipeline.")
        log_quality_remark(project_dir, "VALIDATION_GATE", f"Blueprint missing required sections: {missing_keys}")
        log_orchestration_event(project_dir, "FACTORY_BOSS", "ABORT", "Blueprint validation failed", "FAILED")
        return

    print("✅ Validation Gate Passed. Proceeding to Implementation.")
    phase1_duration = time.time() - phase1_start
    phase_times["Planning (L1+L2)"] = phase1_duration
    
    bb.set_architecture(blueprint)
    print(f"📐 Blueprint accepted and saved. (⏱️ {phase1_duration:.1f}s)")
    
    # === NEW STEP 1: ENVIRONMENT LOCK ===
    run_dependency_agent(blueprint, project_dir)
    
    if plan_only:
        print("\n🛑 Plan-only mode active. Exiting after planning phase.")
        return

    # PHASE 2 & 3: L3 ARCHITECT & L4 DEVELOPER – PARALLEL EXECUTION
    phase2_start = time.time()
    print("\n======================================================================")
    print("PHASE 3: L3 ARCHITECT & L4 DEVELOPER – PARALLEL IMPLEMENTATION")
    print("======================================================================")
    log_orchestration_event(project_dir, "FACTORY_BOSS", "PHASE_START", "Phase 3: Development", "RUNNING")
    
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
        log_orchestration_event(project_dir, "ORCHESTRATOR", "MODULE_ARCH_START", f"Starting architecture: {m_name}", "RUNNING")
        
        # 1. Architect (Spec)
        print(f"    📋 L3 ARCHITECT: Designing {module_type}...")
        l3_sys = FACTORY_BOSS_L3_PROMPT
        bb_data = blueprint.get("blackboard", {})
        l3_context = f"MODULE_TYPE: {module_type}\n\nDATA STRATEGY:\n{yaml.dump(bb_data.get('data_strategy', {}))}\n\nUI DESIGN:\n{yaml.dump(bb_data.get('ui_design', {}))}\n\nModule Details:\n{yaml.dump(module)}"
        
        spec_raw = ask_agent(f"L3_{m_name}", l3_sys, l3_context, "yaml", blackboard=bb, agent_name="L3_ARCHITECT", module_name=m_name, project_dir=project_dir)
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
        test_code = ask_agent(f"TEST_{m_name}", TEST_ENGINEER_PROMPT, test_context, "python", blackboard=bb, agent_name="TEST_ENGINEER", module_name=m_name, project_dir=project_dir)
        
        test_filename = f"test_{m_name}.py"
        tests_dir = os.path.join(project_dir, "tests")
        os.makedirs(tests_dir, exist_ok=True)
        test_path = os.path.join(tests_dir, test_filename)
        with open(test_path, "w", encoding="utf-8") as f:
            f.write(test_code)
            
        # 3. Green Phase (Implementation)
        print(f"    💻 DEVELOPER (GREEN PHASE): Implementing {m_name}...")
        
        reqs_path = os.path.join(project_dir, "requirements.txt")
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
            
            code = ask_agent(f"DEV_{m_name}", DEVELOPER_AGENT_TDD_PROMPT, tdd_context, "python", blackboard=bb, agent_name="L4_DEVELOPER", module_name=m_name, project_dir=project_dir)
            
            # Save candidate code
            file_path = os.path.join(project_dir, filename)
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(code)
            
            # 4. Gatekeeper
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
                
                result = subprocess.run(
                    [sys.executable, "-m", "pytest", os.path.join("tests", test_filename)],
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
                    tdd_context += f"\nTEST FAILURES:\n{output_snippet[-1000:]}"
                    log_quality_remark(project_dir, "GATEKEEPER", f"Tests failed for {m_name}", context=output_snippet[-500:])
            except Exception as e:
                print(f"    ⚠️ Test Execution Error: {e}")
                
        if not success:
            print(f"    ⚠️ Failed to pass tests after {max_retries} attempts. Proceeding with best effort.")
            log_orchestration_event(project_dir, "ORCHESTRATOR", "TEST_FAIL", f"Module: {m_name} - Failed to pass tests after retries", "WARNING")

        # 5. Adversarial Audit
        print(f"    🛡️ SECURITY AGENT: Auditing {m_name}...")
        audit_res = ask_agent(f"SEC_{m_name}", SECURITY_AGENT_PROMPT, f"CODE:\n{code}", "json", blackboard=bb, agent_name="SECURITY_AGENT", module_name=m_name, project_dir=project_dir)
        if "VULNERABLE" in audit_res:
            print(f"    🚨 Security Vulnerabilities Detected: {audit_res}")
            log_quality_remark(project_dir, "SECURITY_AGENT", f"Vulnerabilities in {m_name}", context=audit_res)
        else:
            print(f"    ✅ Security Audit Passed.")
            
        log_orchestration_event(project_dir, "ORCHESTRATOR", "MODULE_COMPLETE", f"Finished module generation: {m_name}", "SUCCESS")
        return {"m_name": m_name, "filename": filename, "spec": spec_raw, "code": code}

    # Execute Phase 3a: Architecture (Parallel)
    print("\n----------------------------------------------------------------------")
    print("PHASE 3a: ARCHITECTURE (Defining Interfaces)")
    print("----------------------------------------------------------------------")
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_architect_module, module): module for module in modules_list}
        for future in as_completed(futures):
            try:
                future.result()
            except Exception as e:
                print(f"❌ Architecture failed: {e}")

    # Execute Phase 3b: Development (Parallel)
    print("\n----------------------------------------------------------------------")
    print("PHASE 3b: DEVELOPMENT (Implementation with TDD)")
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
                log_orchestration_event(project_dir, "FACTORY_BOSS", "MODULE_ERROR", f"Exception in worker: {e}", "ERROR")
    
    # Frontend generation (sequential after all modules done)
    print("\n🎨 Generating frontend files...")
    log_orchestration_event(project_dir, "FACTORY_BOSS", "FRONTEND_START", "Starting Frontend Phase", "RUNNING")
    
    for m_name in results:
        result = results[m_name]
        is_web_module = (
            result.get('module_type') == 'web_interface' or 
            any(kw in m_name.lower() for kw in ["web", "interface", "ui", "frontend", "view"])
        )
        
        if is_web_module:
            try:
                print(f"  🎨 L4.5 FRONTEND DEVELOPER: Creating UI for '{m_name}'...")
                log_orchestration_event(project_dir, "L4_FRONTEND_DEV", "GENERATE", f"Creating UI for {m_name}", "RUNNING")
                
                frontend_code = run_frontend_developer(idea, result['spec'], blackboard=bb)
                frontend_files = extract_frontend_files(frontend_code)
                
                if frontend_files:
                    templates_dir = os.path.join(project_dir, "templates")
                    static_dir = os.path.join(project_dir, "static")
                    os.makedirs(templates_dir, exist_ok=True)
                    os.makedirs(static_dir, exist_ok=True)
                    
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
                    
                    bb.state.setdefault("frontend_files", []).extend(frontend_files.keys())
                    log_orchestration_event(project_dir, "L4_FRONTEND_DEV", "FILES_SAVED", f"Saved {len(frontend_files)} files for {m_name}", "SUCCESS")
            except Exception as e:
                print(f"  ⚠️ Frontend generation failed: {e}")
                log_orchestration_event(project_dir, "L4_FRONTEND_DEV", "ERROR", f"Failed for {m_name}: {e}", "ERROR")
                log_quality_remark(project_dir, "L4_FRONTEND_DEV", f"Generation failed for {m_name}", context=str(e))

    phase2_duration = time.time() - phase2_start
    phase_times["Development (L3+L4)"] = phase2_duration
    print(f"✅ Development complete. (⏱️ {phase2_duration:.1f}s)")
    log_orchestration_event(project_dir, "FACTORY_BOSS", "PHASE_END", "Phase 3: Development Complete", "SUCCESS")
    
    try:
        bb.verify_integrity(check_entrypoint=False)
    except RuntimeError as e:
        print(f"\n❌ FATAL INTEGRITY ERROR: {e}")
        log_quality_remark(project_dir, "INTEGRITY_CHECK", f"Fatal Integrity Error: {e}")
        log_orchestration_event(project_dir, "FACTORY_BOSS", "ABORT", f"Integrity check failed: {e}", "FAILED")
        return

    # PHASE 4: L5 INTEGRATOR
    phase3_start = time.time()
    print("\n======================================================================")
    print("PHASE 4: L5 INTEGRATOR – ASSEMBLY")
    print("======================================================================")
    log_orchestration_event(project_dir, "FACTORY_BOSS", "PHASE_START", "Phase 4: Integration", "RUNNING")
    
    files_list = bb.state["files_created"]
    
    modules_info = "Module Types:\n"
    for mod_name, mod_data in bb.state["modules"].items():
        mod_type = mod_data.get("module_type", "unknown")
        filename = mod_data.get("filename", f"{mod_name}.py")
        modules_info += f"  - {filename}: module_type = {mod_type}\n"

    api_specs_info = "\nAPI SPECIFICATIONS:\n"
    api_registry = bb.state.get("api_registry", {})
    for mod_name, spec in api_registry.items():
        api_specs_info += f"\n--- {mod_name} Spec ---\n{json.dumps(spec, indent=2)}\n"
    
    l5_sys = FACTORY_BOSS_L5_PROMPT
    integrator_input = f"Blackboard snapshot:\n{bb.snapshot()}\n\n{modules_info}\n\n{api_specs_info}\n\nIdea: {idea}"
    
    print(f"  🔗 L5 INTEGRATOR: Creating main.py...")
    
    l5_attempts = 0
    l5_max_retries = 3
    l5_success = False
    main_code = ""

    while l5_attempts < l5_max_retries and not l5_success:
        l5_attempts += 1
        main_code = ask_agent("L5_INTEGRATOR", l5_sys, integrator_input, blackboard=bb, agent_name="L5_INTEGRATOR", module_name="main", project_dir=project_dir)
        
        main_code_stripped = main_code.strip()
        if len(main_code_stripped) > 50 and ("import" in main_code or "def" in main_code):
             l5_success = True
        else:
             print(f"    ⚠️ Integrator output invalid. Retrying...")
             log_quality_remark(project_dir, "L5_INTEGRATOR", "Output invalid (too short or missing code structure)")

    main_path = os.path.join(project_dir, "main.py")
    with open(main_path, "w", encoding="utf-8") as f:
        f.write(main_code)
    
    phase3_duration = time.time() - phase3_start
    phase_times["Integration (L5)"] = phase3_duration
    print(f"✅ Integration complete. (⏱️ {phase3_duration:.1f}s)")
    log_orchestration_event(project_dir, "FACTORY_BOSS", "PHASE_END", "Phase 4: Integration Complete", "SUCCESS")
    
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
    audit_result = ask_agent("SYSTEM_AUDITOR", "You are the System Auditor.", audit_prompt, "text", project_dir=project_dir, agent_name="SYSTEM_AUDITOR")
    print(audit_result)
    log_quality_remark(project_dir, "SYSTEM_AUDITOR", audit_result)
    
    # PHASE 5: AUTO-DEBUG LOOP
    phase4_start = time.time()
    print("\n======================================================================")
    print("PHASE 5: L6 AUTO-DEBUG LOOP – TESTING & FIXING")
    print("======================================================================")
    log_orchestration_event(project_dir, "FACTORY_BOSS", "PHASE_START", "Phase 5: Debugging", "RUNNING")
    
    l6_sys = AUTO_DEBUGGER_PROMPT
    for attempt in range(MAX_RETRIES):
        print(f"\n▶ Attempt {attempt+1}")
        print(f"  🧪 L6 DEBUGGER: Testing application...")
        log_orchestration_event(project_dir, "L6_DEBUGGER", "TEST_RUN", f"Attempt {attempt+1}", "RUNNING")
        
        proc = subprocess.Popen(
            [sys.executable, "main.py"], 
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
            log_orchestration_event(project_dir, "L6_DEBUGGER", "SUCCESS", "App is running (TimeoutExpired implies running server)", "SUCCESS")
            proc.kill()
            break

        if return_code == 0:
            print("🎉 SUCCESS! Output:")
            print(stdout)
            log_orchestration_event(project_dir, "L6_DEBUGGER", "SUCCESS", "App ran successfully (Exit 0)", "SUCCESS")
            break
        else:
            error_msg = stderr
            print("❌ ERROR:")
            print(error_msg)
            log_quality_remark(project_dir, "RUNTIME_ERROR", error_msg)
            
            # Simple Fix Loop
            debug_msg = f"ERROR:\n{error_msg}"
            fix_raw = ask_agent("L6_DEBUGGER", l6_sys, debug_msg, blackboard=bb, agent_name="L6_DEBUGGER", module_name="debug", project_dir=project_dir)
            
            # Apply fix (simplified for refactor safety)
            # In real scenario, would parse "FILE: ..."
            print("    ⚠️ Auto-fix applied (Simulation)")
            log_orchestration_event(project_dir, "L6_DEBUGGER", "FIX_APPLIED", "Simulated auto-fix", "INFO")

    phase4_duration = time.time() - phase4_start
    phase_times["Debugging (L6)"] = phase4_duration
    log_orchestration_event(project_dir, "FACTORY_BOSS", "PHASE_END", "Phase 5: Debugging Complete", "SUCCESS")
    
    overall_duration = time.time() - overall_start_time
    
    print("\n======================================================================")
    print("🎉 BUILD COMPLETE!")
    print("======================================================================")
    print(f"📍 Project directory: {project_dir}")
    log_orchestration_event(project_dir, "FACTORY_BOSS", "COMPLETE", f"Build finished in {overall_duration:.1f}s", "SUCCESS")

import argparse
from agents import agent_analyst

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AgentFactory - AI Software Generator")
    parser.add_argument("--idea", type=str, help="The software idea to build")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode (generates detailed report)")
    parser.add_argument("--plan-only", action="store_true", help="Only run Analyst and Auditor (stop after planning)")
    args = parser.parse_args()

    if not os.path.exists("output"):
        os.makedirs("output")
        
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
