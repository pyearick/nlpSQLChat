import os
import sys
import logging

from azure.identity import DefaultAzureCredential
from semantic_kernel import Kernel as SemanticKernel
from semantic_kernel.connectors.ai.open_ai import AzureChatCompletion
from semantic_kernel.functions import KernelArguments
from semantic_kernel.contents.chat_history import ChatHistory
from semantic_kernel.connectors.ai.function_call_behavior import FunctionCallBehavior
from semantic_kernel.connectors.ai.open_ai.prompt_execution_settings.azure_chat_prompt_execution_settings import (
    AzureChatPromptExecutionSettings,
)
from semantic_kernel.contents.author_role import AuthorRole
from semantic_kernel.contents.finish_reason import FinishReason

from src.database import Database

logger = logging.getLogger(__name__)

# see https://learn.microsoft.com/en-us/azure/ai-services/openai/how-to/managed-identity
scope = 'https://cognitiveservices.azure.com/.default'


class Kernel:
    def __init__(self, database_service: Database, credential: DefaultAzureCredential, openai_endpoint: str,
                 openai_deployment_name: str) -> None:
        # Create a new kernel
        self.kernel = SemanticKernel()
        # Create a chat completion service
        self.chat_completion = AzureChatCompletion(ad_token=credential.get_token(scope).token, endpoint=openai_endpoint,
                                                   deployment_name=openai_deployment_name)

        # Add Azure OpenAI chat completion
        self.kernel.add_service(self.chat_completion)

        # Import and add the plugin directly instead of loading from directory
        try:
            from src.plugins.database_plugin import DatabasePlugin

            # Create plugin instance
            plugin_instance = DatabasePlugin(db=database_service)

            # Add the plugin instance to the kernel
            self.kernel.add_plugin(plugin_instance, "DatabasePlugin")
            logger.info("Successfully loaded DatabasePlugin")

        except Exception as e:
            logger.error(f"Failed to load DatabasePlugin: {e}")
            raise

        # Enable automatic function calling
        self.execution_settings = AzureChatPromptExecutionSettings(tool_choice="auto")
        self.execution_settings.function_call_behavior = FunctionCallBehavior.EnableFunctions(auto_invoke=True,
                                                                                              filters={})

    async def message(self, user_input: str, chat_history: ChatHistory) -> str:
        """
        Send a message to the kernel and get a response.
        """
        chat_history.add_user_message(user_input)
        chat_history_count = len(chat_history)
        response = await self.chat_completion.get_chat_message_contents(
            chat_history=chat_history,
            settings=self.execution_settings,
            kernel=self.kernel,
            arguments=KernelArguments(),
        )

        # print assistant/tool actions
        for message in chat_history[chat_history_count:]:
            if message.role == AuthorRole.TOOL:
                for item in message.items:
                    print("tool {} called and returned {}".format(item.name, item.result))
            elif message.role == AuthorRole.ASSISTANT and message.finish_reason == FinishReason.TOOL_CALLS:
                for item in message.items:
                    print("tool {} needs to be called with parameters {}".format(item.name, item.arguments))

        return str(response[0])