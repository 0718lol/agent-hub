"""Debate harness end-to-end test (encoding-safe for Windows GBK)."""
import asyncio
import websockets
import json
import time
import sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

async def test():
    uri = 'ws://127.0.0.1:8000/ws/test_debate_e2e'
    async with websockets.connect(uri) as ws:
        msg = {
            'type': 'message',
            'sender': 'user',
            'content': {'text': 'React 还是 Vue 做商城？'},
            'conversation_id': 'test_debate_e2e'
        }
        await ws.send(json.dumps(msg))
        start = time.time()
        print(f'[0.0s] Sent, waiting for debate...')

        debate_found = False
        while not debate_found:
            try:
                resp = await asyncio.wait_for(ws.recv(), timeout=10)
                elapsed = time.time() - start
                data = json.loads(resp)
                msg_type = data.get('type', '?')
                sender = data.get('sender', '?')
                message_type = data.get('message_type', '?')

                print(f'[{elapsed:.1f}s] type={msg_type} sender={sender} msg_type={message_type}')

                if data.get('content') and isinstance(data.get('content'), dict):
                    c = data['content'].get('text', '')[:100]
                    if c:
                        print(f'  => {c}')

                if msg_type == 'harness_debate_result' or message_type == 'harness_debate_interaction':
                    print(f'\n=== DEBATE TRIGGERED at {elapsed:.1f}s! ===')
                    sols = data.get('candidate_solutions', [])
                    print(f'Solutions: {len(sols)}')
                    for sol in sols:
                        print(f'  - {sol.get("author")}: {sol.get("summary", "")[:120]}')
                        code = sol.get("code_snippet", "")
                        print(f'    code snippet ({len(code)} chars): {code[:100]}...')
                    debate_found = True
                    break

                if msg_type == 'generating' and data.get('is_generating'):
                    elapsed = time.time() - start
                    print(f'[{elapsed:.1f}s] WARNING: Normal agent flow started (harness failed?)')

            except asyncio.TimeoutError:
                elapsed = time.time() - start
                print(f'[{elapsed:.1f}s] ...waiting...')
                if elapsed > 300:
                    print('Giving up after 5 min')
                    break

        total = time.time() - start
        print(f'\nDone in {total:.1f}s. Debate triggered: {debate_found}')

asyncio.run(test())
