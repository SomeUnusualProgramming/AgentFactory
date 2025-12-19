# AI Context & Project Documentation

## 1. Project Overview
**AgentFactory** is a multi-agent software generation system powered by local LLMs (Ollama/Llama 3.1). It simulates a software development lifecycle where specialized AI agents collaborate to turn a user idea into working Python code. The system uses **module type classification** to guide agents in generating code that matches each module's role.

## 2. Core Architecture

### Module Type System (NEW)
Every module has a **`module_type`** that defines its role and guides agent behavior:
- **`web_interface`**: Flask/FastAPI routes, HTTP handlers, HTML rendering. Must export `app` instance.
- **`service`**: Business logic, data processing, external API calls. Importable functions/classes, no main entry point.
- **`utility`**: Helper functions for validation, formatting, logging. Pure functions, NO business logic.

The module type flows through the entire pipeline:
1. **L1 Analyst** includes `module_type` in architecture
2. **L3 Architect** receives and outputs `module_type` in spec
3. **L4 Developer** generates code matching the type
4. **L5 Integrator** uses type to determine main.py structure

### Orchestrators
- **`factory_boss.py`**: The main controller. It manages the entire lifecycle, coordinates agents, handles state via `FactoryBlackboard`, and validates main.py quality. Contains utility functions (`super_clean`, `fix_yaml_content`) and dependency filtering.
- **`supervisor.py`**: A simpler, high-level orchestrator that focuses on the initial planning phase, looping between the Analyst and Auditor to produce a valid `final_plan.yaml`.

### State Management
- **`factory_boss_blackboard.py`**: Defines the `FactoryBlackboard` class. This is the **Single Source of Truth**. It now stores and propagates `module_type` for each module. Persists project state (status, architecture, modules, logs) to `blackboard.json`.

### Agents (Specialized Scripts)
Each agent is a specialized Python script wrapping an LLM prompt:
- **`agent_analyst.py`** (L1): Converts a user idea into a high-level YAML blueprint with **module_type classification**.
- **`agent_auditor.py`** (L2): Reviews the Analyst's blueprint for logic and feasibility.
- **`agent_architect.py`** (L3): Takes a module definition and creates a detailed Technical Specification. **MUST output module_type as first field**.
- **`agent_developer.py`** (L4): Implements Python code based on module_type (web_interface → Flask routes, service → importable functions, utility → helper functions).
- **`agent_code_reviewer.py`** (L4.5): Reviews generated code for style, architecture, performance, and best practices. Returns JSON report with quality score (0-100) and identified issues.
- **`agent_code_optimizer.py`** (L4.75): Refactors code based on reviewer feedback, applying optimizations while preserving functionality.
- **`agent_integrator.py`** (L5): Generates main.py entry point using **step-by-step algorithm** based on module types. For web apps: imports Flask app and calls `app.run()` (exactly 3 lines). For non-web: imports and calls service module.

## 3. Data Flow & Lifecycle

1.  **Planning Phase (L1+L2)**:
    - Input: User Idea.
    - `Analyst` generates a YAML blueprint with **module_type for each module**.
    - `Auditor` reviews blueprint for logic and feasibility.
    - Loop continues until approved.
    - Result: Blueprint stored in Blackboard with module types.

2.  **Architecture Phase (L3)**:
    - `factory_boss.py` reads the blueprint.
    - Extracts **module_type from each module definition**.
    - For each module, passes module_type **explicitly** to `Architect`.
    - `Architect` receives MODULE_TYPE and **MUST output it as first field** of spec.
    - Result: Technical spec with module_type stored in Blackboard.

3.  **Development Phase (L4+L4.5+L4.75)**:
    - `factory_boss.py` passes `FILENAME` and `MODULE_TYPE` to Developer.
    - `Developer` generates code matching the module type:
      - **web_interface**: Flask app with routes, app instance named `app`
      - **service**: Importable functions/classes, no main() or entry point
      - **utility**: Pure helper functions only, no imports of other modules
    - `CodeReviewer` analyzes code and generates quality report (0-100 score).
    - `CodeOptimizer` refactors code if quality score < 85.
    - Code is saved to project directory with correct filenames (snake_case).
    - Quality metrics are logged to blackboard for each module.

4.  **Integration Phase (L5)**:
    - `factory_boss.py` creates **module type mapping** and passes to `Integrator`.
    - Mapping shows each file and its module_type (e.g., `webinterface.py: module_type = web_interface`).
    - `Integrator` executes **step-by-step algorithm**:
      - STEP 1: Scan modules for module_type = "web_interface"
      - STEP 2: If found → Flask web app (STEP 3a), else → non-web app (STEP 3b)
      - STEP 3a: Generate 3-line main.py that imports Flask app and calls `app.run()`
      - STEP 3b: Import and call service module's run() function
    - Result: Concise, correct main.py that actually starts the application.
    - `factory_boss.py` validates main.py:
      - Checks length (>50 chars)
      - Detects utility functions (format_, validate_, log_)
      - Ensures proper entry point (if __name__, app.run, or imports)
      - Prints warnings if validation fails.
    - `FactoryBoss` manages pip dependencies (filters fake modules like `your_database_module`, `jsonschema`, etc.).

5.  **Auto-Debug Phase (L6)**:
    - `FactoryBoss` runs the application in a subprocess.
    - If it crashes, `L6 Debugger` analyzes the traceback and project files.
    - It applies specific fixes (syntax, imports) to the culprit file.
    - This loop repeats (up to MAX_RETRIES) until the app runs successfully.

## 4. Enhanced Logging & Debugging

The system now captures detailed AI decision-making for better debugging:

- **`agent_reasoning`**: Logs the reasoning and decisions of each agent during generation
- **`agent_attempts`**: Tracks all attempts made by agents, including failures and error context
- **`code_quality_metrics`**: Records quality scores, issues found, and optimizations applied per module

These are all stored in `blackboard.json` for post-mortem analysis when generation fails.

## 5. Key Files & Artifacts
- **`blackboard.json`**: JSON dump of the current project state (managed by `FactoryBlackboard`).
  - Now includes: `module_type` for each module, `agent_reasoning`, `agent_attempts`, `code_quality_metrics`
  - Each module entry has: `filename`, `spec`, `module_type`
- **`draft_plan.yaml`**: Intermediate plan during the Analyst/Auditor loop.
- **`final_plan.yaml`**: The approved project blueprint with module_types.
- **`project_state.yaml`**: Legacy or alternative state tracking.
- **`prompt_library.py`**: Centralized repository of all agent prompts. Contains:
  - `FACTORY_BOSS_L1_PROMPT`: Analyst - includes module_type in examples
  - `FACTORY_BOSS_L3_PROMPT`: Architect - MUST output module_type as first field
  - `FACTORY_BOSS_L4_TEMPLATE`: Developer - generates code based on module_type
  - `FACTORY_BOSS_L5_PROMPT`: Integrator - step-by-step algorithm for main.py generation

## 6. Development Guidelines for AI

### Module Type Propagation
- **L1 (Analyst)**: Include `module_type: "web_interface|service|utility"` for each module in YAML.
- **L2 (Auditor)**: Validate that all modules have valid module_types.
- **L3 (Architect)**: Receive MODULE_TYPE in input, MUST output it as first field of spec YAML.
  - Failure criteria: If output doesn't start with `module_type:` → spec is rejected.
- **L4 (Developer)**: Receive FILENAME and MODULE_TYPE, generate code matching the type.
  - web_interface: Flask routes, `app` instance named exactly 'app'
  - service: Importable functions/classes, no main() blocks
  - utility: Pure helper functions, no business logic
- **L5 (Integrator)**: Receive module_type mapping, execute step-by-step algorithm to create main.py.

### Code Quality & Validation
- **Parsing AI Output**: Always use `factory_boss.super_clean(text)` to strip Markdown code blocks and conversational filler.
- **YAML Handling**: Use `factory_boss.fix_yaml_content(text)` to repair common LLM YAML errors.
- **Dependency Filtering**: Fake modules (your_database_module, jsonschema, email_validator, etc.) are filtered out and NOT installed.
- **Main.py Validation**: `factory_boss.py` post-generation checks:
  - Length > 50 chars (detects utility-only code)
  - No utility function definitions (format_, validate_, log_)
  - Contains proper entry point (if __name__, app.run, or imports in first 5 lines)

### Best Practices
- **Model**: The system is tuned for `llama3.1`.
- **Dependencies**: Relies on `ollama` Python library.
- **Security**: NEVER use hardcoded credentials (API keys, passwords). Always use `os.environ.get()` or mock if env var is missing.
- **Filenames**: Always use snake_case for filenames (ArtcleRepository → article_repository.py)

## 7. How to Run

### Basic Setup
- Ensure Ollama is running with `llama3.1` pulled.
- All generated modules use only Python standard library (no external pip dependencies required except Flask).

### Planning & Analysis
- Run `python supervisor.py` for a simple planning loop with Analyst/Auditor feedback.

### Full Generation with Module Type System
- Run `python factory_boss.py --idea "Your app idea here"` for the complete generation process.
  - This includes: Analyst → Auditor → Architect → Developer → CodeReviewer → CodeOptimizer → Integrator → AutoDebugger
  - Module type system is active throughout:
    - **Analyst** generates blueprint with module_type for each module
    - **Architect** receives and outputs module_type in spec
    - **Developer** generates code matching module_type
    - **Integrator** uses module_type mapping to create correct main.py
  - All agent reasoning and attempts are logged to `blackboard.json`
  - Quality metrics are recorded for each generated module

### Debug Mode
- Run with `--debug` flag to generate a detailed execution report:
  `python factory_boss.py --idea "Your app idea" --debug`
- Creates `debug_report.md` in the project directory containing:
  - Full prompt/response logs for every agent interaction
  - High-level project summary and execution map
  - Useful for auditing AI decision making

### Expected Main.py Behavior

**For Web Applications (Flask):**
- Output should be approximately 3 lines:
  ```python
  if __name__ == '__main__':
      from webinterface import app
      app.run(debug=False, host='0.0.0.0', port=5000)
  ```
- Server starts automatically on port 5000
- Integrator validates this structure post-generation

**For Non-Web Applications (Services/CLI):**
- Imports service module and calls its main() or run() function
- Handles command-line arguments if applicable

### Validation & Warnings
The system prints validation warnings after Integrator phase:
- ⚠️ "main.py is too short (likely utility-only)" → Integrator failed to create entry point
- ⚠️ "main.py contains utility functions" → Code was copied instead of imported
- ⚠️ "main.py may not have proper entry point" → Missing if __name__, app.run, or imports

If warnings appear, the auto-debug phase will attempt fixes.

### Testing & Verification
- Run `python scripts/generate_sample_artifacts.py` to create test artifacts
- Run `python scripts/test_agent_integration.py --verbose` to test all agents
- Run `python scripts/verify_code_quality.py --file <code_file>` to check generated code
- Run `python scripts/compare_outputs.py --baseline <old_output> --improved <new_output>` to compare quality improvements

### Debugging Generated Applications
- Check `output/project_*/blackboard.json` for:
  - `architecture.modules[].module_type`: Each module's role (web_interface, service, utility)
  - `modules[module_name].module_type`: Propagated type from Architect
  - `agent_reasoning`: Why each agent made specific decisions
  - `agent_attempts`: What failed and why
  - `code_quality_metrics`: Quality scores and issues found for each module
