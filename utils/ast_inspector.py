import ast

def analyze_code_structure(code):
    """
    Analyzes Python code to extract defined classes, functions, and their signatures.
    Returns a dictionary describing the actual implementation.
    """
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return {"error": "SyntaxError", "classes": [], "functions": []}

    structure = {
        "classes": {},
        "functions": [],
        "imports": []
    }

    for node in ast.walk(tree):
        # Extract Imports (to see dependencies)
        if isinstance(node, ast.Import):
            for n in node.names:
                structure["imports"].append(n.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                structure["imports"].append(node.module)

        # Extract Classes and their methods
        if isinstance(node, ast.ClassDef):
            class_info = {
                "name": node.name,
                "methods": [],
                "docstring": ast.get_docstring(node)
            }
            for item in node.body:
                if isinstance(item, ast.FunctionDef):
                    method_info = {
                        "name": item.name,
                        "args": [a.arg for a in item.args.args if a.arg != 'self'],
                        "has_return": bool(item.returns)
                    }
                    class_info["methods"].append(method_info)
            structure["classes"][node.name] = class_info

        # Extract Top-level Functions
        elif isinstance(node, ast.FunctionDef):
            # Check if it's a top-level function (not inside a class)
            # AST walk is flat, so we need a heuristic or just accept all names
            # A cleaner way is to iterate body of module directly, but walk is safer for nested.
            # For simplicity, we assume unique names or process module body specifically.
            pass

    # Re-iterate module body for strict top-level functions to avoid class methods
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
             structure["functions"].append(node.name)

    return structure

def generate_implementation_summary(structure):
    """Converts structure dict to a readable summary string for LLM."""
    if structure.get("error"):
        return "ERROR: Could not parse code syntax."

    summary = []
    
    if structure["classes"]:
        summary.append("DEFINED CLASSES:")
        for cls_name, details in structure["classes"].items():
            methods = ", ".join([f"{m['name']}()" for m in details['methods']])
            summary.append(f"- class {cls_name}: methods [{methods}]")
    
    if structure["functions"]:
        summary.append("EXPORTED FUNCTIONS:")
        summary.append(", ".join([f"{f}()" for f in structure["functions"]]))

    if not structure["classes"] and not structure["functions"]:
        summary.append("WARNING: No classes or functions detected.")

    return "\n".join(summary)
