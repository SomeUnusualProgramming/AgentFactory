"""
AgentFactory Code Quality Standards & Validation Framework

Universal quality standards for multi-agent code generation.
Applies to all application types (Web Apps, Services, CLIs).
Enforced at each phase: L1->L2->L3->L4->L4.5->L5

Module Type System:
- web_interface: Web routes, HTTP handlers, HTML rendering (Flask, FastAPI, etc.)
- service: Business logic, data processing, external API integration
- utility: Pure helper functions (validation, formatting, transformation)
"""

import re
import ast
import json
from typing import List, Dict, Tuple, Optional
from enum import Enum
from dataclasses import dataclass, field


# =================================================================
# ENUMS & CONSTANTS
# =================================================================

class ModuleType(str, Enum):
    """Valid module types in the system."""
    WEB_INTERFACE = "web_interface"
    SERVICE = "service"
    UTILITY = "utility"
    DATA = "data"
    FRONTEND_HTML = "frontend_html"
    FRONTEND_CSS = "frontend_css"
    FRONTEND_JS = "frontend_js"


class Severity(str, Enum):
    """Issue severity levels."""
    CRITICAL = "CRITICAL"      # Blocks generation
    HIGH = "HIGH"              # Must be fixed before merge
    MEDIUM = "MEDIUM"          # Should be fixed
    LOW = "LOW"                # Nice to have


class IssueType(str, Enum):
    """Categories of code issues."""
    SYNTAX_ERROR = "syntax_error"
    IMPORT_ERROR = "import_error"
    TYPE_HINT_MISSING = "type_hint_missing"
    SECURITY = "security"
    ARCHITECTURE = "architecture_violation"
    CODE_STYLE = "code_style"
    LOGIC_ERROR = "logic_error"
    PERFORMANCE = "performance"
    DOCUMENTATION = "documentation"


# =================================================================
# DATA CLASSES
# =================================================================

@dataclass
class CodeIssue:
    """Single code issue found during validation."""
    type: IssueType
    severity: Severity
    line: Optional[int] = None
    message: str = ""
    suggestion: str = ""
    
    def to_dict(self) -> dict:
        return {
            "type": self.type.value,
            "severity": self.severity.value,
            "line": self.line,
            "message": self.message,
            "suggestion": self.suggestion,
        }


@dataclass
class ValidationReport:
    """Complete validation report for generated code."""
    module_name: str
    module_type: ModuleType
    filename: str
    quality_score: int  # 0-100
    issues: List[CodeIssue] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    verdict: str = "PENDING"  # APPROVE, REJECT, REQUEST_CHANGES
    
    def to_dict(self) -> dict:
        return {
            "module_name": self.module_name,
            "module_type": self.module_type.value,
            "filename": self.filename,
            "quality_score": self.quality_score,
            "issues": [issue.to_dict() for issue in self.issues],
            "warnings": self.warnings,
            "verdict": self.verdict,
        }


# =================================================================
# MODULE TYPE RULES
# =================================================================

WEB_INTERFACE_RULES = {
    "type": ModuleType.WEB_INTERFACE,
    "name": "Web Interface Module",
    "description": "Flask/FastAPI routes, HTTP handlers, HTML rendering, form handling",
    
    "MUST_HAVE": [
        "from flask import Flask" or "from fastapi import FastAPI",
        "export 'app' instance exactly as 'app = Flask(...)'",
        "@app.route() decorators for endpoints",
        "HTML template rendering or JSON responses",
    ],
    
    "MUST_NOT_HAVE": [
        "Direct database queries (use injected service)",
        "Business logic (move to service)",
        "API calls (move to service)",
        "if __name__ == '__main__' (except main.py)",
        "Class definitions unrelated to HTTP handling",
        "Large data processing algorithms",
    ],
    
    "FORBIDDEN_IMPORTS": [
        "sqlite3", "psycopg2", "pymongo",  # Database drivers
        "requests", "httpx",  # External HTTP (except fetch data for view)
        "custom_db_module",
    ],
    
    "REQUIRED_PATTERNS": [
        {
            "pattern": r"@app\.route\(",
            "message": "Web interface must have at least one route",
        },
        {
            "pattern": r"(render_template|jsonify)",
            "message": "Must return views (HTML) or JSON responses",
        },
    ],
}

SERVICE_RULES = {
    "type": ModuleType.SERVICE,
    "name": "Service Module (Business Logic)",
    "description": "Business logic, data processing, API integration, stateless functions",
    
    "MUST_HAVE": [
        "Public functions or classes with clear responsibility",
        "Type hints on all function signatures",
        "Proper error handling with try-except",
        "Logging for important operations",
    ],
    
    "MUST_NOT_HAVE": [
        "Flask routes (@app.route)",
        "HTML template rendering",
        "if __name__ == '__main__'",
        "Global state (singleton patterns without justification)",
        "Web framework initialization",
        "Direct file system writes (except temp files)",
    ],
    
    "FORBIDDEN_PATTERNS": [
        {
            "pattern": r"@app\.route\(",
            "message": "Service must not contain Flask routes",
        },
        {
            "pattern": r"if __name__\s*==\s*['\"]__main__['\"]",
            "message": "Service must not have main entry point",
        },
        {
            "pattern": r"async def\s+\w+.*:\s*$",  # async def with no awaits after
            "message": "Async function must have await calls",
        },
    ],
    
    "ALLOWED_EXTERNAL_IMPORTS": [
        "requests", "httpx",  # HTTP clients
        "json", "csv",  # Data formats
        "logging",  # Logging
        "typing",  # Type hints
    ],
}

UTILITY_RULES = {
    "type": ModuleType.UTILITY,
    "name": "Utility Module (Pure Functions)",
    "description": "Helper functions: validation, formatting, transformation - NO business logic",
    
    "MUST_HAVE": [
        "Pure functions (no side effects)",
        "Type hints on all function signatures",
        "Meaningful docstrings",
        "Single responsibility per function",
    ],
    
    "MUST_NOT_HAVE": [
        "Class definitions (except data classes)",
        "Business logic",
        "Database access",
        "API calls",
        "Global state or mutable defaults",
        "Import of other project modules",
    ],
    
    "FORBIDDEN_PATTERNS": [
        {
            "pattern": r"\bself\.",
            "message": "Utility should not have class instances with state",
        },
        {
            "pattern": r"(requests\.|db\.|app\.)",
            "message": "Utility must not import external dependencies",
        },
    ],
    
    "ALLOWED_IMPORTS": [
        "re", "json", "datetime", "time",
        "typing", "dataclasses", "enum",
        "string", "collections", "itertools",
    ],
}

FRONTEND_HTML_RULES = {
    "type": ModuleType.FRONTEND_HTML,
    "name": "Frontend HTML Module",
    "description": "HTML Templates",
    
    "MUST_HAVE": [
        "<!DOCTYPE html>",
        "<html",
        "</html>",
        "<body",
        "</body>",
    ],
    
    "MUST_NOT_HAVE": [
        "```html",
        "```",
        "Here is the code",
        "This code",
    ],
    
    "FORBIDDEN_PATTERNS": [
        {
            "pattern": r"```",
            "message": "File contains Markdown code blocks",
        },
        {
            "pattern": r"(?i)(here is|this code|below is)",
            "message": "File contains conversational text",
        },
    ]
}

FRONTEND_CSS_RULES = {
    "type": ModuleType.FRONTEND_CSS,
    "name": "Frontend CSS Module",
    "description": "CSS Stylesheets",
    
    "MUST_HAVE": [
        "{",
        "}",
    ],
    
    "FORBIDDEN_PATTERNS": [
        {
            "pattern": r"```",
            "message": "File contains Markdown code blocks",
        },
        {
            "pattern": r"(?i)(here is|this code|below is|css file)",
            "message": "File contains conversational text",
        },
        {
            "pattern": r"<style>",
            "message": "CSS file should not contain <style> tags",
        },
    ]
}

FRONTEND_JS_RULES = {
    "type": ModuleType.FRONTEND_JS,
    "name": "Frontend JS Module",
    "description": "JavaScript Code",
    
    "MUST_HAVE": [
        "function",
    ],
    
    "FORBIDDEN_PATTERNS": [
        {
            "pattern": r"```",
            "message": "File contains Markdown code blocks",
        },
        {
            "pattern": r"(?i)(here is|this code|below is|js file)",
            "message": "File contains conversational text",
        },
        {
            "pattern": r"<script>",
            "message": "JS file should not contain <script> tags",
        },
    ]
}


# =================================================================
# UNIVERSAL QUALITY RULES (All Modules)
# =================================================================

UNIVERSAL_RULES = {
    "type_hints": {
        "requirement": "ALL public functions must have type hints",
        "severity": Severity.HIGH,
        "patterns": [
            {
                "pattern": r"def\s+\w+\s*\(",
                "check": "Must have return type (-> type)",
            },
        ],
    },
    
    "naming": {
        "requirement": "PEP 8 naming conventions",
        "severity": Severity.MEDIUM,
        "rules": {
            "functions": r"^[a-z_][a-z0-9_]*$",  # snake_case
            "classes": r"^[A-Z][a-zA-Z0-9]*$",   # PascalCase
            "constants": r"^[A-Z_][A-Z0-9_]*$",  # CONSTANT_CASE
            "modules": r"^[a-z_][a-z0-9_]*\.py$",  # snake_case.py
        },
    },
    
    "security": {
        "requirement": "No hardcoded credentials",
        "severity": Severity.CRITICAL,
        "forbidden_patterns": [
            r"(api_key|password|token|secret)\s*=\s*['\"][^'\"]+['\"]",
            r"(API_KEY|PASSWORD|TOKEN|SECRET)\s*=\s*['\"][^'\"]+['\"]",
        ],
    },
    
    "imports": {
        "requirement": "Organized imports (stdlib -> third-party -> local)",
        "severity": Severity.LOW,
        "order": ["__future__", "stdlib", "third_party", "local"],
    },
    
    "documentation": {
        "requirement": "Docstrings for public functions/classes",
        "severity": Severity.MEDIUM,
        "style": "Google-style or PEP 257",
    },
    
    "line_length": {
        "requirement": "Max 100 characters per line (PEP 8 soft limit)",
        "severity": Severity.LOW,
        "max": 100,
    },

    "common_pitfalls": {
        "requirement": "Avoid common Python errors",
        "severity": Severity.HIGH,
        "forbidden_patterns": [
            (r"\.contains\(", "String object has no attribute 'contains'. Use 'in' operator."),
            (r"def\s+\w+\s*\(.*=\s*\[\].*\)", "Mutable default argument detected. Use None."),
            (r"from\s+\w+_interface\s+import", "Importing non-existent Interface module."),
        ]
    },
}


# =================================================================
# VALIDATORS
# =================================================================

class CodeValidator:
    """Main code validation engine."""
    
    def __init__(self, module_type: ModuleType, filename: str):
        self.module_type = module_type
        self.filename = filename
        self.issues: List[CodeIssue] = []
        self.warnings: List[str] = []
        
    def validate(self, code: str, module_name: str = "unknown") -> ValidationReport:
        """
        Comprehensive code validation.
        
        Args:
            code: Python code as string
            module_name: Human-readable module name
            
        Returns:
            ValidationReport with all findings
        """
        self.issues = []
        self.warnings = []
        
        # Determine if it's a Python module
        is_python = self.module_type not in [ModuleType.FRONTEND_HTML, ModuleType.FRONTEND_CSS, ModuleType.FRONTEND_JS]

        # Phase 1: Syntax Check (Python only)
        if is_python:
            self._check_syntax(code)
            if self._has_critical_issues():
                return self._create_report(module_name, quality_score=0, verdict="REJECT")
        
        # Phase 2: Parse AST for deeper analysis (Python only)
        tree = None
        if is_python:
            try:
                tree = ast.parse(code)
            except SyntaxError:
                return self._create_report(module_name, quality_score=10, verdict="REJECT")
        
        # Phase 3: Module-specific rules
        self._check_module_type_rules(code)
        
        # Phase 4: Universal rules (Python only for now)
        if is_python and tree:
            self._check_universal_rules(code, tree)
        
        # Phase 5: Calculate score
        score = self._calculate_quality_score()
        verdict = "APPROVE" if score >= 80 else ("REQUEST_CHANGES" if score >= 60 else "REJECT")
        
        return self._create_report(module_name, quality_score=score, verdict=verdict)
    
    def _check_syntax(self, code: str):
        """Check for Python syntax errors."""
        try:
            ast.parse(code)
        except SyntaxError as e:
            self.issues.append(CodeIssue(
                type=IssueType.SYNTAX_ERROR,
                severity=Severity.CRITICAL,
                line=e.lineno,
                message=f"Syntax error: {e.msg}",
                suggestion="Fix the syntax error before proceeding",
            ))
    
    def _check_module_type_rules(self, code: str):
        """Validate module-specific rules based on module_type."""
        
        if self.module_type == ModuleType.WEB_INTERFACE:
            self._check_web_interface_rules(code)
        elif self.module_type == ModuleType.SERVICE:
            self._check_service_rules(code)
        elif self.module_type == ModuleType.UTILITY:
            self._check_utility_rules(code)
        elif self.module_type in [ModuleType.FRONTEND_HTML, ModuleType.FRONTEND_CSS, ModuleType.FRONTEND_JS]:
            self._check_frontend_rules(code)

    def _check_frontend_rules(self, code: str):
        """Validate frontend module rules."""
        rules = {}
        if self.module_type == ModuleType.FRONTEND_HTML:
            rules = FRONTEND_HTML_RULES
        elif self.module_type == ModuleType.FRONTEND_CSS:
            rules = FRONTEND_CSS_RULES
        elif self.module_type == ModuleType.FRONTEND_JS:
            rules = FRONTEND_JS_RULES
            
        # Check MUST_HAVE
        for pattern in rules.get("MUST_HAVE", []):
            if pattern not in code:
                self.issues.append(CodeIssue(
                    type=IssueType.SYNTAX_ERROR,
                    severity=Severity.HIGH,
                    message=f"Missing required pattern: '{pattern}'",
                ))
                
        # Check MUST_NOT_HAVE
        for pattern in rules.get("MUST_NOT_HAVE", []):
            if pattern in code:
                self.issues.append(CodeIssue(
                    type=IssueType.CODE_STYLE,
                    severity=Severity.MEDIUM,
                    message=f"Contains forbidden pattern: '{pattern}'",
                ))

        # Check FORBIDDEN_PATTERNS (regex)
        for check in rules.get("FORBIDDEN_PATTERNS", []):
            if re.search(check["pattern"], code):
                self.issues.append(CodeIssue(
                    type=IssueType.CODE_STYLE,
                    severity=Severity.HIGH,
                    message=check["message"],
                ))
    
    def _check_web_interface_rules(self, code: str):
        """Validate web_interface module rules."""
        rules = WEB_INTERFACE_RULES
        
        # Check MUST_NOT_HAVE patterns
        forbidden = [
            (r"def\s+\w+\s*\(.*\):\s*(?:(?!return).*\n)*?\s*(db\.|requests\.get|API\.call)",
             "Web interface must not contain business logic", Severity.HIGH),
            (r"@app\.route.*def\s+\w+.*:\s*(?:(?!return).*\n)*?\s*db\.",
             "Web interface must delegate DB access to services", Severity.HIGH),
        ]
        
        for pattern, msg, severity in forbidden:
            if re.search(pattern, code, re.MULTILINE | re.DOTALL):
                self.issues.append(CodeIssue(
                    type=IssueType.ARCHITECTURE,
                    severity=severity,
                    message=msg,
                ))
        
        # Check if app is properly exported
        if "app = Flask" not in code and "app = FastAPI" not in code:
            self.issues.append(CodeIssue(
                type=IssueType.ARCHITECTURE,
                severity=Severity.HIGH,
                message="Web interface must export 'app' instance (app = Flask(...) or app = FastAPI(...))",
            ))
        
        # Check for at least one route
        if not re.search(r"@app\.route\(", code):
            self.issues.append(CodeIssue(
                type=IssueType.ARCHITECTURE,
                severity=Severity.MEDIUM,
                message="Web interface should have at least one route",
            ))
    
    def _check_service_rules(self, code: str):
        """Validate service module rules."""
        rules = SERVICE_RULES
        
        # Check for main entry point
        if re.search(r"if __name__\s*==\s*['\"]__main__['\"]", code):
            self.issues.append(CodeIssue(
                type=IssueType.ARCHITECTURE,
                severity=Severity.HIGH,
                message="Service module must not have main entry point",
                suggestion="Remove 'if __name__ == \"__main__\"' block",
            ))
        
        # Check for Flask routes
        if re.search(r"@app\.route\(", code):
            self.issues.append(CodeIssue(
                type=IssueType.ARCHITECTURE,
                severity=Severity.CRITICAL,
                message="Service module must not contain Flask routes",
                suggestion="Move routes to web_interface module",
            ))
        
        # Check for orphaned async functions
        async_funcs = re.findall(r"async def\s+(\w+)\s*\(", code)
        for func in async_funcs:
            pattern = rf"async def\s+{func}.*?(?=\n(?:async )?def|\nclass|\Z)"
            func_code = re.search(pattern, code, re.DOTALL)
            if func_code and "await " not in func_code.group(0):
                self.issues.append(CodeIssue(
                    type=IssueType.LOGIC_ERROR,
                    severity=Severity.MEDIUM,
                    message=f"Async function '{func}' has no await calls",
                    suggestion="Remove 'async' or add proper await calls",
                ))
    
    def _check_utility_rules(self, code: str):
        """Validate utility module rules."""
        rules = UTILITY_RULES
        
        # Check for class definitions (except simple data classes)
        classes = re.findall(r"class\s+(\w+)", code)
        if classes:
            self.issues.append(CodeIssue(
                type=IssueType.ARCHITECTURE,
                severity=Severity.MEDIUM,
                message=f"Utility module has class definitions: {', '.join(classes)}",
                suggestion="Utilities should be pure functions, not classes",
            ))
        
        # Check for self references (state)
        if re.search(r"\bself\.", code):
            self.issues.append(CodeIssue(
                type=IssueType.ARCHITECTURE,
                severity=Severity.MEDIUM,
                message="Utility functions must be stateless",
                suggestion="Avoid using 'self' in utility modules",
            ))
        
        # Check for forbidden imports
        for forbidden in ["requests.", "db.", "app."]:
            if forbidden in code:
                self.issues.append(CodeIssue(
                    type=IssueType.ARCHITECTURE,
                    severity=Severity.HIGH,
                    message=f"Utility must not use '{forbidden}' calls",
                    suggestion="Keep utilities pure and dependency-free",
                ))
    
    def _check_universal_rules(self, code: str, tree: ast.AST):
        """Check rules that apply to all module types."""
        
        # Check type hints
        self._check_type_hints(tree)
        
        # Check for hardcoded credentials
        self._check_security(code)
        
        # Check naming conventions
        self._check_naming(tree)
        
        # Check line length
        self._check_line_length(code)

        # Check common pitfalls
        self._check_common_pitfalls(code)
    
    def _check_common_pitfalls(self, code: str):
        """Check for common Python pitfalls."""
        pitfalls = UNIVERSAL_RULES["common_pitfalls"]["forbidden_patterns"]
        
        for pattern, message in pitfalls:
            if re.search(pattern, code):
                self.issues.append(CodeIssue(
                    type=IssueType.LOGIC_ERROR,
                    severity=Severity.HIGH,
                    message=message,
                    suggestion="Fix this Python specific error",
                ))
    
    def _check_type_hints(self, tree: ast.AST):
        """Check for missing type hints."""
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                # Skip private/magic methods for utilities
                if node.name.startswith("_") and self.module_type == ModuleType.UTILITY:
                    continue
                
                # Check return type
                if node.returns is None:
                    # Skip __init__ return type check
                    if node.name != "__init__":
                        self.issues.append(CodeIssue(
                            type=IssueType.TYPE_HINT_MISSING,
                            severity=Severity.HIGH,
                            line=node.lineno,
                            message=f"Function '{node.name}' missing return type hint",
                            suggestion=f"Add '-> ReturnType' after function signature",
                        ))
                
                # Check parameter types
                for arg in node.args.args:
                    if arg.annotation is None and arg.arg not in ["self", "cls"]:
                        self.issues.append(CodeIssue(
                            type=IssueType.TYPE_HINT_MISSING,
                            severity=Severity.HIGH,
                            line=node.lineno,
                            message=f"Parameter '{arg.arg}' in '{node.name}' missing type hint",
                            suggestion=f"Add type hint: '{arg.arg}: Type'",
                        ))
    
    def _check_security(self, code: str):
        """Check for security issues."""
        security_patterns = UNIVERSAL_RULES["security"]["forbidden_patterns"]
        
        for pattern in security_patterns:
            if re.search(pattern, code, re.IGNORECASE):
                self.issues.append(CodeIssue(
                    type=IssueType.SECURITY,
                    severity=Severity.CRITICAL,
                    message="Hardcoded credentials detected",
                    suggestion="Use os.environ.get('KEY', default) for secrets",
                ))
                break
    
    def _check_naming(self, tree: ast.AST):
        """Check naming conventions."""
        rules = UNIVERSAL_RULES["naming"]["rules"]
        
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                if not re.match(rules["functions"], node.name):
                    self.warnings.append(
                        f"Function '{node.name}' should be snake_case"
                    )
            elif isinstance(node, ast.ClassDef):
                if not re.match(rules["classes"], node.name):
                    self.warnings.append(
                        f"Class '{node.name}' should be PascalCase"
                    )
    
    def _check_line_length(self, code: str):
        """Check line length."""
        max_length = UNIVERSAL_RULES["line_length"]["max"]
        long_lines = []
        
        for i, line in enumerate(code.split('\n'), 1):
            if len(line) > max_length:
                long_lines.append((i, len(line)))
        
        if long_lines:
            self.warnings.append(
                f"Found {len(long_lines)} lines exceeding {max_length} characters"
            )
    
    def _has_critical_issues(self) -> bool:
        """Check if any critical issues exist."""
        return any(issue.severity == Severity.CRITICAL for issue in self.issues)
    
    def _calculate_quality_score(self) -> int:
        """Calculate quality score based on issues."""
        score = 100
        
        for issue in self.issues:
            if issue.severity == Severity.CRITICAL:
                score -= 20
            elif issue.severity == Severity.HIGH:
                score -= 10
            elif issue.severity == Severity.MEDIUM:
                score -= 5
            elif issue.severity == Severity.LOW:
                score -= 2
        
        # Deduct for warnings
        score -= len(self.warnings) * 1
        
        return max(0, score)
    
    def _create_report(self, module_name: str, quality_score: int, verdict: str) -> ValidationReport:
        """Create validation report."""
        return ValidationReport(
            module_name=module_name,
            module_type=self.module_type,
            filename=self.filename,
            quality_score=quality_score,
            issues=self.issues,
            warnings=self.warnings,
            verdict=verdict,
        )


# =================================================================
# ARCHITECTURE VALIDATOR (L1-L2)
# =================================================================

class ArchitectureValidator:
    """Validates module architecture against standards."""
    
    @staticmethod
    def validate_blueprint(modules: List[Dict]) -> Tuple[bool, List[str]]:
        """
        Validate architecture blueprint.
        
        Args:
            modules: List of module definitions from L1 Analyst
            
        Returns:
            (is_valid, list of errors)
        """
        errors = []
        
        # Check for at least one web_interface if it's a web app
        module_types = [m.get("module_type", m.get("type")) for m in modules]
        has_web = any(t == ModuleType.WEB_INTERFACE.value for t in module_types)
        
        if not has_web and any("web" in m.get("responsibility", "").lower() for m in modules):
            errors.append(
                "Architecture appears to be a web app but has no 'web_interface' module type"
            )
        
        # Check for clear separation
        for module in modules:
            module_type = module.get("module_type", module.get("type"))
            responsibility = module.get("responsibility", "")
            
            if module_type == ModuleType.UTILITY.value:
                if any(keyword in responsibility.lower() for keyword in ["api", "database", "http", "server"]):
                    errors.append(
                        f"Module '{module.get('name')}' is marked as utility but has non-utility responsibility"
                    )
        
        return len(errors) == 0, errors


# =================================================================
# HELPER FUNCTIONS
# =================================================================

def get_validator(module_type: str, filename: str) -> CodeValidator:
    """Factory function to get appropriate validator."""
    try:
        mtype = ModuleType(module_type)
    except ValueError:
        # Fallback based on extension
        if filename.endswith('.html'):
            mtype = ModuleType.FRONTEND_HTML
        elif filename.endswith('.css'):
            mtype = ModuleType.FRONTEND_CSS
        elif filename.endswith('.js'):
            mtype = ModuleType.FRONTEND_JS
        else:
            mtype = ModuleType.SERVICE  # Default
    
    return CodeValidator(mtype, filename)


def format_report_for_display(report: ValidationReport) -> str:
    """Format validation report for display."""
    lines = [
        f"\n{'='*60}",
        f"CODE QUALITY REPORT: {report.filename}",
        f"{'='*60}",
        f"Module Type: {report.module_type.value}",
        f"Quality Score: {report.quality_score}/100",
        f"Verdict: {report.verdict}",
    ]
    
    if report.issues:
        lines.append(f"\n⚠️ ISSUES FOUND ({len(report.issues)}):")
        for i, issue in enumerate(report.issues, 1):
            lines.append(f"\n  {i}. [{issue.severity.value}] {issue.type.value}")
            lines.append(f"     Line {issue.line}: {issue.message}")
            if issue.suggestion:
                lines.append(f"     💡 {issue.suggestion}")
    
    if report.warnings:
        lines.append(f"\n⚡ WARNINGS ({len(report.warnings)}):")
        for warning in report.warnings:
            lines.append(f"  • {warning}")
    
    lines.append(f"\n{'='*60}\n")
    
    return "\n".join(lines)


if __name__ == "__main__":
    # Example usage
    sample_service = """
import requests
from typing import List, Dict

def fetch_articles(source_id: str, limit: int = 10) -> List[Dict]:
    try:
        response = requests.get(
            f"https://api.example.com/articles/{source_id}",
            params={"limit": limit}
        )
        return response.json()["articles"]
    except Exception as e:
        logger.error(f"Error fetching articles: {e}")
        raise
"""
    
    validator = get_validator("service", "fetch_service.py")
    report = validator.validate(sample_service, "FetchService")
    print(format_report_for_display(report))
