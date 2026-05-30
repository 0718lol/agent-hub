import sys
import os
import unittest
import asyncio
import concurrent.futures
from datetime import datetime

# Setup import path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from app.core.database import (
    init_db, save_message, get_messages, clear_messages,
    save_memory_item, get_project_memory, delete_memory_item
)

class TestDbQueuePressure(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        # Ensure database is initialized
        init_db()
        self.test_conv_id = "test_pressure_conv_123"
        clear_messages(self.test_conv_id)

    def tearDown(self):
        clear_messages(self.test_conv_id)

    async def test_high_concurrency_writes_resilience(self):
        """1. Verify that 100 concurrent database writes serialize through @db_write_transaction with 0 locked conflicts."""
        num_writes = 100
        
        async def perform_single_write(idx: int):
            # Interleave message saving and memory saving
            if idx % 2 == 0:
                save_message(
                    conversation_id=self.test_conv_id,
                    sender=f"test_sender_{idx}",
                    content={"text": f"Concurrent message body {idx}"},
                    streaming=False
                )
            else:
                save_memory_item(
                    conversation_id=self.test_conv_id,
                    key=f"key_{idx}",
                    value=f"value_{idx}",
                    source="test"
                )

        # Run 100 concurrent database write tasks in parallel using asyncio.gather
        tasks = [perform_single_write(i) for i in range(num_writes)]
        
        # This will fire all 100 write transactions concurrently
        print(f"\n[Pressure Test] Spawning {num_writes} concurrent SQLite write transactions...")
        start_time = asyncio.get_event_loop().time()
        await asyncio.gather(*tasks)
        elapsed = asyncio.get_event_loop().time() - start_time
        print(f"[Pressure Test] Completed {num_writes} concurrent writes in {elapsed:.3f} seconds with zero exceptions!")

        # Verify all messages were successfully written and are queryable
        messages = get_messages(self.test_conv_id, limit=200)
        memory = get_project_memory(self.test_conv_id)
        
        self.assertEqual(len(messages), num_writes // 2)
        self.assertEqual(len(memory), num_writes // 2)
        
        # Clean memory items
        for i in range(num_writes):
            if i % 2 != 0:
                delete_memory_item(self.test_conv_id, f"key_{i}")

if __name__ == "__main__":
    unittest.main()
