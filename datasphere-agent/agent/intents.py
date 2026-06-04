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
    "create_backup": [
        ["backup", "view"],           # "backup view SV_SALES"
        ["backup", "before"],         # "backup before modifying"
        ["create", "backup"],         # "create backup for SV_SALES"
        ["backup"],                   # "backup SV_SALES"
    ],
    "create_sql_view_with_association": [
        ["sql", "view", "association"],     # "create sql view with association"
        ["billing", "association"],         # "billing document association"
        ["sv_", "billingdocument"],         # "sv_ billingdocument"
        ["sql view", "companycode"],        # "sql view companycode"
    ],
    "create_association": [
        ["create", "association"],          # "create an association"
        ["add", "association"],             # "add association to view"
        ["association", "navigation"],     # "association navigation link"
    ],
    "create_transformation_flow": [
        ["transformation flow"],                        # "create transformation flow"
        ["create", "tf_"],                              # "create TF_BILLING"
        ["aggregated", "flow"],                         # "aggregated flow on billing"
        ["transformation flow", "billing"],             # domain-specific
        ["without", "billing document", "aggregated"],  # matches user phrasing
    ],
    "add_calculated_fields": [
        ["calculated", "field"],            # "add calculated field"
        ["calculated", "column"],           # "calculated column"
        ["gross", "amount"],                # "gross amount"
        ["quantity", "category"],           # "quantity category"
        ["add", "formula"],                 # "add formula to view"
        ["netamount", "taxamount"],         # direct field reference
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
