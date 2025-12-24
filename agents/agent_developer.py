import sys
import os

# Add root to path if running directly
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.prompt_library import DEVELOPER_PROMPT_WITH_COMMENTS
from core.constants import AGENT_L4_DEVELOPER
from core.llm_client import ask_agent

def run_developer(specification):
    print(f"--- AGENT: {AGENT_L4_DEVELOPER} is coding... ---")

    # Use ask_agent for consistent logging and cleaning
    code = ask_agent(
        AGENT_L4_DEVELOPER,
        DEVELOPER_PROMPT_WITH_COMMENTS,
        f"Implement this specification:\n{specification}",
        format_type="python"
    )

    return code

if __name__ == "__main__":
    spec_from_architect = """
    MODULE_NAME: DATABASE_HANDLER
    FUNCTIONS:
      - save_receipt(receipt_text: str) -> bool
        description: Saves to local directory.
      - check_directory() -> bool
        description: Checks if directory exists.
    MOCK_INPUT: {"receipt_text": "Hello World!", "directory_path": "./receipts"}
    """

    code = run_developer(spec_from_architect)

    filename = "database_handler.py"
    with open(filename, "w", encoding="utf-8") as f:
        f.write(code)

    print(f">> Module saved to '{filename}'")
