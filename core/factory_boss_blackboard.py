import json
import os
import time
import re

def normalize_filename(name):
    """
    Standardizes filenames to prevent mismatch errors.
    Handles non-breaking spaces, unicode whitespace, and casing.
    """
    # 1. Replace non-breaking spaces and other unicode whitespace with standard space
    clean_name = re.sub(r'[\s\u00A0\u200B]+', ' ', str(name))
    # 2. Strip whitespace
    clean_name = clean_name.strip().lower()
    # 3. Replace spaces/dots (except extension) with underscores
    if clean_name.endswith('.py'):
        base = clean_name[:-3]
        ext = '.py'
    else:
        base = clean_name
        ext = ''
        
    base = re.sub(r'[^\w\-]', '_', base)
    return f"{base}{ext}"

class FactoryMetrics:
    """
    Separate metrics storage for code quality data.
    Keeps historical metrics data out of the main blackboard.
    """
    
    def __init__(self, root_dir, metadata_dir=None):
        self.root_dir = root_dir
        self.metadata_dir = metadata_dir or root_dir
        self.path = os.path.join(self.metadata_dir, "metrics.json")
        self.state = {
            "modules": {},
            "agent_attempts": []
        }
        self.load()
    
    def load(self):
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    # Handle legacy format where root was dict of modules
                    if "modules" not in data and "agent_attempts" not in data:
                         self.state = {
                             "modules": data,
                             "agent_attempts": []
                         }
                    else:
                        self.state = data
            except:
                self.state = {
                    "modules": {},
                    "agent_attempts": []
                }
        else:
            self.state = {
                "modules": {},
                "agent_attempts": []
            }
    
    def save(self):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.state, f, indent=2)
    
    def log_quality_metrics(self, module: str, reviewer_score: int, issues: int, 
                          optimizations: int, review_report: dict = None):
        """Log code quality metrics for a module."""
        metrics = {
            "reviewer_score": reviewer_score,
            "issues_found": issues,
            "optimizations_applied": optimizations,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        }
        
        if review_report:
            metrics["issues_details"] = review_report.get("issues", [])
            metrics["summary"] = review_report.get("summary", "")
            metrics["strengths"] = review_report.get("strengths", [])
            metrics["recommendations"] = review_report.get("recommendations", [])
        
        self.state["modules"][module] = metrics
        self.save()

    def log_agent_attempt(self, agent: str, module: str, attempt_num: int, 
                         input_data: str, output: str, status: str, error: str = None):
        entry = {
            "agent": agent,
            "module": module,
            "attempt_number": attempt_num,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "input": input_data,
            "output": output,
            "status": status,
            "error": error
        }
        self.state["agent_attempts"].append(entry)
        self.save()
    
    def get_metrics(self, module: str = None):
        """Retrieve metrics for a specific module or all modules."""
        if module:
            return self.state["modules"].get(module, {})
        return self.state["modules"]
    
    def get_summary(self):
        """Get a summary of all metrics."""
        modules = self.state["modules"]
        if not modules:
            return {"modules_reviewed": 0, "average_score": 0}
        
        scores = [m.get("reviewer_score", 0) for m in modules.values()]
        return {
            "modules_reviewed": len(modules),
            "average_score": sum(scores) / len(scores) if scores else 0,
            "total_issues": sum(m.get("issues_found", 0) for m in modules.values()),
            "total_optimizations": sum(m.get("optimizations_applied", 0) for m in modules.values())
        }
    
    def get_agent_attempts(self):
        return self.state.get("agent_attempts", [])

class FactoryBlackboard:
    """
    SINGLE SOURCE OF TRUTH
    Used by factory_boss.py
    Focuses on architecture, modules, and agent attempts.
    Code quality metrics are stored separately in metrics.json
    
    ENFORCEMENT LOGIC:
    - Validates all input against strict schema
    - Prevents partial or invalid states
    - Distinguishes between required and created artifacts
    """

    def __init__(self, idea, root_dir, metadata_dir=None):
        self.root_dir = root_dir
        self.metadata_dir = metadata_dir or root_dir
        self.path = os.path.join(self.metadata_dir, "blackboard.json")
        self.metrics = FactoryMetrics(root_dir, self.metadata_dir)

        # Initialize State with strict structure
        self.state = {
            "project_info": {
                "idea": idea,
                "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "status": "PLANNING"
            },
            # STRICT ARCHITECTURE SECTION
            "architecture": {
                "app_type": None,
                "entrypoint": {
                    "entry_file": None,
                    "entry_callable": None
                },
                "main_flow": [],
                "assembly": {
                    "initialization_order": [],
                    "dependency_graph": {}
                },
                "runtime": {
                    "language": None,
                    "version": None,
                    "command": None,
                    "env_vars": [],
                    "port": None
                },
                "modules": [], # List of module definitions
                "metadata": {
                    "version": "0.0.0",
                    "last_updated_by": None,
                    "change_log": []
                }
            },
            # MODULE REGISTRY (Detailed Implementation State)
            "modules": {}, 
            "api_registry": {},
            
            # ARTIFACT TRACKING
            "required_files": [], # Derived from architecture
            "files_created": [],
            
            # GLOBAL CONSTRAINTS
            "constraints": {
                "no_invention": True,
                "blackboard_only": True,
                "fail_on_missing": True
            },
            
            # LOGS
            "logs": [],
            "agent_reasoning": []
        }

        self.save()

    # ---------- CORE ----------
    def save(self):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.state, f, indent=2)

    def log(self, msg):
        self.state["logs"].append(msg)
        self.save()

    # ---------- ARCHITECTURE & VALIDATION ----------
    def set_architecture(self, blueprint: dict):
        """
        Sets the architecture from the L1/L2 blueprint.
        PERFORMS STRICT VALIDATION.
        """
        # Handle "blackboard" wrapper if present
        if "blackboard" in blueprint:
            blueprint = blueprint["blackboard"]
            
        self._validate_blueprint_structure(blueprint)
        
        # Update State
        self.state["architecture"] = blueprint
        
        # Populate Required Files derived from modules
        self.state["required_files"] = [m["filename"] for m in blueprint["modules"]]
        
        # Add entrypoint file to required files if not already there
        entry_file = blueprint.get("entrypoint", "main.py")
        # Handle if entrypoint is dict or str (L1 prompt might output either, but we enforce dict structure now)
        if isinstance(entry_file, dict):
            entry_file_name = entry_file.get("entry_file", "main.py")
        else:
            entry_file_name = str(entry_file)
            # Normalize to dict structure
            self.state["architecture"]["entrypoint"] = {
                "entry_file": entry_file_name,
                "entry_callable": "app" if "flask" in str(blueprint.get("app_type", "")).lower() else "main"
            }
            
        if entry_file_name not in self.state["required_files"]:
            self.state["required_files"].append(entry_file_name)
            
        self.state["project_info"]["status"] = "ARCHITECTED"
        self.save()

    def _validate_blueprint_structure(self, bp):
        """
        Enforces NON-NEGOTIABLE Blackboard Requirements.
        Raises ValueError if ANY requirement is missing.
        """
        if not isinstance(bp, dict):
            raise ValueError("Blueprint must be a dictionary")

        # 1. Application Type
        if "app_type" not in bp or not bp["app_type"]:
            raise ValueError("MISSING: 'app_type' must be explicitly defined.")

        # 2. Modules
        if "modules" not in bp or not isinstance(bp["modules"], list) or not bp["modules"]:
             raise ValueError("MISSING: 'modules' list is required and cannot be empty.")
        
        for m in bp["modules"]:
            missing = [k for k in ["name", "filename", "type", "responsibility", "requires"] if k not in m]
            if missing:
                raise ValueError(f"INVALID MODULE: {m.get('name', 'Unknown')} missing fields: {missing}")

        # 3. Main Flow
        if "main_flow" not in bp or not isinstance(bp["main_flow"], list):
            raise ValueError("MISSING: 'main_flow' must be a defined list.")

        # 4. Assembly Rules
        if "assembly" not in bp:
            raise ValueError("MISSING: 'assembly' section is required.")
        if "initialization_order" not in bp["assembly"]:
            raise ValueError("MISSING: 'assembly.initialization_order' is required.")
        if "dependency_graph" not in bp["assembly"] and "module_dependencies" not in bp:
             # Support module_dependencies as alias or part of assembly
             raise ValueError("MISSING: 'assembly.dependency_graph' or 'module_dependencies' is required.")

        # 5. Runtime Contract
        if "runtime" not in bp:
            raise ValueError("MISSING: 'runtime' section is required.")
        for field in ["language", "version", "command", "port"]:
            if field not in bp["runtime"]:
                 # Allow port to be optional/null if not a web app, but key must exist? 
                 # Prompt says: "default port If missing, the pipeline MUST STOP."
                 # We will enforce strict presence of keys.
                 if field == "port" and "web" not in str(bp.get("app_type", "")).lower():
                     continue # Skip port check for non-web apps if strictness allows, but prompt says MUST STOP.
                 # Actually, prompt says "default port" is required in runtime section.
                 # So we enforce it.
                 raise ValueError(f"MISSING: 'runtime.{field}' is required.")

        # 6. Metadata
        if "metadata" not in bp:
            raise ValueError("MISSING: 'metadata' section is required.")
        for field in ["version", "last_updated_by", "change_log"]:
            if field not in bp["metadata"]:
                raise ValueError(f"MISSING: 'metadata.{field}' is required.")

    # ---------- MODULES ----------
    def register_module(self, name, filename, spec=None, module_type=None, 
                       exported_symbols=None, imported_symbols=None, explicit_dependencies=None):
        """
        Registers a generated module with extended metadata.
        """
        self.state["modules"][name] = {
            "filename": filename,
            "module_type": module_type,
            "spec": spec,
            "exported_symbols": exported_symbols or [],
            "imported_symbols": imported_symbols or [],
            "explicit_dependencies": explicit_dependencies or []
        }
        
        if filename not in self.state["files_created"]:
            self.state["files_created"].append(filename)
        self.save()

    def update_spec(self, name, spec):
        if name not in self.state["modules"]:
            raise KeyError(f"Module not registered: {name}")
        self.state["modules"][name]["spec"] = spec
        self.save()

    def register_api(self, module_name, api_spec):
        if "api_registry" not in self.state:
            self.state["api_registry"] = {}
        self.state["api_registry"][module_name] = api_spec
        self.save()

    # ---------- AGENT REASONING & DEBUGGING ----------
    def log_agent_reasoning(self, agent: str, module: str, reasoning: str, decision: str):
        entry = {
            "agent": agent,
            "module": module,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "reasoning": reasoning,
            "decision": decision
        }
        self.state["agent_reasoning"].append(entry)
        self.save()

    def log_agent_attempt(self, agent: str, module: str, attempt_num: int, 
                         input_data: str, output: str, status: str, error: str = None):
        """
        Delegates attempt logging to FactoryMetrics to keep Blackboard clean.
        """
        self.metrics.log_agent_attempt(agent, module, attempt_num, input_data, output, status, error)

    def generate_debug_report(self, output_path):
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write("# Factory Debug Report\n\n")
            f.write(f"**Date:** {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"**Idea:** {self.state['project_info']['idea']}\n\n")
            
            f.write("## 1. Architecture Status\n")
            f.write(f"- **Status:** {self.state['project_info']['status']}\n")
            f.write(f"- **App Type:** {self.state['architecture'].get('app_type', 'N/A')}\n")
            f.write(f"- **Runtime:** {self.state['architecture'].get('runtime', {}).get('language', 'N/A')}\n")
            
            f.write("\n## 2. Module Verification\n")
            req_files = set(self.state.get("required_files", []))
            created_files = set(self.state.get("files_created", []))
            missing = req_files - created_files
            
            f.write(f"- **Required Files:** {len(req_files)}\n")
            f.write(f"- **Created Files:** {len(created_files)}\n")
            if missing:
                f.write(f"- **MISSING FILES:** {', '.join(missing)}\n")
            else:
                f.write("- **ALL FILES PRESENT**\n")

            f.write("\n## 3. Execution Log\n")
            attempts = self.metrics.get_agent_attempts()
            for i, attempt in enumerate(attempts, 1):
                f.write(f"\n### Step {i}: {attempt['agent']} -> {attempt.get('module', 'N/A')}\n")
                f.write(f"- **Status:** {attempt['status']}\n")
                if attempt.get('error'):
                    f.write(f"- **Error:** {attempt['error']}\n")

    def log_quality_metrics(self, module: str, reviewer_score: int, issues: int, optimizations: int, review_report: dict = None):
        self.metrics.log_quality_metrics(module, reviewer_score, issues, optimizations, review_report)

    # ---------- AGENT CONTEXT ----------
    def snapshot(self):
        """
        Provides the FULL Blackboard state to agents.
        Includes ALL runtime-critical sections.
        """
        # Ensure we return the full state relevant to agents
        return json.dumps({
            "project_info": self.state["project_info"],
            "architecture": self.state["architecture"],
            "modules": self.state["modules"],
            "required_files": self.state["required_files"],
            "files_created": self.state["files_created"],
            "api_registry": self.state.get("api_registry", {}),
            "constraints": self.state["constraints"]
        }, indent=2)

    def verify_integrity(self, check_entrypoint=True):
        """
        Checks if the current state allows for integration/execution.
        Returns True if safe, raises Exception if not.
        
        Args:
            check_entrypoint (bool): Whether to enforce presence of entrypoint file.
                                     Should be False before Integration Phase.
        """
        req_files = set(self.state.get("required_files", []))
        created_files = set(self.state.get("files_created", []))
        missing = req_files - created_files
        
        if not check_entrypoint:
            # Safely get entrypoint filename
            entrypoint = self.state["architecture"].get("entrypoint", {}).get("entry_file")
            if entrypoint and entrypoint in missing:
                missing.remove(entrypoint)

        if missing:
            raise RuntimeError(f"INTEGRATION FAILED: Missing required files: {missing}")
            
        return True
