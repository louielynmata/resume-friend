"""Temporary, read-only diagnostic for Resume Friend's Ollama prompt."""

from __future__ import annotations

import asyncio
import importlib
import json
import time
import urllib.request
from pathlib import Path

from backend.schemas import GenerateRequest


ROOT = Path(__file__).resolve().parents[1]
OLLAMA_URL = "http://localhost:11434"


def post(path: str, payload: dict, timeout: int = 600) -> dict:
    request = urllib.request.Request(
        f"{OLLAMA_URL}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


def get(path: str, timeout: int = 30) -> dict:
    with urllib.request.urlopen(f"{OLLAMA_URL}{path}", timeout=timeout) as response:
        return json.load(response)


async def capture_application_prompt() -> tuple[str, str]:
    generate_module = importlib.import_module("backend.routers.generate")
    captured: dict[str, str] = {}

    async def capture(provider: str, system_prompt: str, user_prompt: str) -> str:
        captured["system"] = system_prompt
        captured["user"] = user_prompt
        raise RuntimeError("prompt captured")

    generate_module.generate_content = capture
    jd_path = (
        ROOT
        / "outputs"
        / "Ashby_JuniorDesignEngineer_2026-07-08"
        / "job_description.txt"
    )
    request = GenerateRequest(
        job_description=jd_path.read_text(encoding="utf-8"),
        ai_provider="ollama",
        job_type="design",
        position="Junior Design Engineer",
        company="Ashby",
    )
    try:
        await generate_module.generate(request)
    except Exception as exc:
        if "system" not in captured:
            raise RuntimeError(f"failed before prompt capture: {exc!r}") from exc
    return captured["system"], captured["user"]


def loaded_model(model: str) -> dict:
    for item in get("/api/ps").get("models", []):
        if item.get("model") == model or item.get("name") == model:
            return {
                "allocated_bytes": item.get("size"),
                "vram_bytes": item.get("size_vram"),
                "context_length": item.get("context_length"),
            }
    return {}


def timed_chat(model: str, messages: list[dict], options: dict, think: bool) -> dict:
    started = time.perf_counter()
    result = post(
        "/api/chat",
        {
            "model": model,
            "messages": messages,
            "stream": False,
            "think": think,
            "keep_alive": "5m",
            "options": options,
        },
    )
    elapsed = time.perf_counter() - started
    return {
        "wall_seconds": round(elapsed, 2),
        "prompt_tokens": result.get("prompt_eval_count"),
        "output_tokens": result.get("eval_count"),
        "prompt_tokens_per_second": round(
            result.get("prompt_eval_count", 0)
            / max(result.get("prompt_eval_duration", 1) / 1_000_000_000, 0.001),
            2,
        ),
        "output_tokens_per_second": round(
            result.get("eval_count", 0)
            / max(result.get("eval_duration", 1) / 1_000_000_000, 0.001),
            2,
        ),
        "done_reason": result.get("done_reason"),
        "content": result.get("message", {}).get("content", ""),
        "thinking_chars": len(result.get("message", {}).get("thinking", "")),
    }


def score_grounded_response(text: str) -> dict:
    lowered = text.lower()
    return {
        "all_required_tags": all(
            tag in text
            for tag in (
                "<SUMMARY>",
                "</SUMMARY>",
                "<BULLETS>",
                "</BULLETS>",
                "<QA>",
                "</QA>",
            )
        ),
        "kept_supported_metric": "30%" in text,
        "kept_acceptance_facts": "14" in text and "11" in text,
        "flags_unsupported_react": "react: unsupported" in lowered,
        "flags_unsupported_aws": "aws: unsupported" in lowered,
        "flags_no_certification": "certification: none" in lowered,
        "no_forbidden_dash": "—" not in text and "–" not in text,
        "no_unapproved_metric": not any(
            metric in text for metric in ("10%", "20%", "40%", "50%", "100%")
        ),
    }


def main() -> None:
    system_prompt, user_prompt = asyncio.run(capture_application_prompt())
    app_messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    print(
        json.dumps(
            {
                "event": "assembled_prompt",
                "system_chars": len(system_prompt),
                "user_chars": len(user_prompt),
                "total_chars": len(system_prompt) + len(user_prompt),
            }
        ),
        flush=True,
    )

    # Probe the app-sized prompt at Ollama's default context, then at 32K.
    for model in ("qwen3.5:9b", "gemma4:12b"):
        for context in (None, 32768):
            options = {"num_predict": 1, "temperature": 0, "seed": 42}
            if context is not None:
                options["num_ctx"] = context
            result = timed_chat(model, app_messages, options, think=False)
            result.pop("content", None)
            result.update(
                {
                    "event": "context_probe",
                    "model": model,
                    "requested_context": context or "ollama_default",
                    "loaded": loaded_model(model),
                }
            )
            print(json.dumps(result), flush=True)

    grounded_prompt = """You are evaluating a candidate using ONLY the evidence below.

EVIDENCE
- Alex Chen was a Product Designer at Northstar Studio from May 2022 to October 2025.
- Alex used Figma and conducted a WCAG 2.1 AA accessibility audit.
- The audit recommended 14 changes; 11 were accepted. The evidence does not say they were deployed.
- Alex reduced design-to-development handoff time by 30%.
- Alex completed one Python course in 2024 but has no professional software engineering experience.
- Alex has no stated React, AWS, or PMP experience and no stated certification.

TARGET JOB
The role asks for Figma, accessibility, React, AWS, and a PMP certification.

Return exactly these three XML sections and nothing else:
<SUMMARY>Exactly two concise sentences grounded in the evidence.</SUMMARY>
<BULLETS>Exactly three lines beginning with the bullet character ●. Use the 30% metric and distinguish recommended from accepted accessibility changes.</BULLETS>
<QA>Exactly these lines:
REACT: SUPPORTED or REACT: UNSUPPORTED
AWS: SUPPORTED or AWS: UNSUPPORTED
CERTIFICATION: the certification name or CERTIFICATION: NONE
</QA>

Do not invent facts or metrics. Do not use em dashes or en dashes."""
    grounded_messages = [{"role": "user", "content": grounded_prompt}]

    for model in ("qwen3.5:9b", "gemma4:12b"):
        result = timed_chat(
            model,
            grounded_messages,
            {
                "num_ctx": 8192,
                "num_predict": 700,
                "temperature": 0,
                "seed": 42,
            },
            think=True,
        )
        content = result.pop("content")
        result.update(
            {
                "event": "grounded_quality",
                "model": model,
                "score": score_grounded_response(content),
                "response_chars": len(content),
                "response_preview": content[:1200],
                "loaded": loaded_model(model),
            }
        )
        print(json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
