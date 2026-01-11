# AgentFactory 🏭

**Turn ideas into working software with a team of AI Agents.**

AgentFactory is an autonomous multi-agent software generation system powered by local LLMs (Ollama/Llama 3.1). It simulates a complete software development lifecycle—from analysis to deployment—where specialized AI agents collaborate to build, review, optimize, and debug your application.

## 🚀 Key Features

-   **Async Multi-Agent Architecture**: Uses `asyncio` to run agents in parallel (e.g., Frontend and Backend developers work simultaneously).
-   **Module Type System**: Intelligently distinguishes between Web Interfaces (Flask), Services (Business Logic), and Utilities.
-   **Full Stack Generation**: dedicated **Frontend Developer** agent creates HTML/CSS/JS assets while backend developers write Python code.
-   **Auto-Correction**:
    -   **Import Fixer**: Automatically detects and fixes import name mismatches and circular dependencies.
    -   **L6 Debugger**: Analyzes tracebacks and patches code if the app fails to run.
-   **Reliable Logging**: Real-time millisecond-precision logs stored in hidden `.factory` folder to track parallel execution.
-   **Local & Private**: Runs entirely on your machine using Ollama.

## 🛠️ Requirements

-   **Python 3.10+**
-   **Ollama** running locally
-   **Llama 3.1 Model** (`ollama pull llama3.1`)
-   **Redis** (Optional, falls back to in-memory mock for state management)

## 💻 Usage

### Async Engine (Recommended)

To run the new high-performance asynchronous engine:

```bash
python -m async_arch.orchestrator --idea "Your App Idea"
```

### Legacy Synchronous Mode

```bash
python -m core.factory_boss --idea "Your App Idea"
```

## 🤖 Agent Roles

The factory employs a team of specialized agents:

1.  **Analyst (L1)**: Creates the architectural blueprint and defines requirements.
2.  **Auditor (L2)**: Reviews and approves the blueprint.
3.  **Architect (L3)**: Creates technical specifications for each module.
4.  **Backend Developer (L4)**: Writes Python logic (Services, Repositories).
5.  **Frontend Developer**: Designs and implements HTML/CSS/JS in parallel with backend.
6.  **Reviewer (L4.5)**: Reviews code for bugs and quality issues.
7.  **Integrator (L5)**: Assembles `main.py` and connects all modules.

## 📂 Output Structure

Generated projects are saved in `output/`:

```
output/
  └── project_async_YYYYMMDD_HHMMSS/
      ├── .factory/            # 🔒 HIDDEN FACTORY FOLDER
      │   ├── console_log.txt  # Full execution logs with timestamps
      │   ├── blueprint.yaml   # Architecture blueprint
      │   └── [raw_files]      # Raw debug outputs from agents
      ├── templates/           # Generated HTML files
      ├── static/              # Generated CSS/JS files
      ├── main.py              # Entry point (auto-fixed imports)
      ├── requirements.txt     # Auto-generated dependencies
      ├── run.bat              # One-click launch script
      └── [modules].py         # Source code
```

## 🧰 Architecture Highlights

### Asynchronous Orchestration
The `AsyncOrchestrator` uses Python's `asyncio` to dispatch tasks. While local LLMs often process requests sequentially (due to VRAM limits), the orchestrator manages the lifecycle concurrently, allowing for:
-   Parallel dispatch of Developer agents.
-   Non-blocking Frontend generation.
-   Real-time event handling.

### Smart Import Fixing
The system includes a regex-based heuristic engine that:
-   Scans generated code for class definitions.
-   Maps classes to their actual filenames.
-   Rewrites `main.py` imports to match reality (e.g., `from user_service import UserManager as UserService`).
-   Removes instantiations of hallucinated classes.

## 📝 License

[Your License Here]
