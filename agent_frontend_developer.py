import ollama
import re
from prompt_library import get_frontend_developer_prompt

MODEL = 'llama3.1'

def run_frontend_developer(app_idea: str, api_spec: str, blackboard=None):
    """Generate frontend files (HTML, CSS, JS) for a web application"""
    print("--- AGENT: FRONTEND DEVELOPER (L4.5) is generating UI... ---")
    
    prompt = get_frontend_developer_prompt(app_idea, api_spec)
    
    try:
        response = ollama.chat(model=MODEL, messages=[
            {'role': 'system', 'content': 'You are a professional frontend developer.'},
            {'role': 'user', 'content': prompt},
        ], stream=False)
        
        return response['message']['content']
    except Exception as e:
        print(f"❌ Frontend developer error: {e}")
        return ""

def extract_frontend_files(response_text: str) -> dict:
    """
    Parse the LLM response and extract HTML, CSS, and JS files.
    
    Expected format:
    <!-- HTML FILE: index.html -->
    <html>...</html>
    
    /* CSS FILE: style.css */
    body { ... }
    
    // JS FILE: app.js
    function() { ... }
    """
    files = {}
    
    # Pattern for HTML files
    html_pattern = r'(?:<!--\s*)?HTML\s+FILE:\s*(\S+)(?:\s*-->)?\s*\n(.*?)(?=(?:<!--|/\*|//)\s*(?:CSS|JS|JAVASCRIPT)\s+FILE:|$)'
    html_matches = re.finditer(html_pattern, response_text, re.DOTALL | re.IGNORECASE)
    for match in html_matches:
        filename = match.group(1).strip()
        content = match.group(2).strip()
        # Clean up markdown code blocks if present
        content = re.sub(r'^```(?:html|html5)?\s*', '', content, flags=re.MULTILINE)
        content = re.sub(r'\s*```$', '', content, flags=re.MULTILINE)
        files[filename] = content
    
    # Pattern for CSS files
    css_pattern = r'(?:/\*\s*)?CSS\s+FILE:\s*(\S+)(?:\s*\*/)?\s*\n(.*?)(?=(?:<!--|/\*|//)\s*(?:JS|JAVASCRIPT)\s+FILE:|$)'
    css_matches = re.finditer(css_pattern, response_text, re.DOTALL | re.IGNORECASE)
    for match in css_matches:
        filename = match.group(1).strip()
        content = match.group(2).strip()
        # Clean up markdown code blocks if present
        content = re.sub(r'^```(?:css)?\s*', '', content, flags=re.MULTILINE)
        content = re.sub(r'\s*```$', '', content, flags=re.MULTILINE)
        files[filename] = content
    
    # Pattern for JS files
    js_pattern = r'(?://\s*)?(?:JS|JAVASCRIPT)\s+FILE:\s*(\S+)(?:\s*)?\s*\n(.*?)(?=(?:<!--|/\*|//)\s*(?:HTML|CSS|JS|JAVASCRIPT)\s+FILE:|$)'
    js_matches = re.finditer(js_pattern, response_text, re.DOTALL | re.IGNORECASE)
    for match in js_matches:
        filename = match.group(1).strip()
        content = match.group(2).strip()
        # Clean up markdown code blocks if present
        content = re.sub(r'^```(?:javascript|js)?\s*', '', content, flags=re.MULTILINE)
        content = re.sub(r'\s*```$', '', content, flags=re.MULTILINE)
        files[filename] = content
    
    # Fallback: Try code blocks
    if not files:
        # Look for any code blocks
        code_blocks = re.findall(r'```(?:html|css|javascript|js)?\s*(.*?)\s*```', response_text, re.DOTALL)
        if code_blocks:
            # Try to identify file types from context
            for i, block in enumerate(code_blocks):
                if '<html' in block.lower() or '<!doctype' in block.lower():
                    files['index.html'] = block
                elif 'css' in block[:50].lower() or block.strip().startswith('{'):
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
