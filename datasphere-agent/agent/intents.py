"""
Intent detection module.

Maps a user prompt to a known intent (skill name).
Uses simple keyword matching – no NLP dependencies needed.
"""

# Each intent is defined as a list of trigger keywords/phrases.
# If ALL keywords in a group are found in the user prompt, the intent matches.
INTENT_MAP: dict[str, list[list[str]]] = {
    "bronze_to_silver": [
        ["bronze", "silver"],          # "move bronze table to silver"
        ["raw", "cleansed"],           # "transform raw data to cleansed"
        ["landing", "harmonized"],     # alternate SAP Datasphere terminology
    ],
    "read_view": [
        ["read", "view"],             # "read view ADSO_Sales..."
        ["select", "view"],           # "select from view"
        ["query", "view"],            # "query the view"
        ["sales", "document"],        # "show sales document data"
        ["adso"],                     # "read ADSO data"
    ],
    "create_view": [
        ["create", "view"],           # "create a view"
        ["new", "view"],              # "new view for sales"
        ["define", "view"],           # "define a view"
    ],
    "share_to_space": [
        ["share", "view"],            # "share view to another space"
        ["share", "space"],           # "share to space"
        ["share", "object"],          # "share object"
    ],
}


def detect_intent(user_prompt: str) -> str | None:
    """
    Scan the user prompt against known keyword groups.
    Returns the first matching intent name, or None.
    """
    prompt_lower = user_prompt.lower()

    for intent_name, keyword_groups in INTENT_MAP.items():
        for keywords in keyword_groups:
            # All keywords in the group must appear in the prompt
            if all(kw in prompt_lower for kw in keywords):
                return intent_name

    return None
