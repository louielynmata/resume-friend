import base64
import re
from pathlib import Path
from typing import TypeVar

import httpx
from pydantic import BaseModel

from ..config import settings


StructuredResultT = TypeVar("StructuredResultT", bound=BaseModel)


async def generate_content(provider: str, system_prompt: str, user_prompt: str) -> str:
    if provider == "claude":
        return await _call_claude(system_prompt, user_prompt)
    elif provider == "openai":
        return await _call_openai(system_prompt, user_prompt)
    elif provider == "ollama":
        return await _call_ollama(system_prompt, user_prompt)
    else:
        raise ValueError(f"Unknown AI provider: {provider!r}. Must be claude, openai, or ollama.")


async def generate_structured(
    provider: str,
    system_prompt: str,
    user_prompt: str,
    response_model: type[StructuredResultT],
    *,
    image_paths: list[Path] | None = None,
) -> StructuredResultT:
    """Generate a schema-validated response, optionally with page images."""
    images = image_paths or []
    if provider == "claude":
        return await _call_claude_structured(
            system_prompt, user_prompt, response_model, images
        )
    if provider == "openai":
        return await _call_openai_structured(
            system_prompt, user_prompt, response_model, images
        )
    if provider == "ollama":
        return await _call_ollama_structured(
            system_prompt, user_prompt, response_model, images
        )
    raise ValueError(
        f"Unknown AI provider: {provider!r}. Must be claude, openai, or ollama."
    )


async def _call_claude(system_prompt: str, user_prompt: str) -> str:
    if not settings.anthropic_api_key:
        raise ValueError("ANTHROPIC_API_KEY is not set in .env")
    import anthropic
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    message = await client.messages.create(
        model=settings.claude_model,
        max_tokens=4096,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )
    return message.content[0].text


async def _call_openai(system_prompt: str, user_prompt: str) -> str:
    if not settings.openai_api_key:
        raise ValueError("OPENAI_API_KEY is not set in .env")
    import openai
    client = openai.AsyncOpenAI(api_key=settings.openai_api_key)
    response = await client.chat.completions.create(
        model=settings.openai_model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        max_tokens=4096,
    )
    return response.choices[0].message.content


async def _call_ollama(system_prompt: str, user_prompt: str) -> str:
    async with httpx.AsyncClient(timeout=180.0) as client:
        response = await client.post(
            f"{settings.ollama_base_url}/api/chat",
            json={
                "model": settings.ollama_model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "stream": False,
                "think": settings.ollama_think,
            },
        )
        response.raise_for_status()
        return response.json()["message"]["content"]


async def _call_claude_structured(
    system_prompt: str,
    user_prompt: str,
    response_model: type[StructuredResultT],
    image_paths: list[Path],
) -> StructuredResultT:
    if not settings.anthropic_api_key:
        raise ValueError("ANTHROPIC_API_KEY is not set in .env")
    import anthropic

    content: list[dict] = []
    for path in image_paths:
        content.append(
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",
                    "data": base64.b64encode(path.read_bytes()).decode("ascii"),
                },
            }
        )
    content.append({"type": "text", "text": user_prompt})

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    response = await client.messages.parse(
        model=settings.claude_model,
        max_tokens=8192,
        system=system_prompt,
        messages=[{"role": "user", "content": content}],
        output_format=response_model,
    )
    if response.parsed_output is None:
        raise ValueError("Claude returned no parsed structured output.")
    return response.parsed_output


async def _call_openai_structured(
    system_prompt: str,
    user_prompt: str,
    response_model: type[StructuredResultT],
    image_paths: list[Path],
) -> StructuredResultT:
    if not settings.openai_api_key:
        raise ValueError("OPENAI_API_KEY is not set in .env")
    import openai

    content: list[dict] = [{"type": "input_text", "text": user_prompt}]
    for path in image_paths:
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        content.append(
            {
                "type": "input_image",
                "image_url": f"data:image/png;base64,{encoded}",
                "detail": "high",
            }
        )

    client = openai.AsyncOpenAI(api_key=settings.openai_api_key)
    response = await client.responses.parse(
        model=settings.openai_model,
        instructions=system_prompt,
        input=[{"role": "user", "content": content}],
        max_output_tokens=8192,
        text_format=response_model,
    )
    if response.output_parsed is None:
        raise ValueError("OpenAI returned no parsed structured output.")
    return response.output_parsed


async def _call_ollama_structured(
    system_prompt: str,
    user_prompt: str,
    response_model: type[StructuredResultT],
    image_paths: list[Path],
) -> StructuredResultT:
    user_message: dict = {"role": "user", "content": user_prompt}
    if image_paths:
        user_message["images"] = [
            base64.b64encode(path.read_bytes()).decode("ascii")
            for path in image_paths
        ]

    async with httpx.AsyncClient(timeout=240.0) as client:
        response = await client.post(
            f"{settings.ollama_base_url}/api/chat",
            json={
                "model": settings.ollama_model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    user_message,
                ],
                "stream": False,
                "format": response_model.model_json_schema(),
            },
        )
        response.raise_for_status()
        content = response.json()["message"]["content"].strip()
        fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", content, re.DOTALL)
        if fenced:
            content = fenced.group(1)
        return response_model.model_validate_json(content)
