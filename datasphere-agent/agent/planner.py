"""
Planner – orchestrates the full flow:
  User Prompt → Intent Detection → Skill Execution → Executor → Output
"""

from agent.intents import detect_intent
from agent.skill_registry import get_skill


def plan_and_execute(user_prompt: str) -> str:
    """
    Main entry point for the agent pipeline.
    1. Detect user intent from the prompt
    2. Resolve the matching skill
    3. Execute the skill (which calls the executor internally)
    4. Return a human-readable result
    """

    # Step 1: Intent detection
    intent = detect_intent(user_prompt)
    if intent is None:
        return f"[Planner] No matching intent found for: '{user_prompt}'"

    print(f"[Planner] Detected intent: {intent}")

    # Step 2: Retrieve registered skill
    skill_fn = get_skill(intent)
    if skill_fn is None:
        return f"[Planner] Intent '{intent}' matched but no skill is registered."

    # Step 3: Execute skill – pass the raw prompt as context
    result = skill_fn({"user_prompt": user_prompt})

    # Step 4: Format output
    status = result.get("status", "unknown")
    output = result.get("output", "")
    return f"[Planner] Skill '{intent}' completed with status: {status}\n{output}"
