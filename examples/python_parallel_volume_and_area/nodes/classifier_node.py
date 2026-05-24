from __future__ import annotations

import json
from typing import Any, Callable

from nodes.domain_registry import AVAILABLE_DOMAINS, DOMAIN_REGISTRY


def _build_classifier_response_format() -> dict[str, Any]:
    # Schema is generated from the domain registry so new domains can be added
    # in one place.
    return {
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "domain_route",
                "strict": True,
                "schema": {
                    "type": "object",
                    "properties": {
                        "selected_domains": {
                            "type": "array",
                            "items": {
                                "type": "string",
                                "enum": list(AVAILABLE_DOMAINS),
                            },
                            "minItems": 1,
                            "uniqueItems": True,
                        }
                    },
                    "required": ["selected_domains"],
                    "additionalProperties": False,
                },
            },
        }
    }


CLASSIFIER_RESPONSE_FORMAT = _build_classifier_response_format()


def _build_classifier_prompt() -> str:
    domain_bullets = "\n".join(f"- {domain}" for domain in AVAILABLE_DOMAINS)
    domain_examples = []
    for domain in AVAILABLE_DOMAINS:
        domain_examples.append(f"- {domain}-only request -> [\"{domain}\"]")

    if len(AVAILABLE_DOMAINS) > 1:
        combined_domains = "\", \"".join(AVAILABLE_DOMAINS)
        domain_examples.append(f"- asks for multiple domains -> [\"{combined_domains}\"]")

    examples_text = "\n".join(domain_examples)

    return f"""You are routing a geometry request inside a LangGraph workflow.
Choose one or more domains from this list:
{domain_bullets}

Select every domain needed to answer the request.
Examples:
{examples_text}

Return strictly valid JSON with exactly this shape:
{{
  \"selected_domains\": [\"{AVAILABLE_DOMAINS[0]}\", ...]
}}

Output rules:
- Return JSON only.
- Do not use markdown code fences.
- Do not add explanation before or after the JSON object.
"""


CLASSIFIER_PROMPT = _build_classifier_prompt()


def _strip_markdown_code_fence(content: str) -> str:
    stripped = content.strip()
    if not stripped.startswith("```"):
        return stripped

    lines = stripped.splitlines()
    if len(lines) < 3:
        return stripped
    if not lines[-1].strip().startswith("```"):
        return stripped

    return "\n".join(lines[1:-1]).strip()


def _normalize_content_text(content: Any) -> str:
    if isinstance(content, str):
        return content

    # Some providers return content blocks instead of a plain string.
    if isinstance(content, list):
        chunks: list[str] = []
        for block in content:
            if isinstance(block, str):
                chunks.append(block)
                continue
            if isinstance(block, dict):
                text = block.get("text")
                if isinstance(text, str):
                    chunks.append(text)
        return "\n".join(chunks)

    raise RuntimeError("Classifier response content must be a string or text blocks")


def _fallback_domains_from_prompt(user_prompt: str) -> list[str]:
    prompt_lower = user_prompt.lower()
    inferred: list[str] = []

    for domain in AVAILABLE_DOMAINS:
        registry_entry = DOMAIN_REGISTRY.get(domain, {})
        tokens = [domain]
        raw_tokens = registry_entry.get("tool_name_contains", [])
        if isinstance(raw_tokens, list):
            tokens.extend(str(token) for token in raw_tokens)

        if any(token.lower() in prompt_lower for token in tokens):
            inferred.append(domain)

    if inferred:
        return inferred

    # Keep the workflow running even when classification output is malformed.
    return [AVAILABLE_DOMAINS[0]]


def _parse_classifier_output(content: str) -> dict[str, Any]:
    cleaned = _strip_markdown_code_fence(content)
    if not cleaned.strip():
        raise RuntimeError("Classifier response was empty")

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Classifier response was not valid JSON: {exc}") from exc

    if isinstance(parsed, list):
        return {"selected_domains": parsed}
    if not isinstance(parsed, dict):
        raise RuntimeError("Classifier JSON response must be an object")
    return parsed


def create_classifier_node(llm: Any, dbg: Callable[[str], None]) -> Callable[[dict[str, Any]], dict[str, Any]]:
    """
    Build a very small node whose only job is to decide which domain workflow
    should run next.
    """

    def classifier_node(state: dict[str, Any]) -> dict[str, Any]:
        dbg("[graph][classify] Enter node")

        result = llm.invoke(
            [
                {"role": "system", "content": CLASSIFIER_PROMPT},
                {"role": "user", "content": state["user_prompt"]},
            ]
        )
        content = _normalize_content_text(result.content)

        try:
            parsed = _parse_classifier_output(content)
        except Exception as exc:
            dbg(f"[graph][classify] Parse error={exc}; falling back to prompt inference")
            selected_domains = _fallback_domains_from_prompt(state["user_prompt"])
            dbg(f"[graph][classify] Fallback decision={selected_domains}")
            return {"selected_domains": selected_domains}

        selected_domains = parsed.get("selected_domains")
        if not isinstance(selected_domains, list) or not selected_domains:
            dbg("[graph][classify] Missing/empty selected_domains; falling back to prompt inference")
            selected_domains = _fallback_domains_from_prompt(state["user_prompt"])
            dbg(f"[graph][classify] Fallback decision={selected_domains}")
            return {"selected_domains": selected_domains}

        allowed_domains = set(AVAILABLE_DOMAINS)
        normalized_domains: list[str] = []
        for domain in selected_domains:
            if not isinstance(domain, str):
                continue
            if domain not in allowed_domains:
                continue
            if domain not in normalized_domains:
                normalized_domains.append(domain)

        if not normalized_domains:
            dbg("[graph][classify] No supported domains from classifier output; falling back to prompt inference")
            normalized_domains = _fallback_domains_from_prompt(state["user_prompt"])

        dbg(f"[graph][classify] Decision={normalized_domains}")
        return {"selected_domains": normalized_domains}

    return classifier_node