"""Target-role keyword packs for LinkedIn searchability.

Deterministic — no LLM required. Packs mirror how recruiters actually search
(title variants + stack + domain + seniority), not buzzword soup.
"""

from __future__ import annotations

ROLE_PACKS: dict[str, dict] = {
    "sre": {
        "id": "sre",
        "label": "Site Reliability / Platform",
        "search_titles": [
            "Site Reliability Engineer",
            "SRE",
            "Staff SRE",
            "Principal SRE",
            "Platform Engineer",
            "Production Engineer",
            "DevOps Engineer",
            "Infrastructure Engineer",
        ],
        "must_keywords": [
            "kubernetes", "aws", "observability", "prometheus", "grafana",
            "incident", "on-call", "terraform", "cicd", "slo", "sla",
            "reliability", "automation", "linux",
        ],
        "nice_keywords": [
            "gcp", "azure", "helm", "istio", "datadog", "pagerduty",
            "chaos", "runbook", "ansible", "python", "golang", "kafka",
            "cost optimization", "platform engineering",
        ],
        "seniority": ["senior", "staff", "principal", "lead"],
        "impact_verbs": [
            "reduced", "improved", "automated", "scaled", "cut", "built",
            "owned", "led", "designed", "migrated",
        ],
        "headline_template": (
            "{seniority}Site Reliability Engineer | Kubernetes · AWS · Observability | "
            "SLOs, incident response & platform automation"
        ),
        "about_beats": [
            "Open with the role you want + years + domain.",
            "Name 3–5 stack keywords recruiters search.",
            "One paragraph of proof (systems owned, scale, reliability wins).",
            "Close with what you're looking for (role, location, remote).",
        ],
    },
    "devops": {
        "id": "devops",
        "label": "DevOps / Cloud Engineering",
        "search_titles": [
            "DevOps Engineer",
            "Cloud Engineer",
            "CI/CD Engineer",
            "Infrastructure Engineer",
            "Platform Engineer",
        ],
        "must_keywords": [
            "devops", "ci/cd", "aws", "docker", "kubernetes", "terraform",
            "jenkins", "github actions", "linux", "automation", "infrastructure",
        ],
        "nice_keywords": [
            "ansible", "prometheus", "grafana", "helm", "python", "bash",
            "gitlab", "argo", "monitoring", "security",
        ],
        "seniority": ["senior", "staff", "lead"],
        "impact_verbs": [
            "automated", "accelerated", "standardized", "reduced", "built",
            "migrated", "hardened",
        ],
        "headline_template": (
            "{seniority}DevOps Engineer | CI/CD · Cloud · Kubernetes | "
            "Shipping reliable infrastructure at scale"
        ),
        "about_beats": [
            "State DevOps/cloud focus and environments you've owned.",
            "List pipeline + IaC + cloud keywords.",
            "Quantify delivery speed or reliability improvements.",
            "Say the role/location you're open to.",
        ],
    },
    "fullstack": {
        "id": "fullstack",
        "label": "Full Stack Engineer",
        "search_titles": [
            "Full Stack Engineer",
            "Full Stack Developer",
            "Software Engineer",
            "Backend Engineer",
            "Frontend Engineer",
        ],
        "must_keywords": [
            "full stack", "javascript", "typescript", "react", "node",
            "api", "sql", "rest", "frontend", "backend",
        ],
        "nice_keywords": [
            "next.js", "python", "postgres", "graphql", "aws", "docker",
            "system design", "microservices",
        ],
        "seniority": ["senior", "staff", "lead"],
        "impact_verbs": [
            "shipped", "built", "launched", "improved", "scaled", "designed",
        ],
        "headline_template": (
            "{seniority}Full Stack Engineer | React · Node · APIs | "
            "Product-minded software delivery"
        ),
        "about_beats": [
            "Lead with full-stack scope and product domain.",
            "Name FE/BE stack clearly.",
            "Cite shipped features and user/business impact.",
            "State target role and work style.",
        ],
    },
    "ai_engineer": {
        "id": "ai_engineer",
        "label": "AI / ML Engineer",
        "search_titles": [
            "AI Engineer",
            "ML Engineer",
            "Machine Learning Engineer",
            "Applied Scientist",
            "LLM Engineer",
        ],
        "must_keywords": [
            "machine learning", "python", "llm", "nlp", "model",
            "pytorch", "tensorflow", "rag", "embeddings", "mlops",
        ],
        "nice_keywords": [
            "langchain", "vector", "fine-tuning", "transformers", "aws",
            "gpu", "evaluation", "prompt", "agents",
        ],
        "seniority": ["senior", "staff", "lead"],
        "impact_verbs": [
            "trained", "deployed", "improved", "built", "evaluated", "shipped",
        ],
        "headline_template": (
            "{seniority}AI/ML Engineer | LLMs · Python · MLOps | "
            "Production ML systems & evaluation"
        ),
        "about_beats": [
            "Name AI/ML focus (LLMs, classical ML, vision, etc.).",
            "List frameworks + production serving keywords.",
            "Show measurable model/product outcomes.",
            "Clarify the roles you're targeting.",
        ],
    },
    "backend": {
        "id": "backend",
        "label": "Backend / Systems",
        "search_titles": [
            "Backend Engineer",
            "Software Engineer",
            "Systems Engineer",
            "API Engineer",
        ],
        "must_keywords": [
            "backend", "api", "python", "java", "go", "microservices",
            "sql", "distributed", "scalability", "rest",
        ],
        "nice_keywords": [
            "kafka", "redis", "postgres", "grpc", "aws", "system design",
            "concurrency", "performance",
        ],
        "seniority": ["senior", "staff", "principal", "lead"],
        "impact_verbs": [
            "scaled", "designed", "optimized", "built", "reduced", "led",
        ],
        "headline_template": (
            "{seniority}Backend Engineer | APIs · Distributed systems | "
            "Reliable services at scale"
        ),
        "about_beats": [
            "Open with backend/systems focus.",
            "List languages + data + infra keywords.",
            "Quantify scale, latency, or reliability wins.",
            "State target seniority and location prefs.",
        ],
    },
}


def list_roles() -> list[dict]:
    return [
        {"id": p["id"], "label": p["label"], "search_titles": list(p["search_titles"])}
        for p in ROLE_PACKS.values()
    ]


def get_role(role_id: str) -> dict:
    key = (role_id or "sre").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "site_reliability": "sre",
        "site_reliability_engineer": "sre",
        "ml": "ai_engineer",
        "ml_engineer": "ai_engineer",
        "ai": "ai_engineer",
        "full_stack": "fullstack",
        "full-stack": "fullstack",
    }
    key = aliases.get(key, key)
    return ROLE_PACKS.get(key) or ROLE_PACKS["sre"]
