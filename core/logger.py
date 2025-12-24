import sys
import os
import json
import time

def log_orchestration_event(project_dir, agent_name, action, details="", status="INFO"):
    """
    Logs high-level orchestration events to track process flow.
    target: .factory/orchestration_log.jsonl
    """
    try:
        if not project_dir: return
        meta_dir = os.path.join(project_dir, ".factory")
        if not os.path.exists(meta_dir):
            os.makedirs(meta_dir, exist_ok=True)
            
        log_path = os.path.join(meta_dir, "orchestration_log.jsonl")
        
        event = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "agent": agent_name,
            "action": action,
            "status": status,
            "details": details
        }
        
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event) + "\n")
            
    except Exception as e:
        print(f"⚠️ Failed to log orchestration event: {e}")

def log_quality_remark(project_dir, category, remark, context=""):
    """
    Logs quality remarks/feedback for future training.
    target: .factory/quality_remarks.jsonl
    """
    try:
        if not project_dir: return
        meta_dir = os.path.join(project_dir, ".factory")
        if not os.path.exists(meta_dir):
            os.makedirs(meta_dir, exist_ok=True)
            
        log_path = os.path.join(meta_dir, "quality_remarks.jsonl")
        
        entry = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "category": category,
            "remark": remark,
            "context": context
        }
        
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
            
    except Exception as e:
        print(f"⚠️ Failed to log quality remark: {e}")

def log_debug_interaction(project_dir, step, content):
    """Logs interaction to a readable text file for debugging."""
    try:
        meta_dir = os.path.join(project_dir, ".factory")
        target_dir = meta_dir if os.path.exists(meta_dir) else project_dir
        
        log_path = os.path.join(target_dir, "interaction_debug.txt")
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"\n{'='*80}\n")
            f.write(f"[{timestamp}] {step}\n")
            f.write(f"{'-'*80}\n")
            f.write(f"{content}\n")
            f.write(f"{'='*80}\n")
    except Exception as e:
        print(f"⚠️ Failed to write to interaction log: {e}")

def capture_snapshot(project_dir, attempt_num, filename=None):
    """Captures a snapshot of the project files or a specific file for debugging."""
    try:
        snapshot_dir = os.path.join(project_dir, ".factory", "debug_snapshots", f"attempt_{attempt_num}")
        os.makedirs(snapshot_dir, exist_ok=True)
        
        if filename:
            # Snapshot specific file
            src = os.path.join(project_dir, filename)
            if os.path.exists(src):
                dest = os.path.join(snapshot_dir, filename)
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                try:
                    with open(src, 'r', encoding='utf-8') as f:
                        content = f.read()
                    with open(dest, 'w', encoding='utf-8') as f:
                        f.write(content)
                except Exception as e:
                    print(f"⚠️ Failed to snapshot {filename}: {e}")
        else:
            # Snapshot all .py files if no specific file identified
            for root, _, files in os.walk(project_dir):
                if ".factory" in root: continue
                for file in files:
                    if file.endswith(".py"):
                        src = os.path.join(root, file)
                        rel_path = os.path.relpath(src, project_dir)
                        dest = os.path.join(snapshot_dir, rel_path)
                        os.makedirs(os.path.dirname(dest), exist_ok=True)
                        try:
                            with open(src, 'r', encoding='utf-8') as f:
                                content = f.read()
                            with open(dest, 'w', encoding='utf-8') as f:
                                f.write(content)
                        except:
                            pass
    except Exception as e:
        print(f"⚠️ Snapshot failed completely: {e}")

class DualLogger:
    """
    Duplicates stdout to a file and the console.
    Ensures all console output is captured for debugging.
    Also logs ERROR level output to quality_remarks.jsonl
    """
    def __init__(self, filepath, project_dir=None):
        self.terminal = sys.stdout
        self.log = open(filepath, "w", encoding="utf-8")
        self.project_dir = project_dir

    def write(self, message):
        self.terminal.write(message)
        self.log.write(message)
        self.log.flush()
        
        # Capture errors to quality remarks
        if self.project_dir and message.strip():
             lower_msg = message.lower()
             if "error" in lower_msg or "exception" in lower_msg or "failed" in lower_msg or "traceback" in lower_msg:
                 # Avoid duplicates and simple warnings
                 if "attempt" not in lower_msg and "retrying" not in lower_msg:
                     try:
                        log_quality_remark(self.project_dir, "CONSOLE_ERROR", message.strip())
                     except:
                        pass

    def flush(self):
        self.terminal.flush()
        self.log.flush()
