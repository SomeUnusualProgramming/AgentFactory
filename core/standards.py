import os
import json

def load_quality_standards():
    """Load quality standards from JSON files."""
    # Assuming this file is in core/standards.py, so we go up one level to root then to utils/standards
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
