"""
CLI module – parses command-line arguments and invokes the planner.
Separated from main.py so the logic can be imported/tested independently.
"""

import sys


def get_user_prompt() -> str:
    """
    Read the user prompt from the first CLI argument.
    Exits with usage info if no argument is provided.
    """
    if len(sys.argv) < 2:
        print("Usage: python main.py \"<your prompt>\"")
        print("Example: python main.py \"move bronze customer table to silver\"")
        sys.exit(1)

    return sys.argv[1]
