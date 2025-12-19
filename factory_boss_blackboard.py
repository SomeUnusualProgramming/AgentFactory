import json
import os
import time

class FactoryMetrics:
    """
    Separate metrics storage for code quality data.
    Keeps historical metrics data out of the main blackboard.
    """
    
    def __init__(self, root_dir):
        self.root_dir = root_dir
        self.path = os.path.join(root_dir, "metrics.json")
        self.state = {}
        self.load()
    
    def load(self):
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    self.state = json.load(f)
            except:
                self.state = {}
        else:
            self.state = {}
    
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
        
        self.state[module] = metrics
        self.save()
    
    def get_metrics(self, module: str = None):
        """Retrieve metrics for a specific module or all modules."""
        if module:
            return self.state.get(module, {})
        return self.state
    
    def get_summary(self):
        """Get a summary of all metrics."""
        if not self.state:
            return {"modules_reviewed": 0, "average_score": 0}
        
        scores = [m.get("reviewer_score", 0) for m in self.state.values()]
        return {
            "modules_reviewed": len(self.state),
            "average_score": sum(scores) / len(scores) if scores else 0,
            "total_issues": sum(m.get("issues_found", 0) for m in self.state.values()),
            "total_optimizations": sum(m.get("optimizations_applied", 0) for m in self.state.values())
        }

class FactoryBlackboard:
    """
    SINGLE SOURCE OF TRUTH
    Used by factory_boss.py
    Focuses on architecture, modules, and agent attempts.
    Code quality metrics are stored separately in metrics.json
    """

    def __init__(self, idea, root_dir):
        self.root_dir = root_dir
        self.path = os.path.join(root_dir, "blackboard.json")
        self.metrics = FactoryMetrics(root_dir)

        self.state = {
            "project_info": {
                "idea": idea,
                "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "status": "PLANNING"
            },
            "architecture": {
                "modules": []
            },
            "modules": {},
            "files_created": [],
            "logs": [],
            "agent_reasoning": [],
            "agent_attempts": []
        }

        self.save()

    # ---------- CORE ----------
    def save(self):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.state, f, indent=2)

    def log(self, msg):
        self.state["logs"].append(msg)
        self.save()

    # ---------- ARCHITECTURE ----------
    def set_architecture(self, blueprint: dict):
        self._validate_blueprint(blueprint)
        self.state["architecture"] = blueprint
        self.state["project_info"]["status"] = "ARCHITECTED"
        self.save()

    def _validate_blueprint(self, bp):
        if not isinstance(bp, dict):
            raise ValueError("Blueprint is not a dict")
        if "modules" not in bp:
            raise ValueError("Blueprint missing 'modules' key")
        if not isinstance(bp["modules"], list):
            raise ValueError("'modules' must be a list")
        for m in bp["modules"]:
            if not isinstance(m, dict):
                raise ValueError(f"Invalid module entry: {m}")
            if "name" not in m or "responsibility" not in m:
                raise ValueError(f"Module missing fields: {m}")

    # ---------- MODULES ----------
    def register_module(self, name, filename, spec=None, module_type=None):
        self.state["modules"][name] = {
            "filename": filename,
            "spec": spec,
            "module_type": module_type
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
        """
        Log the reasoning process and decision of an agent.
        Helps understand why AI made specific choices.
        """
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
        Log each attempt an agent makes, including success/failure.
        Helps debug when generation fails.
        """
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

    def generate_debug_report(self, output_path):
        """Generates a detailed debug report to a file."""
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write("# Factory Debug Report\n\n")
            f.write(f"**Date:** {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"**Idea:** {self.state['project_info']['idea']}\n\n")
            
            f.write("## 1. High Level Summary\n")
            f.write(f"- **Status:** {self.state['project_info']['status']}\n")
            f.write(f"- **Modules Created:** {len(self.state['modules'])}\n")
            for name, mod in self.state['modules'].items():
                 f.write(f"  - **{name}** ({mod.get('module_type', 'unknown')}): {mod['filename']}\n")
            
            f.write("\n## 2. Execution Steps & Logic\n")
            for i, attempt in enumerate(self.state["agent_attempts"], 1):
                f.write(f"\n### Step {i}: {attempt['agent']} -> {attempt.get('module', 'N/A')}\n")
                f.write(f"- **Timestamp:** {attempt['timestamp']}\n")
                f.write(f"- **Status:** {attempt['status']}\n")
                if attempt.get('error'):
                    f.write(f"- **Error:** {attempt['error']}\n")
                
                f.write("\n**Input (Prompt):**\n")
                f.write("```\n")
                f.write(str(attempt.get('input', '')))
                f.write("\n```\n")
                
                f.write("\n**Output (Response):**\n")
                f.write("```\n")
                f.write(str(attempt.get('output', '')))
                f.write("\n```\n")
                
                f.write("---\n")


    def log_quality_metrics(self, module: str, reviewer_score: int, issues: int, optimizations: int, review_report: dict = None):
        """
        Log code quality metrics for a module after review and optimization.
        Metrics are stored in a separate metrics.json file.
        """
        self.metrics.log_quality_metrics(module, reviewer_score, issues, optimizations, review_report)

    # ---------- AGENT CONTEXT ----------
    def snapshot(self):
        """Bezpieczny kontekst dla agentów"""
        return json.dumps({
            "architecture": self.state["architecture"],
            "modules": self.state["modules"],
            "files_created": self.state["files_created"],
            "api_registry": self.state.get("api_registry", {})
        }, indent=2)
