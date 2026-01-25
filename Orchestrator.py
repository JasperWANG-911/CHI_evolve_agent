import httpx
import asyncio
import json
from pathlib import Path
from typing import Dict, List, Optional, Any
import logging


class Orchestrator:
    """
    Main orchestrator that coordinates all agents.

    Enhanced with Capability Gatekeeping workflow:
    - Can set function library level for experiments
    - Detects capability gaps before code generation
    - Handles PR workflow for new function proposals
    - Waits for human review when needed
    """

    def __init__(self, function_level: str = "full"):
        """
        Initialize orchestrator.

        Args:
            function_level: Initial function library level ("minimal", "partial", "full")
        """
        self.agents = {
            "execution": "http://localhost:8001",
            "pr_review": "http://localhost:8002",
            "scene_planning": "http://localhost:8003",
            "coding": "http://localhost:8004"
        }
        self.project_root = Path(__file__).parent
        self.logger = self._setup_logger()
        self.timeout = httpx.Timeout(1000, connect=10.0)
        self.current_combination = None
        self.total_steps = 0

        # Capability gatekeeping settings
        self.function_level = function_level
        self.enable_capability_check = True
        self.auto_propose_functions = True
        self.pending_prs = []

        # Review queue paths
        self.review_queue_dir = self.project_root / "review_queue"
        
    def _setup_logger(self):
        logger = logging.getLogger('Orchestrator')
        logger.setLevel(logging.INFO)
        handler = logging.StreamHandler()
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        return logger
    
    async def check_agents_health(self):
        """Check if all agents are running"""
        for name, url in self.agents.items():
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.get(f"{url}/health")
                    if response.status_code == 200:
                        self.logger.info(f"✓ {name} agent is healthy")
                    else:
                        self.logger.error(f"✗ {name} agent is unhealthy")
                        return False
            except Exception as e:
                self.logger.error(f"✗ {name} agent is not reachable: {e}")
                return False
        return True

    async def set_function_library_level(self, level: str):
        """Set the function library level in coding agent"""
        self.function_level = level
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.agents['coding']}/set-library-level",
                json={"level": level}
            )
        result = response.json()
        if result.get("success"):
            self.logger.info(f"Function library level set to: {level}")
        else:
            self.logger.error(f"Failed to set library level: {result}")
        return result

    async def get_library_status(self) -> Dict[str, Any]:
        """Get current function library status"""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(f"{self.agents['coding']}/library-status")
        return response.json()

    async def check_capabilities(self, task_description: str) -> Dict[str, Any]:
        """Check if current function library can handle the task"""
        self.logger.info("Checking capability coverage...")
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.agents['coding']}/check-capabilities",
                json={"task_description": task_description}
            )
        result = response.json()
        if result.get("has_gaps"):
            self.logger.warning(f"Capability gaps detected! Coverage: {result['coverage']['coverage_rate']*100:.1f}%")
            for gap in result['coverage']['gaps']:
                self.logger.warning(f"  Missing: {gap['required_capability']} for {gap['action']}")
        else:
            self.logger.info(f"Full capability coverage: {result['coverage']['coverage_rate']*100:.1f}%")
        return result

    async def propose_and_submit_functions(self, task_description: str) -> Dict[str, Any]:
        """Check capabilities and propose new functions if needed"""
        self.logger.info("Running capability check and proposal workflow...")
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.agents['coding']}/check-and-propose",
                json={"task_description": task_description}
            )
        result = response.json()

        if result.get("submitted_prs"):
            for pr in result["submitted_prs"]:
                self.pending_prs.append(pr["pr_id"])
                self.logger.info(f"Submitted PR: {pr['pr_id']} for {pr.get('message', 'new function')}")

        return result

    async def review_proposed_function(self, pr_id: str, submission: Dict[str, Any]) -> Dict[str, Any]:
        """Send a function proposal to PR Review Agent"""
        self.logger.info(f"Sending {pr_id} to PR Review Agent...")
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.agents['pr_review']}/review",
                json=submission
            )
        result = response.json()
        self.logger.info(f"PR Review result: {result.get('decision')} - {result.get('recommendation_reason')}")
        return result

    async def handle_capability_gap(self, task_description: str) -> Dict[str, Any]:
        """
        Handle capability gaps in the function library.

        Workflow:
        1. Check capabilities
        2. If gaps, propose new functions
        3. Send to PR Review Agent
        4. Add to human review queue
        5. Return status

        Returns:
            {
                "has_gaps": bool,
                "gaps_handled": bool,
                "pending_human_review": List of PR IDs,
                "auto_approved": List of PR IDs,
                "auto_rejected": List of PR IDs
            }
        """
        # Step 1-2: Check capabilities and propose
        proposal_result = await self.propose_and_submit_functions(task_description)

        if not proposal_result.get("coverage", {}).get("has_gaps", False):
            return {
                "has_gaps": False,
                "gaps_handled": True,
                "pending_human_review": [],
                "auto_approved": [],
                "auto_rejected": []
            }

        pending_human = []
        auto_approved = []
        auto_rejected = []

        # Step 3: Send each proposal to PR Review Agent
        for i, proposal in enumerate(proposal_result.get("proposals", [])):
            if "error" in proposal:
                self.logger.error(f"Proposal error: {proposal['error']}")
                continue

            pr_result = proposal_result.get("submitted_prs", [])[i] if i < len(proposal_result.get("submitted_prs", [])) else None
            if not pr_result:
                continue

            pr_id = pr_result["pr_id"]

            # Build submission for PR Review
            submission = {
                "pr_id": pr_id,
                "function_name": proposal["function_name"],
                "function_code": proposal["function_code"],
                "description": proposal["description"],
                "parameters": proposal.get("parameters", []),
                "returns": proposal.get("returns", "None"),
                "context": proposal.get("context", "")
            }

            # Send to PR Review Agent
            review_result = await self.review_proposed_function(pr_id, submission)

            decision = review_result.get("decision", "needs_human_review")

            if decision == "recommend_approve":
                # Still needs human confirmation, but marked as recommended
                pending_human.append(pr_id)
            elif decision == "auto_reject":
                auto_rejected.append(pr_id)
                self.logger.info(f"Auto-rejected {pr_id}: {review_result.get('recommendation_reason')}")
            else:
                pending_human.append(pr_id)

        return {
            "has_gaps": True,
            "gaps_handled": len(pending_human) > 0 or len(auto_rejected) > 0,
            "pending_human_review": pending_human,
            "auto_approved": auto_approved,
            "auto_rejected": auto_rejected
        }

    async def check_human_reviews(self) -> List[Dict[str, Any]]:
        """Check for completed human reviews"""
        pending_path = self.review_queue_dir / "pending_reviews.json"
        if not pending_path.exists():
            return []

        with open(pending_path, 'r') as f:
            pending = json.load(f)

        completed = [r for r in pending if r.get("human_decision")]
        return completed

    async def process_approved_functions(self) -> List[str]:
        """Process any newly approved functions"""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.agents['coding']}/process-approved-functions"
            )
        result = response.json()
        approved = result.get("approved_functions", [])
        if approved:
            self.logger.info(f"Processed {len(approved)} approved functions: {approved}")
        return approved

    async def wait_for_human_review(self, pr_ids: List[str], timeout_seconds: int = 300) -> bool:
        """
        Wait for human to review pending PRs.

        In practice, this polls the review queue. For the research study,
        humans edit the JSON file directly.

        Args:
            pr_ids: List of PR IDs waiting for review
            timeout_seconds: How long to wait

        Returns:
            True if all PRs were reviewed, False if timeout
        """
        if not pr_ids:
            return True

        self.logger.info(f"Waiting for human review of {len(pr_ids)} PRs...")
        self.logger.info(f"Please edit: {self.review_queue_dir / 'pending_reviews.json'}")
        self.logger.info("Set 'human_decision' to 'approve' or 'reject' for each PR")

        elapsed = 0
        check_interval = 5

        while elapsed < timeout_seconds:
            completed = await self.check_human_reviews()
            completed_ids = {r["pr_id"] for r in completed}

            if all(pr_id in completed_ids for pr_id in pr_ids):
                self.logger.info("All PRs reviewed!")
                # Process the approved ones
                await self.process_approved_functions()
                return True

            await asyncio.sleep(check_interval)
            elapsed += check_interval

            if elapsed % 30 == 0:
                self.logger.info(f"Still waiting for human review... ({elapsed}s elapsed)")

        self.logger.warning(f"Timeout waiting for human review after {timeout_seconds}s")
        return False
    
    async def plan_scene(self, description: str, assets_csv_path: str, num_combinations: int = 1):
        """Step 1: Use scene planning agent to parse description and generate combinations"""
        self.logger.info("Planning scene...")
        
        # Convert to absolute path
        abs_path = str(Path(assets_csv_path).absolute())
        self.logger.info(f"Using assets CSV at: {abs_path}")
        
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.agents['scene_planning']}/plan-scene",
                json={
                    "description": description,
                    "assets_csv_path": abs_path,
                    "num_combinations": num_combinations
                }
            )
            
        result = response.json()
        if not result["success"]:
            self.logger.error(f"Scene planning failed: {result.get('error', 'Unknown error')}")
            if "missing_assets" in result:
                self.logger.error(f"Missing assets: {result['missing_assets']}")
            return None
            
        self.logger.info(f"Scene planning successful. Generated {result['total_combinations']} combinations")
        return result
    
    async def set_combination_in_coding_agent(self, combination: Dict):
        """Send combination data to coding agent"""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.agents['coding']}/set-combination",
                json={"combination": combination}
            )
        
        result = response.json()
        if not result["success"]:
            raise RuntimeError(f"Failed to set combination data: {result.get('message')}")
        
        self.logger.info("Combination data sent to coding agent")
    
    async def get_step_info(self, step_num: int) -> Dict:
        """Get information about a specific step from the generated code"""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.agents['coding']}/get-step-info",
                json={"step": step_num}
            )
        
        return response.json()
    
    async def execute_workflow_steps(self, combination: Dict):
        """Execute all workflow steps"""
        # First, send combination data to coding agent
        await self.set_combination_in_coding_agent(combination)

        # Generate complete code on step 1
        self.logger.info("Generating complete scene construction code...")

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.agents['coding']}/generate-code",
                json={
                    "step": 1,
                    "task_description": "Generate complete scene construction code with intelligent scaling",
                    "review_result": None
                }
            )

        code_result = response.json()
        if not code_result["success"]:
            self.logger.error(f"Code generation failed: {code_result['message']}")
            return False

        self.total_steps = code_result.get("total_steps", 0)
        self.logger.info(f"Generated code with {self.total_steps} steps")

        # Execute each step
        for step_num in range(1, self.total_steps + 1):
            self.logger.info(f"\n--- Executing Step {step_num}/{self.total_steps} ---")

            # Get the code for this specific step
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.agents['coding']}/get-step-code",
                    json={"step": step_num}
                )

            step_code_result = response.json()
            if not step_code_result["success"]:
                self.logger.error(f"Failed to get code for step {step_num}")
                return False

            step_code = step_code_result["code"]

            # Execute this step's code in Blender
            self.logger.info(f"Executing step {step_num} code in Blender...")

            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.agents['execution']}/run-step-code",
                    json={
                        "code": step_code,
                        "capture_views": False
                    }
                )

            exec_result = response.json()
            if not exec_result.get("ok", False):
                error_msg = exec_result.get('error') or exec_result.get('result', {}).get('error', 'Unknown error')
                self.logger.error(f"Step {step_num} execution failed: {error_msg}")
                return False

            self.logger.info(f"✓ Step {step_num} executed successfully")

            # Short delay between steps
            await asyncio.sleep(0.5)

        # If we get here, all steps completed successfully
        return True

    async def generate_scene_for_combination(self, combination: Dict, combination_num: int):
        """Generate scene for a single combination"""
        self.logger.info(f"\n{'='*60}")
        self.logger.info(f"Generating scene for combination {combination_num}")
        self.logger.info(f"Objects in this combination:")
        for obj in combination["objects"]:
            self.logger.info(f"  - {obj['instance_id']}: {obj['file_name']}")
        self.logger.info(f"{'='*60}")
        
        # Clear any existing execution_code.py to start fresh
        execution_code_path = Path("execution_code.py")
        if execution_code_path.exists():
            execution_code_path.unlink()
            self.logger.info("Cleared existing execution_code.py")
        
        # Store combination data
        self.current_combination = combination
        
        # Execute workflow steps with combination data
        success = await self.execute_workflow_steps(combination)
        
        if success:
            self.logger.info(f"\n✓ Successfully generated scene for combination {combination_num}")
        else:
            self.logger.error(f"\n✗ Failed to generate scene for combination {combination_num}")
        
        return success
    
    async def run_workflow(self, description: str, assets_csv_path: str, num_combinations: int = 1):
        """Main workflow execution with capability gatekeeping"""
        self.logger.info("\n" + "="*80)
        self.logger.info("STARTING SCENE GENERATION WORKFLOW")
        self.logger.info("="*80)
        self.logger.info(f"Description: {description}")
        self.logger.info(f"Assets CSV: {assets_csv_path}")
        self.logger.info(f"Number of combinations: {num_combinations}")
        self.logger.info(f"Function library level: {self.function_level}")

        # Check all agents are healthy
        self.logger.info("\nChecking agent health...")
        if not await self.check_agents_health():
            self.logger.error("Not all agents are healthy. Aborting.")
            return {"success": False, "error": "Agents not healthy"}

        # Set function library level
        await self.set_function_library_level(self.function_level)
        library_status = await self.get_library_status()
        self.logger.info(f"Available functions: {library_status.get('total_available', 0)}")

        # Check capabilities if enabled
        if self.enable_capability_check:
            self.logger.info("\nStep 0: Capability Check")
            gap_result = await self.handle_capability_gap(description)

            if gap_result["has_gaps"]:
                self.logger.warning(f"Capability gaps detected!")

                if gap_result["pending_human_review"]:
                    self.logger.info(f"PRs pending human review: {gap_result['pending_human_review']}")

                    if self.auto_propose_functions:
                        # Wait for human to review
                        reviewed = await self.wait_for_human_review(
                            gap_result["pending_human_review"],
                            timeout_seconds=300
                        )
                        if not reviewed:
                            self.logger.warning("Proceeding without all reviews completed")

                if gap_result["auto_rejected"]:
                    self.logger.info(f"Auto-rejected PRs: {gap_result['auto_rejected']}")

        # Plan the scene
        self.logger.info("\nStep 1: Scene Planning")
        planning_result = await self.plan_scene(description, assets_csv_path, num_combinations)
        if not planning_result:
            return {"success": False, "error": "Scene planning failed"}

        # Process each combination
        combinations = planning_result["combinations"]
        successful_combinations = 0
        results = []

        for idx, combination in enumerate(combinations):
            combination_num = combination["combination_id"]

            success = await self.generate_scene_for_combination(combination, combination_num)
            results.append({
                "combination_id": combination_num,
                "success": success
            })

            if success:
                successful_combinations += 1

            # Add a delay between combinations if needed
            if idx < len(combinations) - 1:
                self.logger.info("\nWaiting before next combination...")
                await asyncio.sleep(5)

        # Final summary
        self.logger.info("\n" + "="*80)
        self.logger.info("WORKFLOW COMPLETED")
        self.logger.info(f"Successfully generated: {successful_combinations}/{len(combinations)} scenes")
        self.logger.info("="*80)

        return {
            "success": successful_combinations > 0,
            "total_combinations": len(combinations),
            "successful_combinations": successful_combinations,
            "results": results,
            "library_level": self.function_level
        }

async def main():
    import sys

    # Parse command line arguments
    # Usage: python Orchestrator.py [level] [description] [assets_csv] [num_combinations]
    # level: minimal, partial, full (default: full)

    function_level = "full"
    description = "A house with 2 trees"
    assets_csv_path = "assets/assets.csv"
    num_combinations = 1

    if len(sys.argv) > 1:
        function_level = sys.argv[1].lower()
        if function_level not in ["minimal", "partial", "full"]:
            print(f"Invalid level: {function_level}. Using 'full'")
            function_level = "full"

    if len(sys.argv) > 2:
        description = sys.argv[2]

    if len(sys.argv) > 3:
        assets_csv_path = sys.argv[3]

    if len(sys.argv) > 4:
        num_combinations = int(sys.argv[4])

    # Create orchestrator with specified function level
    orchestrator = Orchestrator(function_level=function_level)

    # Verify assets.csv exists
    if not Path(assets_csv_path).exists():
        print(f"Error: {assets_csv_path} not found!")
        print(f"Current directory: {Path.cwd()}")
        return

    result = await orchestrator.run_workflow(description, assets_csv_path, num_combinations)
    print(f"\nWorkflow result: {result}")


if __name__ == "__main__":
    asyncio.run(main())