import httpx
from ..config import settings


async def generate_content(provider: str, system_prompt: str, user_prompt: str) -> str:
    if provider == "claude":
        return await _call_claude(system_prompt, user_prompt)
    elif provider == "openai":
        return await _call_openai(system_prompt, user_prompt)
    elif provider == "ollama":
        return await _call_ollama(system_prompt, user_prompt)
    else:
        raise ValueError(f"Unknown AI provider: {provider!r}. Must be claude, openai, or ollama.")


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
            },
        )
        response.raise_for_status()
        return response.json()["message"]["content"]
