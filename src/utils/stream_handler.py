import chainlit as cl
import os
import sys
from loguru import logger


logger.remove()
logger.add(sys.stderr, level=os.getenv('LOG_LEVEL', 'ERROR'))


class StreamHandler:
    """Handles the processing and display of message content in the chat UI."""

    def __init__(self):
        """Initialize the message handler with needed state tracking."""
        self.thinking_message = cl.Message(content='_Thinking..._ \n\n', type='assistant_message')
        self.active_objects = {}  # index -> {type, object}
        self.current_index = None
        self.current_tool_names = {}  # index -> tool_name (to track tool names across chunks)

    async def handle_index_change(self, new_index):
        """Handle a change in the message index, finalizing previous objects as needed."""
        if new_index == self.current_index:
            return

        # Finalize previous objects for the previous index
        if self.current_index is not None and self.current_index in self.active_objects:
            obj_info = self.active_objects[self.current_index]
            if obj_info['type'] == 'message' and obj_info['object'] is not None:
                await obj_info['object'].send()
                # Remove the finalized object
                del self.active_objects[self.current_index]

        self.current_index = new_index

    def get_or_create_message(self, index):
        """Get an existing message or create a new one for the given index."""
        if index not in self.active_objects or self.active_objects[index]['type'] != 'message':
            self.active_objects[index] = {'type': 'message', 'object': cl.Message(content='')}
        return self.active_objects[index]['object']

    async def handle_text_content(self, index, text):
        """Handle regular text content for a given index."""
        message = self.get_or_create_message(index)
        await message.stream_token(token=text)

    def get_or_create_tool_step(self, index, tool_name):
        """Get an existing tool step or create a new one for the given index."""
        if index not in self.active_objects or self.active_objects[index]['type'] != 'tool_step':
            logger.debug(f'Creating new tool step for index {index}, tool {tool_name}')
            step_id = f'{index}-{tool_name}'
            # Create a step that shows both input and output
            with cl.Step(
                name=f'MCP Tool: {tool_name}', type='tool', default_open=False, id=step_id
            ) as step:
                self.active_objects[index] = {'type': 'tool_step', 'object': step}
                self.current_index = index  # Update current index to this tool step
                logger.debug(f'Tool step created and current_index set to {index}')
        return self.active_objects[index]['object']

    async def handle_reasoning_content(self, content_item):
        """Handle reasoning (thinking) content."""
        if content_item['reasoning_content']['type'] == 'text':
            await self.thinking_message.stream_token(
                token=content_item['reasoning_content']['text']
            )
        elif content_item['reasoning_content']['type'] == 'signature':
            await self.thinking_message.send()

    async def handle_end_turn(self):
        """Handle the end turn signal by finalizing the current message."""
        if self.current_index is not None and self.current_index in self.active_objects:
            obj_info = self.active_objects[self.current_index]
            if obj_info['type'] == 'message':
                await obj_info['object'].send()

    async def handle_tool_output(self, content):
        """Handle tool output for the current index."""
        if self.current_index is None or self.current_index not in self.active_objects:
            return

        obj_info = self.active_objects[self.current_index]
        if obj_info['type'] == 'tool_step':
            with obj_info['object'] as step:
                await step.stream_token(token=content, is_input=False)
                await step.send()  # Finalize the step to display it in the UI

    async def handle_tool_input(self, index, tool_name, input_content):
        """Handle tool input for a given index and tool name."""
        logger.debug(f'Handling tool input for index {index}, tool {tool_name}')
        tool_step = self.get_or_create_tool_step(index, tool_name)
        with tool_step as step:
            await step.stream_token(token=input_content, is_input=True)
            # Note: We don't send the step here, as we want to wait for the output
