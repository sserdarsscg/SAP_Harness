"""
Entry point for the Datasphere Agent.

Usage:
    python main.py "move bronze customer table to silver"

Flow:
    User Prompt → Planner → Skill → Executor → Output
"""

# Import skills package first so all skills self-register
import skills  # noqa: F401

from cli import get_user_prompt
from agent.planner import plan_and_execute


def main() -> None:
    user_prompt = get_user_prompt()
    print(f"\n[Agent] User prompt: \"{user_prompt}\"\n")

    result = plan_and_execute(user_prompt)
    print(f"\n{result}")


if __name__ == "__main__":
    main()
