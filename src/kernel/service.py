# Enhanced src/kernel/service.py with session caching for database plugin prompt

import os
import sys
import logging
import asyncio
from typing import Optional, Dict, Any
from dataclasses import dataclass
from datetime import datetime, timedelta

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


@dataclass
class PluginCacheEntry:
    """Cache entry for plugin instances with metadata"""
    plugin_instance: Any
    created_at: datetime
    database_version: str  # Track if database schema changes


class SessionCache:
    """Session-aware cache for plugin instances and prompts"""

    def __init__(self, cache_ttl_hours: int = 24):
        self.cache_ttl = timedelta(hours=cache_ttl_hours)
        self.plugin_cache: Dict[str, PluginCacheEntry] = {}
        self.prompt_cache: Dict[str, str] = {}

    def get_plugin(self, cache_key: str) -> Optional[Any]:
        """Get cached plugin instance if valid"""
        if cache_key not in self.plugin_cache:
            return None

        entry = self.plugin_cache[cache_key]

        # Check if cache is expired
        if datetime.now() - entry.created_at > self.cache_ttl:
            logger.info(f"Plugin cache expired for key: {cache_key}")
            del self.plugin_cache[cache_key]
            return None

        logger.info(f"Using cached plugin for key: {cache_key}")
        return entry.plugin_instance

    def cache_plugin(self, cache_key: str, plugin_instance: Any, database_version: str = "1.0"):
        """Cache plugin instance with metadata"""
        self.plugin_cache[cache_key] = PluginCacheEntry(
            plugin_instance=plugin_instance,
            created_at=datetime.now(),
            database_version=database_version
        )
        logger.info(f"Cached plugin for key: {cache_key}")

    def get_prompt(self, prompt_key: str) -> Optional[str]:
        """Get cached prompt"""
        return self.prompt_cache.get(prompt_key)

    def cache_prompt(self, prompt_key: str, prompt_content: str):
        """Cache prompt content"""
        self.prompt_cache[prompt_key] = prompt_content
        logger.info(f"Cached prompt for key: {prompt_key}")

    def invalidate_all(self):
        """Clear all cached items"""
        self.plugin_cache.clear()
        self.prompt_cache.clear()
        logger.info("All cache entries invalidated")

    def invalidate_plugin(self, cache_key: str):
        """Invalidate specific plugin cache"""
        if cache_key in self.plugin_cache:
            del self.plugin_cache[cache_key]
            logger.info(f"Invalidated plugin cache for key: {cache_key}")


class Kernel:
    def __init__(self, database_service: Database, credential: DefaultAzureCredential,
                 openai_endpoint: str, openai_deployment_name: str,
                 session_id: Optional[str] = None) -> None:

        # Store initialization parameters
        self.database_service = database_service
        self.credential = credential
        self.openai_endpoint = openai_endpoint
        self.openai_deployment_name = openai_deployment_name
        self.session_id = session_id or "default"

        # Initialize session cache (shared across all kernel instances)
        if not hasattr(Kernel, '_session_cache'):
            Kernel._session_cache = SessionCache()

        self.cache = Kernel._session_cache

        # Track token refresh count for cache invalidation
        self.token_refresh_count = 0

        # Initialize the kernel
        self._initialize_kernel()

    def _get_plugin_cache_key(self) -> str:
        """Generate cache key for database plugin"""
        # Include database service hash to detect schema changes
        db_hash = hash(str(self.database_service))
        return f"database_plugin_{self.session_id}_{db_hash}_{self.token_refresh_count}"

    def _initialize_kernel(self):
        """Initialize or re-initialize the kernel with session caching"""
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

            # Load database plugin with caching
            self._load_database_plugin_with_cache()

            # Enable automatic function calling
            self.execution_settings = AzureChatPromptExecutionSettings(tool_choice="auto")
            self.execution_settings.function_call_behavior = FunctionCallBehavior.EnableFunctions(
                auto_invoke=True, filters={}
            )

            logger.info("✅ Kernel initialized successfully with fresh token")

        except Exception as e:
            logger.error(f"❌ Kernel initialization failed: {e}")
            raise

    def _load_database_plugin_with_cache(self):
        """Load database plugin with session caching"""
        try:
            cache_key = self._get_plugin_cache_key()

            # Try to get cached plugin first
            cached_plugin = self.cache.get_plugin(cache_key)

            if cached_plugin is not None:
                # Use cached plugin instance
                self.kernel.add_plugin(cached_plugin, "DatabasePlugin")
                logger.info("✅ Using cached DatabasePlugin instance")
                return

            # Create new plugin instance if not cached
            logger.info("🔄 Creating new DatabasePlugin instance...")

            from src.plugins.database_plugin import DatabasePlugin

            # Create plugin instance
            plugin_instance = DatabasePlugin(db=self.database_service)

            # Cache the plugin instance
            self.cache.cache_plugin(cache_key, plugin_instance)

            # Add to kernel
            self.kernel.add_plugin(plugin_instance, "DatabasePlugin")
            logger.info("✅ Successfully loaded and cached DatabasePlugin")

        except Exception as e:
            logger.error(f"❌ Failed to load DatabasePlugin: {e}")
            raise

    def _refresh_token_and_reinitialize(self):
        """Force refresh token and reinitialize kernel with cache management"""
        try:
            logger.info("🔄 Refreshing token and reinitializing kernel...")

            # Increment token refresh count to invalidate old cached plugins
            self.token_refresh_count += 1

            # Force get a new token by creating new credential
            self.credential = DefaultAzureCredential()

            # Re-initialize everything
            self._initialize_kernel()

            logger.info("✅ Token refreshed and kernel reinitialized")
            return True

        except Exception as e:
            logger.error(f"❌ Token refresh and reinitialization failed: {e}")
            return False

    def invalidate_plugin_cache(self):
        """Manually invalidate plugin cache (useful for development/debugging)"""
        cache_key = self._get_plugin_cache_key()
        self.cache.invalidate_plugin(cache_key)
        logger.info("🗑️ Plugin cache invalidated manually")

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics for monitoring"""
        return {
            "cached_plugins": len(self.cache.plugin_cache),
            "cached_prompts": len(self.cache.prompt_cache),
            "session_id": self.session_id,
            "token_refresh_count": self.token_refresh_count,
            "cache_keys": list(self.cache.plugin_cache.keys())
        }

    async def message(self, user_input: str, chat_history: ChatHistory) -> str:
        """Send a message to the kernel with automatic token retry and session caching"""
        max_retries = 2

        for attempt in range(max_retries + 1):
            try:
                # Add user message to chat history
                chat_history.add_user_message(user_input)

                # Create kernel arguments (required for auto function calling)
                kernel_arguments = KernelArguments()

                # Use the chat completion service directly with function calling enabled
                response = await self.chat_completion.get_chat_message_contents(
                    chat_history=chat_history,
                    settings=self.execution_settings,
                    kernel=self.kernel,  # This enables function calling with plugins
                    arguments=kernel_arguments  # Required for auto invoking tool calls
                )

                # Extract response text from the response
                response_text = ""
                if response and len(response) > 0:
                    # Get the last response message
                    last_message = response[-1]
                    if hasattr(last_message, 'content') and last_message.content:
                        response_text = str(last_message.content)
                    elif hasattr(last_message, 'value') and last_message.value:
                        response_text = str(last_message.value)
                    else:
                        response_text = str(last_message)

                # Add assistant response to chat history
                if response_text.strip():
                    chat_history.add_assistant_message(response_text)
                else:
                    # Fallback if no content
                    response_text = "I received your request but couldn't generate a response."
                    chat_history.add_assistant_message(response_text)

                return response_text

            except ClientAuthenticationError as auth_error:
                logger.warning(f"Authentication error on attempt {attempt + 1}: {auth_error}")

                if attempt < max_retries:
                    logger.info(f"Retrying with fresh token (attempt {attempt + 2}/{max_retries + 1})...")

                    if self._refresh_token_and_reinitialize():
                        continue
                    else:
                        logger.error("Failed to refresh token, cannot retry")
                        break
                else:
                    logger.error("Max retries exceeded for authentication")
                    raise

            except Exception as e:
                logger.error(f"Error in message processing: {e}")
                logger.debug(f"Response object type: {type(response) if 'response' in locals() else 'undefined'}")
                logger.debug(f"Response content: {response if 'response' in locals() else 'undefined'}")

                if attempt < max_retries:
                    logger.info(f"Retrying due to error (attempt {attempt + 2}/{max_retries + 1})...")
                    continue
                else:
                    raise

        return "I apologize, but I encountered an error processing your request. Please try again."