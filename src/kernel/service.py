import os
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

scope = os.getenv('AZURE_OPENAI_SCOPE', 'https://cognitiveservices.azure.com/.default')

class Kernel:
    def __init__(self, database_service: Database, credential: DefaultAzureCredential, openai_endpoint: str,
                 openai_deployment_name: str) -> None:
        self.database_service = database_service
        self.credential = credential
        self.openai_endpoint = openai_endpoint
        self.openai_deployment_name = openai_deployment_name
        self._initialize_kernel()

    def _initialize_kernel(self):
        try:
            self.kernel = SemanticKernel()
            fresh_token = self.credential.get_token(scope).token
            logger.info(f"Obtained token: {fresh_token[:20]}...")
            self.chat_completion = AzureChatCompletion(
                ad_token=fresh_token,
                endpoint=self.openai_endpoint,
                deployment_name=self.openai_deployment_name
            )
            self.kernel.add_service(self.chat_completion)
            from src.plugins.database_plugin import DatabasePlugin
            plugin_instance = DatabasePlugin(db=self.database_service)
            self.kernel.add_plugin(plugin_instance, "DatabasePlugin")
            logger.info("Successfully loaded DatabasePlugin")
            self.execution_settings = AzureChatPromptExecutionSettings(tool_choice="auto")
            self.execution_settings.function_call_behavior = FunctionCallBehavior.EnableFunctions(
                auto_invoke=True, filters={}
            )
            logger.info("Kernel initialized successfully")
        except Exception as e:
            logger.error(f"Kernel initialization failed: {e}", exc_info=True)
            raise

    def _refresh_token_and_reinitialize(self):
        try:
            logger.info("Refreshing token and reinitializing kernel...")
            fresh_token = self.credential.get_token(scope).token
            logger.info(f"Refreshed token: {fresh_token[:20]}...")
            self._initialize_kernel()
            logger.info("Token refreshed and kernel reinitialized")
            return True
        except Exception as e:
            logger.error(f"Token refresh failed: {e}", exc_info=True)
            return False

    async def message(self, user_input: str, chat_history: ChatHistory) -> str:
        max_retries = 3
        for attempt in range(max_retries):
            try:
                logger.debug(f"Attempt {attempt + 1}: Sending request to AzureChatCompletion")
                chat_history.add_user_message(user_input)
                chat_history_count = len(chat_history)
                response = await self.chat_completion.get_chat_message_contents(
                    chat_history=chat_history,
                    settings=self.execution_settings,
                    kernel=self.kernel,
                    arguments=KernelArguments(),
                )
                for message in chat_history[chat_history_count:]:
                    if message.role == AuthorRole.TOOL:
                        for item in message.items:
                            logger.debug(f"tool {item.name} called and returned {item.result}")
                    elif message.role == AuthorRole.ASSISTANT and message.finish_reason == FinishReason.TOOL_CALLS:
                        for item in message.items:
                            logger.debug(f"tool {item.name} needs to be called with parameters {item.arguments}")
                logger.debug(f"Response received: {response}")
                return str(response[0])
            except ClientAuthenticationError as e:
                error_str = str(e).lower()
                logger.error(f"Attempt {attempt + 1} failed: {error_str}")
                if attempt < max_retries - 1:
                    logger.info(f"Attempting token refresh (attempt {attempt + 1}/{max_retries})")
                    if self._refresh_token_and_reinitialize():
                        await asyncio.sleep(1)
                        continue
                    else:
                        logger.error("Token refresh failed")
                        return f"Authentication error: Unable to refresh Azure token."
                else:
                    logger.error(f"Max retries ({max_retries}) exceeded for authentication error")
                    return f"Authentication error: Unable to connect to Azure OpenAI after {max_retries} attempts."
            except Exception as e:
                logger.error(f"Non-authentication error: {e}")
                return f"Error processing request: {str(e)}"
        return "Error: Could not process request after multiple attempts"