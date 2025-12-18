import json
import os
import time

class FactoryBlackboard:
    """
    SINGLE SOURCE OF TRUTH
    Used by factory_boss.py
    """

    def __init__(self, idea, root_dir):
        self.root_dir = root_dir
        self.path = os.path.join(root_dir, "blackboard.json")

        self.state = {
            "project_info": {
                "idea": idea,
                "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "status": "PLANNING"
            },
            "architecture": {
                "modules": []
            },
            "api_registry": {}, # Stores method signatures and validation rules
            "modules": {},
            "files_created": [],
            "logs": []
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
    def register_module(self, name, filename, spec=None):
        self.state["modules"][name] = {
            "filename": filename,
            "spec": spec
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
        """
        Registers the public API contract for a module.
        api_spec should be a dict of function/method names and their signatures/rules.
        """
        self.state["api_registry"][module_name] = api_spec
        self.save()

    # ---------- AGENT CONTEXT ----------
    def snapshot(self):
        """Bezpieczny kontekst dla agentów"""
        return json.dumps({
            "architecture": self.state["architecture"],
            "api_registry": self.state["api_registry"],
            "modules": self.state["modules"],
            "files_created": self.state["files_created"]
        }, indent=2)
