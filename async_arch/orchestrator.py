import asyncio
import sys
from typing import List, Dict, Any
from pathlib import Path

try:
    from .state_manager import RedisStateManager
except ImportError:
    from state_manager import RedisStateManager

class AsyncOrchestrator:
    def __init__(self, redis_url: str = "mock"):
        self.state_manager = RedisStateManager(redis_url)
        self.running = True

    async def initialize(self):
        await self.state_manager.connect()
        # Optional: Start listening for events in background
        asyncio.create_task(self.state_manager.listen(
            ["TASK_COMPLETED", "TASK_FAILED"], 
            self.handle_event
        ))

    async def handle_event(self, channel: str, data: Dict):
        """Reactive event handler."""
        print(f"[EVENT] Received on {channel}: {data}")
        if channel == "TASK_FAILED":
            # Handle failure (e.g., trigger debugger)
            pass

    async def run_pipeline(self, idea: str):
        """
        Main entry point for the event-driven pipeline.
        """
        await self.initialize()
        print(f"[PIPELINE] Starting Async Pipeline for: {idea}")

        try:
            # Phase 1: Analyst (Sequential)
            print("[Orchestrator] Running Analyst...")
            blueprint = await self.invoke_agent("Analyst", {"idea": idea})
            await self.state_manager.set_state("project:blueprint", blueprint)

            # Phase 2: Architect (Sequential - defines contracts)
            print("[Orchestrator] Running Architect...")
            specs = await self.invoke_agent("Architect", blueprint)
            await self.state_manager.set_state("project:specs", specs)

            # Phase 3: Parallel Development (The Core Optimization)
            print("[Orchestrator] Spawning Parallel Developers...")
            
            # Example specs structure: {"frontend": {...}, "backend": {...}, "auth": {...}}
            tasks = []
            for module_name, module_spec in specs.get("modules", {}).items():
                # Launch independent developer tasks
                task = self.run_developer_lifecycle(module_name, module_spec)
                tasks.append(task)

            # Wait for all developers to finish
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Phase 4: Integration
            print("[Orchestrator] Running Integrator...")
            final_app = await self.invoke_agent("Integrator", results)
            
            print("[SUCCESS] Project Generation Complete!")
            return final_app

        except Exception as e:
            print(f"[ERROR] Pipeline Error: {e}")
        finally:
            await self.state_manager.close()

    async def run_developer_lifecycle(self, module_name: str, spec: Dict):
        """
        Manages the lifecycle of a single module development:
        Generate -> Review -> Fix -> Commit
        """
        try:
            print(f"   [START] Dev: {module_name}")
            
            # 1. Generate Code
            code = await self.invoke_agent("Developer", spec)
            
            # 2. Save State
            await self.state_manager.set_state(f"module:{module_name}:code", code)
            
            # 3. Publish Completion Event
            await self.state_manager.publish_event("TASK_COMPLETED", {
                "module": module_name,
                "status": "success"
            })
            
            print(f"   [DONE] Dev: {module_name}")
            return code
            
        except Exception as e:
            await self.state_manager.publish_event("TASK_FAILED", {
                "module": module_name,
                "error": str(e)
            })
            raise e

    async def invoke_agent(self, role: str, data: Any) -> Any:
        """
        Mock for calling an LLM agent. 
        In production, this would call the specific agent script or API.
        """
        # Simulate async work
        delay = 2 if role == "Developer" else 1
        await asyncio.sleep(delay)
        
        # Mock responses
        if role == "Architect":
            return {
                "modules": {
                    "frontend": {"type": "web", "tech": "React"},
                    "backend": {"type": "api", "tech": "Flask"},
                    "utils": {"type": "lib", "tech": "Python"}
                }
            }
        return {"mock_output": f"Result from {role}"}

# Entry point for testing
# if __name__ == "__main__":
#     orchestrator = AsyncOrchestrator()
#     asyncio.run(orchestrator.run_pipeline("Super Fast Async App"))
