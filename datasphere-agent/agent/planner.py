"""
Planner – orchestrates the full flow:
  User Prompt → Intent Detection → Skill Execution → Executor → Output
"""

from agent.intents import detect_intent
from agent.skill_registry import get_skill
from agent.governance_guard import validate_skill_call, log_skill_action


def plan_and_execute(
    user_prompt: str,
    confirm: bool = False,
    acknowledge_ai: bool = False,
) -> str:
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

    # Step 3: Governance pre-check before any skill execution.
    params = {
        "user_prompt": user_prompt,
        "confirm": confirm,
        "acknowledge_ai": acknowledge_ai,
    }
    validation = validate_skill_call(intent, params)
    if not validation.get("allowed"):
        log_skill_action(
            skill_name=intent,
            params=params,
            validation=validation,
            output="Execution blocked by governance guard.",
            result="blocked",
        )
        return (
            f"[Planner] Governance validation failed for skill '{intent}'.\n"
            f"Errors: {validation.get('errors', [])}"
        )

    # Step 4: Execute skill – pass the validated prompt context.
    result = skill_fn(validation.get("normalized_arguments", params))

    status = result.get("status", "unknown")
    output = result.get("output", "")
    exec_result = "success" if str(status).lower() in {"ok", "success"} else "failed"
    log_skill_action(
        skill_name=intent,
        params=params,
        validation=validation,
        output=str(output),
        result=exec_result,
    )

    # Step 5: Format output
    return f"[Planner] Skill '{intent}' completed with status: {status}\n{output}"
