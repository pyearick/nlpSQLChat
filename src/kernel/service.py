# Enhanced src/kernel/service.py with automatic token refresh

import os
import sys
import logging
import asyncio

from azure.identity import DefaultAzureCredential
from azure.core.exceptions import ClientAuthenticationError
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

# see https://learn.microsoft.com/en-us/azure/ai-services/openai/how-to-managed-identity
scope = 'https://cognitiveservices.azure.com/.default'


class Kernel:
    def __init__(self, database_service: Database, credential: DefaultAzureCredential, openai_endpoint: str,
                 openai_deployment_name: str) -> None:

        # Store initialization parameters for re-initialization
        self.database_service = database_service
        self.credential = credential
        self.openai_endpoint = openai_endpoint
        self.openai_deployment_name = openai_deployment_name

        # Initialize the kernel
        self._initialize_kernel()

    def _initialize_kernel(self):
        """Initialize or re-initialize the kernel with fresh token"""
        try:
            # Create a new kernel
            self.kernel = SemanticKernel()

            # Get fresh token
            fresh_token = self.credential.get_token(scope).token

            # Create a chat completion service with fresh token
            self.chat_completion = AzureChatCompletion(
                ad_token=fresh_token,
                endpoint=self.openai_endpoint,
                deployment_name=self.openai_deployment_name
            )

            # Add Azure OpenAI chat completion
            self.kernel.add_service(self.chat_completion)

            # Import and add the plugin directly instead of loading from directory
            try:
                from src.plugins.database_plugin import DatabasePlugin

                # Create plugin instance
                plugin_instance = DatabasePlugin(db=self.database_service)

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

            logger.info("✅ Kernel initialized successfully with fresh token")

        except Exception as e:
            logger.error(f"❌ Kernel initialization failed: {e}")
            raise

    def _refresh_token_and_reinitialize(self):
        """Force refresh token and reinitialize kernel"""
        try:
            logger.info("🔄 Refreshing token and reinitializing kernel...")

            # Force get a new token by creating new credential
            self.credential = DefaultAzureCredential()

            # Re-initialize everything
            self._initialize_kernel()

            logger.info("✅ Token refreshed and kernel reinitialized")
            return True

        except Exception as e:
            logger.error(f"❌ Token refresh and reinitialization failed: {e}")
            return False

    async def message(self, user_input: str, chat_history: ChatHistory) -> str:
        """
        Send a message to the kernel and get a response with automatic token retry.
        """
        max_retries = 2

        for attempt in range(max_retries):
            try:
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

            except Exception as e:
                error_str = str(e).lower()

                # Check if it's an authentication error (more comprehensive detection)
                is_auth_error = (
                        '401' in error_str or
                        'unauthorized' in error_str or
                        'token' in error_str or
                        'expired' in error_str or
                        'authentication' in error_str or
                        'authenticationerror' in error_str or
                        'access token is missing' in error_str or
                        'invalid audience' in error_str
                )

                if is_auth_error:

                    if attempt < max_retries - 1:
                        logger.warning(f"🔄 Authentication error detected, refreshing token (attempt {attempt + 1})")
                        logger.warning(f"Error details: {e}")

                        # Try to refresh token and reinitialize
                        if self._refresh_token_and_reinitialize():
                            # Wait a moment before retry
                            await asyncio.sleep(1)
                            continue
                        else:
                            logger.error("Failed to refresh token, falling back to error message")
                            return f"Authentication error: Unable to refresh Azure token. Please restart the server."
                    else:
                        logger.error("❌ Max retries exceeded for authentication error")
                        return f"Authentication error: Unable to connect to Azure OpenAI after {max_retries} attempts. Please restart the server."
                else:
                    # Non-auth error, don't retry
                    logger.error(f"Non-authentication error in kernel: {e}")
                    return f"Error processing request: {str(e)}"

        return "Error: Could not process request after multiple attempts"