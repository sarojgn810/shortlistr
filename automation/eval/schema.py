"""Evaluation JSON schema v1."""

SCHEMA_V1 = {
    "type": "object",
    "required": ["score", "legitimacy", "company", "role", "blocks"],
    "properties": {
        "score": {"type": "number", "minimum": 0, "maximum": 5},
        "legitimacy": {
            "enum": ["verified", "likely", "uncertain", "suspicious", "expired"],
        },
        "company": {"type": "string"},
        "role": {"type": "string"},
        "blocks": {
            "type": "object",
            "properties": {
                "A": {"type": "string"},
                "B": {"type": "string"},
                "C": {"type": "string"},
                "D": {"type": "string"},
                "E": {"type": "string"},
                "F": {"type": "string"},
                "G": {"type": "string"},
            },
        },
    },
}
