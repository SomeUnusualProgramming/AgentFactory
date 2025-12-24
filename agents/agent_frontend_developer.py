import re
import sys
import os
import json

# Add root to path if running directly
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.prompt_library import get_frontend_developer_prompt
from core.constants import AGENT_FRONTEND_DEV
from core.llm_client import ask_agent

def sanitize_filename(filename: str) -> str:
    """
    Remove invalid Windows/Unix filename characters and path components.
    Returns only the basename to ensure files are saved in the correct managed directories.
    """
    # First, handle potential paths by taking the basename
    filename = filename.replace('\\', '/').split('/')[-1]
    
    # Remove invalid characters
    invalid_chars = r'[<>:"/\\|?*]'
    sanitized = re.sub(invalid_chars, '', filename)
    sanitized = sanitized.strip('.')
    return sanitized if sanitized else 'file.txt'

def run_frontend_developer(app_idea: str, api_spec: str, blackboard=None):
    """Generate frontend files (HTML, CSS, JS) for a web application"""
    print(f"--- AGENT: {AGENT_FRONTEND_DEV} is generating UI... ---")
    
    ui_design_str = ""
    
    # Handle Blackboard object or dict
    if blackboard:
        if hasattr(blackboard, 'state'):
            # It's a FactoryBlackboard object
            # UI Design is usually in architecture
            arch = blackboard.state.get('architecture', {})
            ui_design = arch.get('ui_design', {})
            if not ui_design and 'ui_design' in blackboard.state:
                 # Fallback if stored at root
                 ui_design = blackboard.state['ui_design']
        elif isinstance(blackboard, dict):
            # It's a raw dict
            ui_design = blackboard.get('ui_design', {})
            if not ui_design and 'architecture' in blackboard:
                ui_design = blackboard['architecture'].get('ui_design', {})
        else:
            ui_design = {}

        if ui_design:
            ui_design_str = json.dumps(ui_design, indent=2)

    prompt = get_frontend_developer_prompt(app_idea, api_spec, ui_design_str)
    
    # Use ask_agent
    # Note: We use "text" format because we parse multiple files manually
    response = ask_agent(
        AGENT_FRONTEND_DEV,
        "You are a professional frontend developer.",
        prompt,
        format_type="text",
        agent_name=AGENT_FRONTEND_DEV,
        blackboard=blackboard if hasattr(blackboard, 'state') else None
    )
    
    return response

def clean_file_content(content: str, file_type: str) -> str:
    """Clean up markdown and conversational artifacts from file content."""
    # Remove markdown code blocks
    content = re.sub(r'^```(?:html|css|javascript|js|xml)?\s*', '', content, flags=re.MULTILINE)
    content = re.sub(r'\s*```$', '', content, flags=re.MULTILINE)
    
    # Remove trailing conversational text
    # Look for common ending patterns and cut everything after
    garbage_markers = [
        "This code", "Here is", "Note that", "The above code", 
        "In this example", "Explanation:", "**JS FILE:", "**CSS FILE:", 
        "<!-- END", "<!-- HTML FILE"
    ]
    
    lines = content.split('\n')
    clean_lines = []
    
    for line in lines:
        # If we hit a known garbage marker at the start of a line (ignoring whitespace), stop
        if any(line.strip().startswith(marker) for marker in garbage_markers):
            # Special case: <!-- END HTML --> is a valid marker we might want to respect or just stop at
            if "<!-- END" in line:
                break
            # If it's a file marker for another file, definitely stop
            if "FILE:" in line and ("CSS" in line or "JS" in line or "HTML" in line):
                break
            
            # Found garbage - stop processing
            break
        
        clean_lines.append(line)
        
    return '\n'.join(clean_lines).strip()

def extract_frontend_files(response_text: str) -> dict:
    """
    Parse the LLM response and extract HTML, CSS, and JS files.
    """
    files = {}
    
    # 1. First, remove any "Thought" or "Thinking" blocks that might confuse parsing
    response_text = re.sub(r'\[.*?\] 🧠 Thinking\.\.\..*?Done!', '', response_text, flags=re.DOTALL)
    
    # 2. Try JSON parsing first (if the model followed instructions perfectly)
    try:
        json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group(0))
            if "files" in data:
                for f in data["files"]:
                    if "path" in f and "content" in f:
                        files[sanitize_filename(f["path"])] = clean_file_content(f["content"], 'unknown')
                if files:
                    return files
    except:
        pass

    # 3. Robust Regex for "FILE: filename" pattern
    # Matches: "<!-- HTML FILE: templates/index.html -->" or "HTML FILE: templates/index.html"
    # Capture Group 1: Filename
    # Capture Group 2: Content
    
    # Generic pattern to find file headers and split content
    # We look for lines starting with HTML FILE:, CSS FILE:, JS FILE:, or their comment variants
    
    # Split text by file headers
    # Regex explanation:
    # (?m) = Multiline mode
    # ^ = Start of line
    # (?:...)? = Optional comment start (<!--, /*, //)
    # (HTML|CSS|JS|JAVASCRIPT)\s+FILE:\s* = Type marker
    # ([^\n\r]+?) = Filename (lazy)
    # (?:-->|\*/)? = Optional comment end
    # \s*$ = End of line
    
    # NOTE: We use re.IGNORECASE to catch "html file:" as well
    pattern = r'(?m)^(?:<!--|/\*|//)?\s*(HTML|CSS|JS|JAVASCRIPT)\s+FILE:\s*([^\n\r]+?)(?:\s*-->|\s*\*/)?\s*$'
    
    parts = re.split(pattern, response_text, flags=re.IGNORECASE)
    
    # parts[0] is preamble (garbage)
    # parts[1] is Type 1
    # parts[2] is Filename 1
    # parts[3] is Content 1
    # parts[4] is Type 2 ...
    
    if len(parts) >= 4:
        # Iterate in chunks of 3 (Type, Filename, Content)
        for i in range(1, len(parts), 3):
            if i+2 >= len(parts): break
            
            ftype = parts[i].lower()
            fname = parts[i+1].strip()
            content = parts[i+2].strip()
            
            # Clean content (remove markdown blocks if they wrap the whole content)
            content = clean_file_content(content, ftype)
            
            # Sanitize filename
            safe_name = sanitize_filename(fname)
            
            # Ensure correct extension if missing
            if 'html' in ftype and not safe_name.endswith('.html'): safe_name += '.html'
            if 'css' in ftype and not safe_name.endswith('.css'): safe_name += '.css'
            if 'js' in ftype and not safe_name.endswith('.js'): safe_name += '.js'
            
            # Additional clean: remove any leading ```html or trailing ``` if they slipped in
            content = re.sub(r'^```\w*\s*', '', content)
            content = re.sub(r'\s*```$', '', content)
            
            files[safe_name] = content

    # 4. Fallback: Try code blocks IF no files found yet
    # ... existing code block logic ...
    if not files:
         # Try raw dump if it looks like a single HTML file (Agent sometimes just dumps code without markers)
        if "<!DOCTYPE html>" in response_text or "<html" in response_text:
             # Assume it's index.html + maybe css/js blocks inside
             # But if it's just raw text, let's look for blocks
             pass

        code_blocks = re.findall(r'```(?:html|css|javascript|js)?\s*(.*?)\s*```', response_text, re.DOTALL)
        if code_blocks:
            # Try to identify file types from context
            for i, block in enumerate(code_blocks):
                block = clean_file_content(block, 'unknown')
                if '<html' in block.lower() or '<!doctype' in block.lower():
                    files['index.html'] = block
                elif 'body {' in block or 'margin:' in block:
                    files['style.css'] = block
                else:
                    files['app.js'] = block
        elif "<!DOCTYPE html>" in response_text:
             # Fallback for when agent dumps just one big HTML file without markdown
             # We need to try to split it if it contains CSS/JS
             full_text = response_text
             
             # Extract HTML
             html_end_idx = full_text.find("</html>")
             if html_end_idx != -1:
                 files['index.html'] = full_text[:html_end_idx+7]
                 remainder = full_text[html_end_idx+7:]
                 
                 # Look for CSS in remainder
                 if "body {" in remainder or "margin:" in remainder:
                     # Heuristic: assume the rest is CSS/JS
                     # Try to split JS
                     js_start_idx = remainder.find("async function")
                     if js_start_idx == -1: js_start_idx = remainder.find("function ")
                     if js_start_idx == -1: js_start_idx = remainder.find("document.addEventListener")
                     
                     if js_start_idx != -1:
                         files['style.css'] = remainder[:js_start_idx].strip()
                         files['app.js'] = remainder[js_start_idx:].strip()
                     else:
                         files['style.css'] = remainder.strip()
             else:
                 files['index.html'] = full_text
    
    return files

if __name__ == "__main__":
    test_idea = "A news aggregator app for Polish users"
    test_spec = """
    Routes:
    - GET /: Render main dashboard
    - POST /links: Create a new link
    - GET /links: Get all links
    - POST /categories: Create category
    - GET /categories: Get all categories
    """
    
    result = run_frontend_developer(test_idea, test_spec)
    files = extract_frontend_files(result)
    
    print("\nExtracted files:")
    for filename, content in files.items():
        print(f"\n--- {filename} ---")
        print(content[:200] + "..." if len(content) > 200 else content)
