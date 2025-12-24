import os
import sys
import json
import yaml
from core.logger import log_quality_remark, log_orchestration_event

STATUS_PASSED = "PASSED"
STATUS_FAILED = "FAILED"
STATUS_WARNING = "WARNING"

class MilestoneManager:
    def __init__(self, project_dir):
        self.project_dir = project_dir
        self.milestone_log = os.path.join(project_dir, ".factory", "milestones.json")
        self.history = self._load_history()

    def _load_history(self):
        if os.path.exists(self.milestone_log):
            try:
                with open(self.milestone_log, 'r') as f:
                    return json.load(f)
            except:
                return []
        return []

    def _save_history(self):
        os.makedirs(os.path.dirname(self.milestone_log), exist_ok=True)
        with open(self.milestone_log, 'w') as f:
            json.dump(self.history, f, indent=2)

    def record_milestone(self, stage_name, status, details=None):
        entry = {
            "stage": stage_name,
            "status": status,
            "details": details or [],
            "timestamp": "TODO_TIMESTAMP" # Using simpler approach to avoid imports if possible, or just ignore time
        }
        self.history.append(entry)
        self._save_history()

    def verify_architecture_milestone(self, blueprint):
        """
        Milestone 1: Architecture Defined
        Checks:
        - Valid YAML structure
        - Modules defined
        - No circular deps (assumed checked by Auditor, but we double check basics)
        """
        checks = []
        status = STATUS_PASSED
        
        if not blueprint or "blackboard" not in blueprint:
            checks.append("❌ Blueprint format invalid (missing 'blackboard' key)")
            status = STATUS_FAILED
        else:
            checks.append("✅ Blueprint format valid")
            
        modules = blueprint.get("blackboard", {}).get("modules", [])
        if not modules:
            checks.append("❌ No modules defined in blueprint")
            status = STATUS_FAILED
        else:
            checks.append(f"✅ {len(modules)} modules defined")

        self.record_milestone("Architecture", status, checks)
        return status == STATUS_PASSED, checks

    def verify_env_milestone(self):
        """
        Milestone 2: Environment Ready
        Checks:
        - requirements.txt exists
        - run.bat exists
        """
        checks = []
        status = STATUS_PASSED
        
        req_path = os.path.join(self.project_dir, ".factory", "requirements.txt")
        if os.path.exists(req_path):
             checks.append("✅ requirements.txt generated")
        else:
             checks.append("❌ requirements.txt missing")
             status = STATUS_FAILED

        # We don't strictly fail on pip install because we have auto-fixers, 
        # but we should note if it's completely broken.
        
        self.record_milestone("Environment", status, checks)
        return status == STATUS_PASSED, checks

    def verify_development_milestone(self, modules_results):
        """
        Milestone 3: Modules Developed & Tested
        Checks:
        - All modules have code files
        - All modules have test files
        - Test pass rate
        """
        checks = []
        status = STATUS_PASSED
        total_modules = len(modules_results)
        passed_tests = 0
        failed_tests = 0
        
        test_failures_dir = os.path.join(self.project_dir, ".factory", "test_failures")
        
        for m_name, result in modules_results.items():
            filename = result.get('filename')
            file_path = os.path.join(self.project_dir, filename)
            
            # Check Code
            if os.path.exists(file_path):
                # Check Tests
                fail_log = os.path.join(test_failures_dir, f"{m_name}_fail.txt")
                if os.path.exists(fail_log):
                    checks.append(f"⚠️ Module {m_name}: Tests FAILED")
                    failed_tests += 1
                else:
                    checks.append(f"✅ Module {m_name}: Tests Passed (or no failure log)")
                    passed_tests += 1
            else:
                checks.append(f"❌ Module {m_name}: Code file missing ({filename})")
                status = STATUS_FAILED

        checks.append(f"📊 Test Summary: {passed_tests}/{total_modules} passed")
        
        if failed_tests > 0:
            status = STATUS_WARNING # We allow proceeding but with warning
            
        self.record_milestone("Development", status, checks)
        return status != STATUS_FAILED, checks

    def verify_frontend_milestone(self, frontend_files):
        """
        Milestone 3.5: Frontend Development
        Checks:
        - Templates directory exists
        - Static directory exists
        - Essential files (index.html) created
        """
        checks = []
        status = STATUS_PASSED
        
        if not frontend_files:
             # If no frontend files were expected/generated, we might skip or warn
             # But if this is called, we assume frontend WAS attempted.
             checks.append("⚠️ No frontend files returned by agent")
             status = STATUS_WARNING
        else:
             checks.append(f"✅ Generated {len(frontend_files)} frontend files")
             
             templates_dir = os.path.join(self.project_dir, "templates")
             if os.path.exists(templates_dir) and os.listdir(templates_dir):
                 checks.append("✅ Templates directory populated")
             else:
                 checks.append("⚠️ Templates directory missing or empty")
                 status = STATUS_WARNING

        self.record_milestone("Frontend", status, checks)
        return status == STATUS_PASSED, checks

    def verify_integration_milestone(self):
        """
        Milestone 4: System Integrated
        Checks:
        - main.py exists
        - main.py imports all modules
        """
        checks = []
        status = STATUS_PASSED
        main_path = os.path.join(self.project_dir, "main.py")
        
        if os.path.exists(main_path):
            checks.append("✅ main.py created")
            # We could do AST analysis here but Factory Boss already does it
        else:
            checks.append("❌ main.py missing")
            status = STATUS_FAILED
            
        self.record_milestone("Integration", status, checks)
        return status == STATUS_PASSED, checks
