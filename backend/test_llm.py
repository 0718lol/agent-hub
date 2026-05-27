import asyncio
from app.core.llm_client import llm_client
from app.main import _load_llm_config

print("configured:", llm_client.is_configured())
print("provider:", llm_client.provider)
print("base_url:", llm_client.base_url)
print("model:", llm_client.model)
print("temperature:", llm_client.temperature)
print("max_tokens:", llm_client.max_tokens)

async def test():
    chunks = []
    async for c in llm_client.chat_stream(
        [{"role": "user", "content": "say hi"}],
        "You are helpful."
    ):
        chunks.append(c)
    result = "".join(chunks)
    print("--- Response ---")
    print(result[:500])

asyncio.run(test())
