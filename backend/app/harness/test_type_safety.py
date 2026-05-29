import sys
import os
import asyncio
import unittest
from pydantic import ValidationError

# Ensure app is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from app.core.state_graph import GraphState, StateGraph
from app.tools.web_search import WebSearchTool
from app.tools.registry import execute_tool_call


class TestTypeSafety(unittest.TestCase):

    def test_graph_state_dict_compatibility(self):
        """Test that GraphState operates seamlessly like a dictionary while maintaining strong typing."""
        # 1. Initialize with dict
        init_data = {
            "original_prompt": "Create a weather website",
            "pm_response": "Initial plan outline"
        }
        state = GraphState(**init_data)

        # 2. Attribute access
        self.assertEqual(state.original_prompt, "Create a weather website")
        self.assertEqual(state.pm_response, "Initial plan outline")

        # 3. Dictionary key access
        self.assertEqual(state["original_prompt"], "Create a weather website")
        self.assertEqual(state["pm_response"], "Initial plan outline")

        # 4. Dictionary .get() access
        self.assertEqual(state.get("original_prompt"), "Create a weather website")
        self.assertEqual(state.get("non_existent", "default_val"), "default_val")

        # 5. Dict update
        state.update({"pm_response": "Updated plan"})
        self.assertEqual(state.pm_response, "Updated plan")
        self.assertEqual(state["pm_response"], "Updated plan")

        # 6. Containment operator
        self.assertTrue("pm_response" in state)
        self.assertFalse("non_existent" in state)

        # 7. Dynamic extra fields (allowed by model_config extra="allow")
        state.update({"custom_metadata_key": "some_value"})
        self.assertEqual(state.get("custom_metadata_key"), "some_value")
        self.assertEqual(state["custom_metadata_key"], "some_value")
        self.assertTrue("custom_metadata_key" in state)

    def test_graph_state_strict_validation(self):
        """Test that invalid types assigned to GraphState fields trigger Pydantic validation errors."""
        # completed_nodes must be List[str]
        with self.assertRaises(ValidationError):
            GraphState(completed_nodes="Not a list")

        state = GraphState()
        # Updating with invalid type
        with self.assertRaises(ValidationError):
            state.update({"completed_nodes": 12345})

    def test_tool_parameter_validation_success(self):
        """Test that passing correct arguments to a tool with params_model passes validation."""
        tool = WebSearchTool()
        
        # Correct arguments
        params = {"query": "FastAPI tutorial", "max_results": 3}
        
        import asyncio
        from unittest.mock import AsyncMock, patch
        
        with patch.object(tool, "execute", new_callable=AsyncMock) as mock_execute:
            mock_execute.return_value = "success"
            
            loop = asyncio.get_event_loop()
            res = loop.run_until_complete(tool.validate_and_execute(params))
            
            # Assert execute was called
            mock_execute.assert_called_once_with(params)

    def test_tool_parameter_validation_failure(self):
        """Test that passing incorrect arguments to a tool with params_model gets gracefully intercepted by Pydantic."""
        tool = WebSearchTool()
        
        # Missing required parameter 'query'
        invalid_params_1 = {"max_results": 3}
        
        loop = asyncio.get_event_loop()
        res_1 = loop.run_until_complete(tool.validate_and_execute(invalid_params_1))
        
        self.assertFalse(res_1.success)
        self.assertIn("【参数强校验失败】", res_1.error)
        self.assertIn("Field required", res_1.error)

        # Mismatched type for 'max_results'
        invalid_params_2 = {"query": "test", "max_results": "invalid_int_type"}
        res_2 = loop.run_until_complete(tool.validate_and_execute(invalid_params_2))
        
        self.assertFalse(res_2.success)
        self.assertIn("【参数强校验失败】", res_2.error)
        self.assertIn("Input should be a valid integer", res_2.error)


if __name__ == "__main__":
    unittest.main()
