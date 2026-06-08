"""
Skills package.

Each skill module should:
1. Define an `execute(params: dict) -> dict` function
2. Register itself via skill_registry.register_skill()
"""

# Import all skill modules so they self-register on package load
from skills import bronze_to_silver  # noqa: F401
from skills import read_view          # noqa: F401
from skills import create_view        # noqa: F401
from skills import create_backup      # noqa: F401
from skills import share_to_space     # noqa: F401
from skills import create_association  # noqa: F401
from skills import add_columns  # noqa: F401
from skills import create_transformation_flow  # noqa: F401
