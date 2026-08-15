"""Evaluation JSON schema v1."""

SCHEMA_V1 = {
    "type": "object",
    # must_haves is required because the score is derived from it. Left
    # optional, a response that skipped the requirement list still validated,
    # and the scorer quietly fell back to the model's own number — which is the
    # thing being replaced.
    "required": ["score", "legitimacy", "company", "role", "blocks", "must_haves"],
    "properties": {
        "score": {"type": "number", "minimum": 0, "maximum": 5},
        "must_haves": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["req", "met"],
                "properties": {
                    "req": {"type": "string"},
                    "met": {"type": "boolean"},
                    "evidence": {"type": "string"},
                },
            },
        },
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
