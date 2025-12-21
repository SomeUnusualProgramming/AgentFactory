"""
File Merger Module: Intelligent merging and validation of generated frontend files.

Provides stage/unstage functionality for tracking file changes and merging new content
with existing files without losing previous work.
"""

import os
import json
import hashlib
from typing import Dict, List, Optional, Tuple
from pathlib import Path


class FileMerger:
    """Handles intelligent merging of generated files with existing content."""
    
    def __init__(self, project_dir: str):
        self.project_dir = project_dir
        self.stage_dir = os.path.join(project_dir, ".stage")
        self.history_file = os.path.join(self.stage_dir, "history.json")
        os.makedirs(self.stage_dir, exist_ok=True)
        self.history = self._load_history()
    
    def _load_history(self) -> Dict:
        """Load file change history."""
        if os.path.exists(self.history_file):
            with open(self.history_file, "r") as f:
                return json.load(f)
        return {"files": {}, "merge_events": []}
    
    def _save_history(self):
        """Save file change history."""
        with open(self.history_file, "w") as f:
            json.dump(self.history, f, indent=2)
    
    def _get_file_hash(self, content: str) -> str:
        """Get SHA256 hash of file content."""
        return hashlib.sha256(content.encode()).hexdigest()
    
    def stage_file(self, filepath: str, content: str) -> bool:
        """
        Stage a new file version for review before merging.
        Returns True if new content differs from current.
        """
        abs_path = os.path.join(self.project_dir, filepath)
        new_hash = self._get_file_hash(content)
        
        # Check if file exists and hasn't changed
        if os.path.exists(abs_path):
            with open(abs_path, "r", encoding="utf-8") as f:
                current_content = f.read()
            current_hash = self._get_file_hash(current_content)
            
            if current_hash == new_hash:
                print(f"⏭️  {filepath}: No changes detected")
                return False
        
        # Stage the new version
        stage_path = os.path.join(self.stage_dir, filepath.replace("/", "_"))
        os.makedirs(os.path.dirname(stage_path), exist_ok=True)
        with open(stage_path, "w", encoding="utf-8") as f:
            f.write(content)
        
        print(f"📋 Staged {filepath} for review")
        return True
    
    def unstage_file(self, filepath: str) -> str:
        """
        Retrieve a staged file for inspection before merge.
        Returns the staged content.
        """
        stage_path = os.path.join(self.stage_dir, filepath.replace("/", "_"))
        if os.path.exists(stage_path):
            with open(stage_path, "r", encoding="utf-8") as f:
                return f.read()
        return ""
    
    def merge_frontend_file(self, filepath: str, new_content: str, strategy: str = "smart") -> Tuple[str, bool]:
        """
        Intelligently merge new frontend file content with existing content.
        
        Args:
            filepath: Path relative to project_dir
            new_content: New content to merge
            strategy: "overwrite", "smart", or "manual"
        
        Returns:
            Tuple of (merged_content, is_valid)
        """
        abs_path = os.path.join(self.project_dir, filepath)
        
        # If file doesn't exist, just validate new content
        if not os.path.exists(abs_path):
            is_valid = self._validate_frontend_file(filepath, new_content)
            return new_content, is_valid
        
        # File exists - apply merge strategy
        with open(abs_path, "r", encoding="utf-8") as f:
            existing_content = f.read()
        
        if strategy == "overwrite":
            merged = new_content
        elif strategy == "smart":
            merged = self._smart_merge(filepath, existing_content, new_content)
        else:
            # Manual merge would require user intervention
            merged = new_content
        
        # Validate merged content
        is_valid = self._validate_frontend_file(filepath, merged)
        
        return merged, is_valid
    
    def _smart_merge(self, filepath: str, existing: str, new: str) -> str:
        """
        Intelligently merge files based on type.
        """
        if filepath.endswith(".html"):
            return self._merge_html(existing, new)
        elif filepath.endswith(".js"):
            return self._merge_javascript(existing, new)
        elif filepath.endswith(".css"):
            return self._merge_css(existing, new)
        else:
            # Default: overwrite
            return new
    
    def _merge_html(self, existing: str, new: str) -> str:
        """
        Merge HTML files: Keep existing structure, update content sections.
        Strategy: Merge <head> sections and <body> content areas.
        """
        # For now, simple strategy: keep existing if it has more features
        # In production, this would parse and selectively merge sections
        if len(existing) > len(new) * 0.8:
            # Existing has substantial content, preserve it
            # But update script/style references from new file
            merged = existing
            # Extract new imports from new file
            new_scripts = [line for line in new.split('\n') if '<script' in line or '<link' in line]
            for script in new_scripts:
                if script not in existing:
                    # Add new script references before closing body
                    merged = merged.replace('</body>', f'{script}\n</body>')
            return merged
        return new
    
    def _merge_javascript(self, existing: str, new: str) -> str:
        """
        Merge JavaScript files: Extract functions and merge intelligently.
        Strategy: Keep both async functions, avoid duplicate definitions.
        """
        existing_lines = existing.split('\n')
        new_lines = new.split('\n')
        
        # Extract function definitions
        existing_funcs = self._extract_js_functions(existing)
        new_funcs = self._extract_js_functions(new)
        
        # Keep functions from both, prefer new versions
        all_funcs = {**existing_funcs, **new_funcs}
        
        # Reconstruct file with merged functions
        merged_lines = []
        seen_funcs = set()
        
        for line in new_lines:
            merged_lines.append(line)
            for func_name in new_funcs:
                if f"function {func_name}" in line or f"const {func_name}" in line:
                    seen_funcs.add(func_name)
        
        # Add any functions from existing that aren't in new
        for func_name, func_def in existing_funcs.items():
            if func_name not in new_funcs:
                merged_lines.extend(func_def)
        
        return '\n'.join(merged_lines)
    
    def _merge_css(self, existing: str, new: str) -> str:
        """
        Merge CSS files: Keep both rulesets, allow new to override existing.
        """
        # Simple strategy: append new CSS, let cascade rules handle conflicts
        if existing.strip() and new.strip():
            return f"{existing}\n\n/* Merged from new generation */\n{new}"
        return new if new.strip() else existing
    
    def _extract_js_functions(self, js_content: str) -> Dict[str, List[str]]:
        """Extract JavaScript function definitions from content."""
        functions = {}
        lines = js_content.split('\n')
        current_func = None
        current_lines = []
        depth = 0
        
        for line in lines:
            # Detect function definition
            if 'function ' in line or 'const ' in line and '=' in line and '(' in line:
                if current_func and current_lines:
                    functions[current_func] = current_lines
                
                func_match = line.split('(')[0]
                if 'function' in func_match:
                    current_func = func_match.split('function')[-1].strip()
                else:
                    current_func = func_match.split('=')[0].strip()
                current_lines = [line]
                depth = line.count('{') - line.count('}')
            elif current_func:
                current_lines.append(line)
                depth += line.count('{') - line.count('}')
                if depth <= 0 and current_lines:
                    functions[current_func] = current_lines
                    current_func = None
                    current_lines = []
        
        return functions
    
    def _validate_frontend_file(self, filepath: str, content: str) -> bool:
        """
        Validate frontend file for basic correctness.
        """
        if filepath.endswith(".html"):
            return self._validate_html(content)
        elif filepath.endswith(".js"):
            return self._validate_javascript(content)
        elif filepath.endswith(".css"):
            return self._validate_css(content)
        return True
    
    def _validate_html(self, content: str) -> bool:
        """Check HTML validity."""
        required = ['<!DOCTYPE', '<html', '</html>']
        for tag in required:
            if tag not in content:
                print(f"  ⚠️ Missing {tag} in HTML")
                return False
        
        # Check for balanced tags
        open_tags = content.count('<')
        close_tags = content.count('>')
        if open_tags != close_tags:
            print(f"  ⚠️ Unbalanced HTML tags ({open_tags} < vs {close_tags} >)")
            return False
        
        return True
    
    def _validate_javascript(self, content: str) -> bool:
        """Check JavaScript validity."""
        # Basic checks
        if content.count('{') != content.count('}'):
            print(f"  ⚠️ Unbalanced braces in JavaScript")
            return False
        
        if content.count('(') != content.count(')'):
            print(f"  ⚠️ Unbalanced parentheses in JavaScript")
            return False
        
        # Check for async/await in fetch calls
        if 'fetch(' in content and 'async' not in content:
            print(f"  ⚠️ fetch() found but no async function")
            return False
        
        return True
    
    def _validate_css(self, content: str) -> bool:
        """Check CSS validity."""
        # Basic syntax check
        if content.count('{') != content.count('}'):
            print(f"  ⚠️ Unbalanced braces in CSS")
            return False
        
        return True
    
    def commit_file(self, filepath: str, content: str) -> bool:
        """
        Commit a file to the project after validation and merge.
        """
        abs_path = os.path.join(self.project_dir, filepath)
        
        try:
            merged_content, is_valid = self.merge_frontend_file(filepath, content, strategy="smart")
            
            if not is_valid:
                print(f"  ❌ Validation failed for {filepath}")
                return False
            
            # Write to project
            os.makedirs(os.path.dirname(abs_path), exist_ok=True)
            with open(abs_path, "w", encoding="utf-8") as f:
                f.write(merged_content)
            
            # Update history
            file_hash = self._get_file_hash(merged_content)
            self.history["files"][filepath] = {
                "hash": file_hash,
                "size": len(merged_content)
            }
            self.history["merge_events"].append({
                "file": filepath,
                "timestamp": str(Path(abs_path).stat().st_mtime),
                "valid": is_valid
            })
            self._save_history()
            
            print(f"  ✅ Committed {filepath}")
            return True
        
        except Exception as e:
            print(f"  ❌ Failed to commit {filepath}: {e}")
            return False


def apply_merger_to_factory(factory_boss_content: str) -> str:
    """
    Generate updated factory_boss code that uses FileMerger for frontend files.
    This is called internally by the factory to update how frontend files are saved.
    """
    # Injection point: Replace the simple file write logic with merger logic
    old_pattern = """                        os.makedirs(os.path.dirname(target_path), exist_ok=True)
                        with open(target_path, "w", encoding="utf-8") as f:
                            f.write(content)
                        print(f"   ✅ Created {target_path}")"""
    
    new_pattern = """                        os.makedirs(os.path.dirname(target_path), exist_ok=True)
                        # Use FileMerger for intelligent file handling
                        merger = FileMerger(project_dir)
                        rel_path = os.path.relpath(target_path, project_dir)
                        if merger.commit_file(rel_path, content):
                            print(f"   ✅ Merged/Created {target_path}")
                        else:
                            print(f"   ⚠️  Failed to properly merge {target_path}")"""
    
    return factory_boss_content.replace(old_pattern, new_pattern)


if __name__ == "__main__":
    # Example usage
    merger = FileMerger("./test_project")
    
    html_content = """<!DOCTYPE html>
<html>
<head><title>Test</title></head>
<body><h1>Hello</h1></body>
</html>"""
    
    js_content = """async function fetchData() {
    const response = await fetch('/api/data');
    return response.json();
}"""
    
    # Test staging
    merger.stage_file("templates/index.html", html_content)
    merger.stage_file("static/app.js", js_content)
    
    # Test commit
    merger.commit_file("templates/index.html", html_content)
    merger.commit_file("static/app.js", js_content)
    
    print("✅ File merger test complete")
