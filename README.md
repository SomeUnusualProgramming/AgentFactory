# AgentFactory 🏭

**Turn ideas into working software with a team of AI Agents.**

AgentFactory is an autonomous multi-agent software generation system powered by local LLMs (Ollama/Llama 3.1). It simulates a complete software development lifecycle—from analysis to deployment—where specialized AI agents collaborate to build, review, optimize, and debug your application.

## 🚀 Key Features

-   **Multi-Agent Pipeline**: A coordinated team of 7+ specialized agents (Analyst, Auditor, Architect, Developer, Reviewer, Optimizer, Integrator).
-   **Module Type System**: Intelligently distinguishes between Web Interfaces (Flask), Services (Business Logic), and Utilities to generate appropriate code structures.
-   **Self-Healing & Auto-Debug**: If the generated app fails to run, the L6 Debugger agent analyzes the error and patches the code automatically.
-   **Code Quality Assurance**: Dedicated Reviewer and Optimizer agents ensure code meets quality standards before it's finalized.
-   **Local & Private**: Runs entirely on your machine using Ollama, keeping your ideas and code private.

## 🛠️ Requirements

-   **Python 3.8+**
-   **Ollama** running locally
-   **Llama 3.1 Model** (`ollama pull llama3.1`)

## 💻 Usage

### Basic Usage

Run the factory by providing a software idea directly via the command line:

```bash
python factory_boss.py --idea "A personal finance tracker with a dashboard and CSV export"
```

### Interactive Mode

If you don't provide an idea, the **Analyst Agent** will interview you to gather requirements:

```bash
python factory_boss.py
```

### 🐞 Debug Mode (New!)

Want to see exactly how the AI built your app? Enable debug mode to generate a comprehensive execution report:

```bash
python factory_boss.py --idea "Simple ToDo App" --debug
```

This will create a `debug_report.md` file in your project folder containing:
-   **High-Level Summary**: Project status and created modules.
-   **Execution Map**: A step-by-step log of every agent decision, prompt, and response.

## 🤖 Agent Orchestration Schema

The factory operates as a sequential pipeline where each agent passes its output to the next via a shared "Blackboard".

| Phase | Agent | Role | Input | Output |
| :--- | :--- | :--- | :--- | :--- |
| **1. Planning** | **L1 Analyst** | CTO / System Architect | User Idea | YAML Architecture Blueprint |
| | **L2 Auditor** | Logic Auditor | Blueprint | Approval or Rejection Feedback |
| **2. Specs** | **L3 Architect** | Module Architect | Approved Blueprint Module | Technical Spec (API, Data Types) |
| **3. Build** | **L4 Developer** | Senior Python Dev | Technical Spec | Python Code (`.py`) |
| | **L4.5 Reviewer** | Code Reviewer | Python Code | Quality Report (JSON) |
| | **L4.75 Optimizer** | Refactoring Specialist | Code + Review Report | Optimized Python Code |
| | **L4.5 Frontend** | Frontend Dev | Idea + Spec | HTML/CSS/JS (for Web Modules) |
| **4. Assembly** | **L5 Integrator** | System Integrator | All Modules + Blackboard | `main.py` Entry Point |
| **5. Quality** | **L6 Debugger** | Maintenance Engineer | Traceback + Source Files | Patched Code |

## 🏗️ Architecture Overview

The system follows a strict "Chain of Thought" workflow:

1.  **Phase 1: Planning (L1 Analyst & L2 Auditor)**
    *   Converts your idea into a structured architectural blueprint.
    *   Auditor reviews and approves the plan.
2.  **Phase 2: Architecture (L3 Architect)**
    *   Generates detailed technical specifications and API contracts for each module.
3.  **Phase 3: Development (L4 Developer)**
    *   Writes the actual Python code based on specifications.
    *   **L4.5 Reviewer** & **L4.75 Optimizer** refine the code for quality and performance.
4.  **Phase 4: Integration (L5 Integrator)**
    *   Assembles all modules into a working application (`main.py`).
5.  **Phase 5: Auto-Debug (L6 Debugger)**
    *   Runs the app, detects crashes, and autonomously fixes errors until the app runs successfully.

## 📂 Output Structure

All generated projects are saved in the `output/` directory:

```
output/
  └── project_YYYYMMDD_HHMMSS/
      ├── main.py              # Entry point
      ├── blackboard.json      # Project state & metadata
      ├── debug_report.md      # (If --debug used) Full execution log
      ├── templates/           # HTML files (for web apps)
      ├── static/              # CSS/JS files (for web apps)
      └── [module_name].py    # Generated modules
```

## 📝 License

[Your License Here]
