"""
Entry point for the Datasphere Agent.

Usage:
    python main.py "<prompt>" [--yes]

    --yes   Pass confirm=True and acknowledge_ai=True (required for mutating skills
            such as create_view, create_backup, share_to_space).

Flow:
    User Prompt → Planner → Skill → Executor → Output
"""

import sys

# Import skills package first so all skills self-register
import skills  # noqa: F401

from agent.planner import plan_and_execute


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    yes = "--yes" in sys.argv

    if not args:
        print('Usage: python main.py "<prompt>" [--yes]')
        print('  --yes   required for mutating skills (create_backup, create_view, share_to_space)')
        sys.exit(1)

    user_prompt = args[0]
    print(f"\n[Agent] User prompt: \"{user_prompt}\"\n")
    if yes:
        print("[Agent] Running with confirm=True, acknowledge_ai=True\n")

    result = plan_and_execute(user_prompt, confirm=yes, acknowledge_ai=yes)
    print(f"\n{result}")


if __name__ == "__main__":
    main()
