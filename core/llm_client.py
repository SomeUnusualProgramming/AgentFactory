import ollama
import re
import yaml
import json
from core.config import MODEL
from core.logger import log_orchestration_event, log_debug_interaction

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

def clean_reasoning(text):
    """Removes REASONING blocks from the text to allow clean parsing."""
    clean = re.sub(r'REASONING:.*?END REASONING', '', text, flags=re.DOTALL | re.IGNORECASE)
    return clean

def super_clean(text, format_type="python"):
    # First, remove explicit reasoning blocks if present
    text = clean_reasoning(text)
    
    # Capture language tag to allow filtering
    blocks = re.findall(r'```(\w*)\s*(.*?)\s*```', text, re.DOTALL | re.IGNORECASE)
    if blocks:
        filtered_blocks = []
        for lang, content in blocks:
            lang = lang.lower().strip()
            # Filter logic:
            # If we specifically want python, reject html/css/js blocks
            # Keep untagged blocks ("") as they might be code
            if format_type == "python":
                if lang in ["python", "py", ""]:
                    # Secondary check: If untagged, does it look like HTML?
                    if lang == "" and ("{% extends" in content or "</html>" in content):
                        continue
                    filtered_blocks.append(content)
            elif format_type == "yaml":
                if lang in ["yaml", "yml", ""]:
                    filtered_blocks.append(content)
            else:
                filtered_blocks.append(content)
        
        if filtered_blocks:
            text = "\n".join(filtered_blocks)
        elif blocks:
            # We found blocks but filtered them all out (e.g. found html but wanted python)
            # Return empty string to force validation failure rather than returning garbage
            return ""
    else:
        text = text.replace(f'```{format_type}', '').replace('```', '')

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
            
            # Fix: invalid flow sequence char (like "key: [ ... :" )
            # If line has a list start '[' but then has a colon inside it that isn't quoted
            if '[' in stripped and ':' in stripped:
                 # Check if colon is after the bracket
                 bracket_idx = stripped.find('[')
                 colon_idx = stripped.find(':', bracket_idx)
                 if colon_idx > -1:
                     # This is likely "key: [ item: value ]" which is invalid in some YAML parsers if not quoted
                     # We'll just leave it for now, the fix_yaml_content might handle quotes
                     pass

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
             # Check for common "expected ',' or ']', but got ':'" error
             # This happens when flow style list has map-like content: [ key: value ] -> needs { key: value } or [ {key: value} ]
             
             # Attempt to convert flow lists with colons to flow maps if they look like maps
             # Regex to find [ ... : ... ]
             # This is a naive heuristic
             fixed_text = re.sub(r'\[(.*?:.*?)\]', r'[{\1}]', fixed_text)
             
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

def repair_python_code(code):
    """
    Attempts to repair Python code by removing trailing HTML/Jinja2 artifacts.
    """
    lines = code.split('\n')
    new_lines = []
    for line in lines:
        # Check for HTML/Jinja markers that shouldn't be in Python
        stripped = line.strip()
        # Heuristic: If line starts with template tags and isn't inside a python string (hard to know, but assuming garbage at end)
        if stripped.startswith("{%") or stripped.startswith("{{") or stripped.startswith("</") or stripped.startswith("<!DOCTYPE") or stripped == "html":
            # Likely start of template junk
            break
        new_lines.append(line)
    
    return '\n'.join(new_lines)

def ask_agent(role, system, message, format_type="python", blackboard=None, agent_name=None, module_name=None, project_dir=None, raw_output=False):
    if blackboard and not project_dir:
        project_dir = blackboard.root_dir

    if project_dir:
        # Use proper Agent Name for logging (e.g. "Developer"), put role/module in details
        log_agent = agent_name if agent_name else role
        log_details = f"Role: {role}"
        if module_name:
            log_details += f", Module: {module_name}"
        
        log_orchestration_event(project_dir, log_agent, "INVOKE", log_details, "STARTED")
        
        # Log detailed input for debugging
        log_debug_interaction(project_dir, f"{role}_INPUT", f"SYSTEM PROMPT:\n{system}\n\nUSER MESSAGE:\n{message}")
        
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
        
        # Log detailed output for debugging
        if project_dir:
            log_debug_interaction(project_dir, f"{role}_OUTPUT", full_response)
        
        if raw_output:
            cleaned_response = full_response
        else:
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
    # Try to find explicit header
    if any(k in text.lower() for k in ["corrected blueprint", "corrected version", "fixed blueprint", "improved blueprint"]):
        match = re.search(r'(?:Corrected blueprint|corrected version|CORRECTED BLUEPRINT|FIXED BLUEPRINT|IMPROVED BLUEPRINT)[:\s]+', text, re.IGNORECASE)
        if match:
            remaining_text = text[match.end():]
            return super_clean(remaining_text, format_type="yaml")
    
    # Fallback: If no header, but we find a large YAML block that looks like a blueprint
    if "modules:" in text:
        clean_yaml = super_clean(text, format_type="yaml")
        if "modules:" in clean_yaml and "- name:" in clean_yaml:
            return clean_yaml
            
    return None

def extract_audit_issues(audit_text):
    # Remove reasoning block first to avoid false positives
    audit_text = clean_reasoning(audit_text)
    
    issues = []
    lines = audit_text.split('\n')
    raw_feedback = []

    for line in lines:
        line = line.strip()
        if not line or line.upper().startswith('VERDICT') or line.startswith('---') or line.startswith('['):
            continue
        
        # Filter out common conversational headers that get mistaken for issues
        if line.endswith(':') and len(line) < 50:
            # e.g. "Here are actionable steps:", "Feedback:", "Issues found:"
            continue

        clean_line = line.lstrip('-').lstrip('*').lstrip('•').strip()
        if clean_line.startswith(('{', '}', '"', "'", '[', ']', 'modules:', 'verdict:', '```')):
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
    
    # If no structured issues found, fallback to raw lines but filter intelligently
    if not issues and raw_feedback:
        for l in raw_feedback[:4]: 
            # Skip lines that look like numbering headers "1. Reformat..." if they are just generic
            if l[0].isdigit() and len(l) < 10: continue
            
            issues.append(f"FEEDBACK: {l[:150]}")
    
    if not issues:
        issues.append("GENERAL: Review architecture for violations of separation of concerns")
    
    return issues

def chat_with_agent(agent_name, messages, project_dir=None):
    """
    Executes a chat request with the LLM using a full list of messages.
    Useful for interactive sessions where history is maintained.
    """
    if project_dir:
        log_orchestration_event(project_dir, agent_name, "CHAT_INVOKE", "Interactive session step", "STARTED")
        # Log last user message for debug
        last_msg = next((m['content'] for m in reversed(messages) if m['role'] == 'user'), "No user message")
        log_debug_interaction(project_dir, f"{agent_name}_CHAT_INPUT", last_msg)

    print(f"[{agent_name}] 🧠 Thinking...", end='', flush=True)
    full_response = ""
    try:
        stream = ollama.chat(model=MODEL, messages=messages, stream=True)
        
        for chunk in stream:
            content = chunk['message']['content']
            full_response += content
            print(".", end='', flush=True)
            
        print(" Done!")
        
        if project_dir:
            log_debug_interaction(project_dir, f"{agent_name}_CHAT_OUTPUT", full_response)
            log_orchestration_event(project_dir, agent_name, "CHAT_COMPLETE", f"Response length: {len(full_response)}", "SUCCESS")
            
        return full_response
    except Exception as e:
        print(f"\n❌ Error: {e}")
        if project_dir:
            log_orchestration_event(project_dir, agent_name, "CHAT_ERROR", str(e), "FAILED")
        return ""
