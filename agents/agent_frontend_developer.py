import ollama
import re
from utils.prompt_library import get_frontend_developer_prompt

MODEL = 'llama3.1'

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
    print("--- AGENT: FRONTEND DEVELOPER (L4.5) is generating UI... ---")
    
    ui_design_str = ""
    if blackboard and isinstance(blackboard, dict):
        ui_design = blackboard.get('ui_design', {})
        if ui_design:
            import json
            ui_design_str = json.dumps(ui_design, indent=2)

    prompt = get_frontend_developer_prompt(app_idea, api_spec, ui_design_str)
    
    try:
        response = ollama.chat(model=MODEL, messages=[
            {'role': 'system', 'content': 'You are a professional frontend developer.'},
            {'role': 'user', 'content': prompt},
        ], stream=False)
        
        return response['message']['content']
    except Exception as e:
        print(f"❌ Frontend developer error: {e}")
        return ""

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
    found_garbage = False
    
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
            found_garbage = True
            break
        
        clean_lines.append(line)
        
    return '\n'.join(clean_lines).strip()

def extract_frontend_files(response_text: str) -> dict:
    """
    Parse the LLM response and extract HTML, CSS, and JS files.
    """
    files = {}
    
    # Pattern for HTML files
    html_pattern = r'(?:<!--\s*)?HTML\s+FILE:\s*(\S+)(?:\s*-->)?\s*\n(.*?)(?=(?:<!--|/\*|//)\s*(?:CSS|JS|JAVASCRIPT)\s+FILE:|$)'
    html_matches = re.finditer(html_pattern, response_text, re.DOTALL | re.IGNORECASE)
    for match in html_matches:
        filename = sanitize_filename(match.group(1).strip())
        content = match.group(2).strip()
        files[filename] = clean_file_content(content, 'html')
    
    # Pattern for CSS files
    css_pattern = r'(?:/\*\s*)?CSS\s+FILE:\s*(\S+)(?:\s*\*/)?\s*\n(.*?)(?=(?:<!--|/\*|//)\s*(?:HTML|JS|JAVASCRIPT)\s+FILE:|$)'
    css_matches = re.finditer(css_pattern, response_text, re.DOTALL | re.IGNORECASE)
    for match in css_matches:
        filename = sanitize_filename(match.group(1).strip())
        content = match.group(2).strip()
        files[filename] = clean_file_content(content, 'css')
    
    # Pattern for JS files
    js_pattern = r'(?://\s*)?(?:JS|JAVASCRIPT)\s+FILE:\s*(\S+)(?:\s*)?\s*\n(.*?)(?=(?:<!--|/\*|//)\s*(?:HTML|CSS|JS|JAVASCRIPT)\s+FILE:|$)'
    js_matches = re.finditer(js_pattern, response_text, re.DOTALL | re.IGNORECASE)
    for match in js_matches:
        filename = sanitize_filename(match.group(1).strip())
        content = match.group(2).strip()
        files[filename] = clean_file_content(content, 'js')
    
    # Fallback: Try code blocks
    if not files:
        # Look for any code blocks
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
