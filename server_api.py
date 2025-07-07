import time
import os
import sys
import logging
import uvicorn
import re
import socket
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from dotenv import load_dotenv
from azure.identity import DefaultAzureCredential
from semantic_kernel.contents.chat_history import ChatHistory
from src.kernel.service import Kernel
from src.database.secure_service import create_database_service, get_database_credentials, SecureDatabase
from src.conversation.context_manager import ConversationMemory  # ADD THIS
from typing import Dict, Any, Optional, List
import uuid


# Configure logging
def setup_production_logging():
    log_dir = Path("C:/Logs")
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / "voice_sql_api.log"
    logging.getLogger().handlers.clear()  # Prevent duplicate handlers
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(logging.Formatter(
        "[%(asctime)s - %(name)s:%(lineno)d - %(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    ))
    console_handler.stream = open(sys.stdout.fileno(), mode='w', encoding='utf-8', errors='replace')
    file_handler = logging.FileHandler(log_file, mode='a', encoding='utf-8')
    file_handler.setFormatter(logging.Formatter(
        "[%(asctime)s - %(name)s:%(lineno)d - %(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    ))
    logging.basicConfig(level=logging.INFO, handlers=[console_handler, file_handler])
    logging.getLogger("azure").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("uvicorn").setLevel(logging.WARNING)  # Suppress Uvicorn logs
    return logging.getLogger(__name__)


logger = setup_production_logging()

# ADD THIS: Store conversation sessions
conversation_sessions = {}  # Store session_id -> ConversationMemory

app = FastAPI(
    title="Voice SQL API",
    version="1.0.0",
    description="Production Voice SQL API Service with Conversational Features"
)

kernel = None
chat_history = None
shutdown_requested = False


class QueryRequest(BaseModel):
    question: str
    session_id: Optional[str] = None  # ADD THIS
    export_format: Optional[str] = None  # 'csv', 'txt', or None for display


class QueryResponse(BaseModel):
    answer: str
    status: str = "success"
    session_id: Optional[str] = None  # ADD THIS
    suggestions: Optional[List[str]] = None  # ADD THIS


class ConversationResetRequest(BaseModel):  # ADD THIS
    session_id: Optional[str] = None


class SimpleKernel:
    """Fallback kernel for when AI services aren't available, with basic NLP"""

    def __init__(self, database_service):
        self.database_service = database_service

    async def message(self, user_input: str, chat_history: ChatHistory) -> str:
        """Process natural language queries with basic parsing"""
        try:
            user_input = user_input.lower().strip()
            logger.info(f"SimpleKernel processing query: {user_input}")

            # Pattern for counting records: "how many records in [table]"
            count_pattern = r"how\s+many\s+records\s+(?:are\s+)?in\s+([a-zA-Z_][a-zA-Z0-9_]*)"
            count_match = re.match(count_pattern, user_input)
            if count_match:
                table_name = count_match.group(1)
                sql_query = f"SELECT COUNT(*) FROM {table_name}"
                result = self.database_service.query(sql_query)
                if isinstance(result, str):
                    return result
                elif result and isinstance(result[0], tuple):
                    count = result[0][0]
                    return f"The table {table_name} has {count:,} records."
                else:
                    return f"No records found in table {table_name}."

            # Pattern for selecting columns: "show [columns] from [table]"
            select_pattern = r"show\s+([a-zA-Z0-9_, ]+)\s+from\s+([a-zA-Z_][a-zA-Z0-9_]*)"
            select_match = re.match(select_pattern, user_input)
            if select_match:
                columns = select_match.group(1).replace(" ", "").split(",")
                table_name = select_match.group(2)
                sql_query = f"SELECT {', '.join(columns)} FROM {table_name} WHERE ROWNUM <= 3"
                result = self.database_service.query(sql_query)
                if isinstance(result, str):
                    return result
                elif result:
                    return f"Query returned {len(result)} rows: {str(result)}"
                else:
                    return f"No records found in table {table_name}."

            return "Sorry, I couldn't understand your query. Try something like 'how many records in [table]' or 'show [columns] from [table]'."

        except Exception as e:
            logger.error(f"SimpleKernel error: {e}")
            return f"Error executing query: {str(e)}"


def load_environment_config():
    env_paths = [
        Path(".env"),
        Path(__file__).parent / ".env",
    ]
    env_loaded = False
    for env_path in env_paths:
        if env_path.exists():
            logger.info(f"Loading .env file from: {env_path.absolute()}")
            load_dotenv(env_path)
            env_loaded = True
            break
    if not env_loaded:
        logger.warning("No .env file found in expected locations")
        logger.info(f"Searched: {[str(p.absolute()) for p in env_paths]}")

    config = {
        'server_name': os.getenv("SQL_SERVER_NAME", "BI-SQL001"),
        'database_name': os.getenv("SQL_DATABASE_NAME", "CRPAF"),
        'openai_endpoint': os.getenv("AZURE_OPENAI_ENDPOINT"),
        'openai_deployment_name': os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT_NAME"),
        'db_username': os.getenv("DB_USERNAME"),
        'db_password': os.getenv("DB_PASSWORD"),
        'server_host': os.getenv("SERVER_HOST", "0.0.0.0"),
        'server_port': int(os.getenv("SERVER_PORT", "8000")),
        'debug': os.getenv("DEBUG", "false").lower() == "true"
    }
    logger.info("Production environment configuration:")
    logger.info(f"  Working Directory: {os.getcwd()}")
    logger.info(f"  SQL Server: {config['server_name']}")
    logger.info(f"  Database: {config['database_name']}")
    logger.info(f"  DB Username from env: {'Yes' if config['db_username'] else 'No'}")
    logger.info(f"  DB Password from env: {'Yes' if config['db_password'] else 'No'}")
    logger.info(f"  Azure OpenAI: {'Yes' if config['openai_endpoint'] else 'No'}")
    logger.info(f"  Server: {config['server_host']}:{config['server_port']}")
    return config


def initialize_database_service(config):
    try:
        if config['db_username'] and config['db_password']:
            logger.info(f"Using database credentials from environment for user: {config['db_username']}")
            database_service = SecureDatabase(
                server_name=config['server_name'],
                database_name=config['database_name'],
                username=config['db_username'],
                password=config['db_password']
            )
        else:
            username, password = get_database_credentials()
            if username and password:
                logger.info(f"Using database credentials from encrypted storage for user: {username}")
                database_service = SecureDatabase(
                    server_name=config['server_name'],
                    database_name=config['database_name'],
                    username=username,
                    password=password
                )
            else:
                logger.warning("No credentials found - using trusted connection")
                database_service = create_database_service(
                    config['server_name'],
                    config['database_name']
                )
        if database_service.test_connection():
            logger.info("Database connection successful")
            return database_service
        else:
            raise Exception("Database connection test failed")
    except Exception as e:
        logger.error(f"Failed to initialize database service: {e}")
        raise


def initialize_azure_services(config):
    try:
        credential = None
        if config['openai_endpoint'] and config['openai_deployment_name']:
            credential = DefaultAzureCredential()
            logger.info("Azure credentials initialized")
        else:
            logger.info("Azure OpenAI not configured")
        return credential
    except Exception as e:
        logger.warning(f"Azure credential initialization failed: {e}")
        return None


# ADD THIS: Helper function to get or create conversation session
def get_conversation_session(session_id: Optional[str]) -> tuple[str, ConversationMemory]:
    """Get existing conversation session or create new one"""
    if session_id and session_id in conversation_sessions:
        return session_id, conversation_sessions[session_id]
    else:
        # Create new session
        new_session_id = str(uuid.uuid4())
        conversation_sessions[new_session_id] = ConversationMemory()
        logger.info(f"Created new conversation session: {new_session_id}")
        return new_session_id, conversation_sessions[new_session_id]


# ADD THIS: Helper function to generate follow-up suggestions
def generate_follow_up_suggestions(conversation_memory: ConversationMemory, response: str) -> List[str]:
    """Generate context-aware follow-up suggestions"""
    try:
        # Update conversation context first
        conversation_memory.update_context(
            conversation_memory.current_context.query_text if conversation_memory.current_context else "", response)

        # Get suggestions from conversation memory
        suggestions = conversation_memory.get_follow_up_suggestions()

        return suggestions[:4]  # Limit to 4 suggestions
    except Exception as e:
        logger.error(f"Error generating suggestions: {e}")
        return []


@asynccontextmanager
async def lifespan(app: FastAPI):
    global kernel, chat_history
    try:
        logger.info("Starting Voice SQL API server...")
        config = load_environment_config()
        database_service = initialize_database_service(config)
        credential = initialize_azure_services(config)
        if credential and config['openai_endpoint'] and config['openai_deployment_name']:
            try:
                kernel = Kernel(
                    database_service=database_service,
                    credential=credential,
                    openai_endpoint=config['openai_endpoint'],
                    openai_deployment_name=config['openai_deployment_name']
                )
                logger.info("Semantic kernel initialized with automatic token refresh")
            except Exception as e:
                logger.error(f"AI kernel initialization failed: {e}", exc_info=True)
                logger.info("Falling back to simple kernel")
                kernel = SimpleKernel(database_service=database_service)
        else:
            logger.info("Using simple kernel (no AI services)")
            kernel = SimpleKernel(database_service=database_service)
        chat_history = ChatHistory()
        logger.info("Voice SQL API server ready!")
        logger.info(f"  Database: {config['database_name']} on {config['server_name']}")
        logger.info(f"  Security: {'Authenticated user' if config['db_username'] else 'Trusted connection'}")
        logger.info(f"  AI: {'Enabled with auto token refresh' if hasattr(kernel, 'chat_completion') else 'Disabled'}")
        logger.info(f"  Speech: Handled by client (Windows TTS)")
        logger.info(f"  Conversational Features: Enabled")  # ADD THIS
    except Exception as e:
        logger.error(f"Critical startup failure: {e}", exc_info=True)
        try:
            config = load_environment_config()
            database_service = initialize_database_service(config)
            kernel = SimpleKernel(database_service=database_service)
            chat_history = ChatHistory()
            logger.info("Minimal server functionality initialized")
        except Exception as minimal_error:
            logger.error(f"Even minimal initialization failed: {minimal_error}", exc_info=True)
            raise
    yield
    logger.info("Voice SQL API server shutting down...")
    global shutdown_requested
    shutdown_requested = True


app = FastAPI(lifespan=lifespan)


@app.get("/")
async def root():
    return {
        "message": "Voice SQL API is running",
        "status": "healthy",
        "mode": "production",
        "features": ["conversational_ai", "session_management", "follow_up_suggestions"]  # ADD THIS
    }


@app.get("/health")
async def health_check():
    try:
        db_status = False
        if kernel and hasattr(kernel, 'database_service'):
            db_status = kernel.database_service.test_connection()
        config = load_environment_config()
        username = config['db_username'] or get_database_credentials()[0]
        health_data = {
            "status": "healthy" if db_status else "degraded",
            "timestamp": time.time(),
            "database": {
                "connected": db_status,
                "server": config['server_name'],
                "database": config['database_name'],
                "auth_mode": "authenticated" if username else "trusted"
            },
            "services": {
                "ai_enabled": hasattr(kernel, 'chat_completion') if kernel else False,
                "kernel_type": "ai" if hasattr(kernel, 'chat_completion') else "simple",
                "token_refresh": "automatic" if hasattr(kernel, '_refresh_token_and_reinitialize') else "manual",
                "conversation_sessions": len(conversation_sessions)  # ADD THIS
            }
        }
        if not db_status:
            logger.warning("Health check failed - database not connected")
        return health_data
    except Exception as e:
        logger.error(f"Health check error: {e}")
        raise HTTPException(status_code=500, detail="Health check failed")


@app.post("/ask")
async def ask_question(request: QueryRequest) -> QueryResponse:
    try:
        if not kernel:
            raise HTTPException(status_code=503, detail="Service not initialized")

        logger.info(f"Processing question: {request.question}")

        # Get or create conversation session
        session_id, conversation_memory = get_conversation_session(request.session_id)

        # Handle option selection from client
        if request.question.lower().strip().startswith("option "):
            try:
                # Extract option number and convert to full query
                enhanced_question = conversation_memory.handle_follow_up_selection(request.question)
                if enhanced_question:
                    logger.info(f"Converted option selection to: {enhanced_question}")
                else:
                    enhanced_question = request.question
            except Exception as e:
                logger.warning(f"Error handling option selection: {e}")
                enhanced_question = request.question
        else:
            # Enhance query with conversation context
            enhanced_question = conversation_memory.enhance_query_with_context(request.question)

        # Add export instruction if requested
        if request.export_format:
            export_instruction = f" Please export the results to {request.export_format} format."
            enhanced_question = enhanced_question + export_instruction

        # Get response from kernel
        response = await kernel.message(enhanced_question, chat_history)
        logger.info("Response generated successfully")

        # Generate follow-up suggestions
        suggestions = generate_follow_up_suggestions(conversation_memory, str(response))

        return QueryResponse(
            answer=str(response),
            status="success",
            session_id=session_id,
            suggestions=suggestions if suggestions else None
        )
    except Exception as e:
        logger.error(f"Error processing question: {e}")
        raise HTTPException(status_code=500, detail=f"Error processing question: {str(e)}")


# ADD THIS: New endpoint for resetting conversations
@app.post("/reset_conversation")
async def reset_conversation(request: ConversationResetRequest):
    """Reset conversation context and start fresh"""
    try:
        if request.session_id and request.session_id in conversation_sessions:
            # Reset existing session
            conversation_sessions[request.session_id] = ConversationMemory()
            logger.info(f"Reset conversation session: {request.session_id}")
            return {
                "status": "success",
                "session_id": request.session_id,
                "message": "Conversation reset successfully"
            }
        else:
            # Create new session
            new_session_id = str(uuid.uuid4())
            conversation_sessions[new_session_id] = ConversationMemory()
            logger.info(f"Created new conversation session: {new_session_id}")
            return {
                "status": "success",
                "session_id": new_session_id,
                "message": "New conversation started"
            }
    except Exception as e:
        logger.error(f"Error resetting conversation: {e}")
        raise HTTPException(status_code=500, detail=f"Error resetting conversation: {str(e)}")


# ADD THIS: Debug endpoint for conversation state
@app.get("/conversation_state/{session_id}")
async def get_conversation_state(session_id: str):
    """Get conversation state for debugging"""
    try:
        if session_id not in conversation_sessions:
            raise HTTPException(status_code=404, detail="Session not found")

        conversation_memory = conversation_sessions[session_id]
        state = conversation_memory.get_conversation_state()

        return {
            "session_id": session_id,
            "state": state,
            "timestamp": time.time()
        }
    except Exception as e:
        logger.error(f"Error getting conversation state: {e}")
        raise HTTPException(status_code=500, detail=f"Error getting conversation state: {str(e)}")


@app.get("/status")
async def get_detailed_status():
    try:
        config = load_environment_config()
        username = config['db_username'] or get_database_credentials()[0]
        return {
            "server": "running",
            "uptime": time.time(),
            "process_id": os.getpid(),
            "working_directory": os.getcwd(),
            "database": {
                "server_name": config['server_name'],
                "database_name": config['database_name'],
                "user": username if username else "trusted_connection",
                "security_mode": "authenticated" if username else "trusted"
            },
            "services": {
                "kernel_type": "ai_enabled" if hasattr(kernel, 'chat_completion') else "simple",
                "azure_openai": "configured" if config['openai_endpoint'] else "not_configured",
                "token_management": "automatic" if hasattr(kernel, '_refresh_token_and_reinitialize') else "none"
            },
            "environment": {
                "env_file_loaded": any(Path(p).exists() for p in [".env", Path(__file__).parent / ".env"]),
                "credentials_in_env": bool(config['db_username'] and config['db_password'])
            },
            "chat_history_length": len(chat_history) if chat_history else 0,
            "conversation_sessions": len(conversation_sessions)  # ADD THIS
        }
    except Exception as e:
        logger.error(f"Status check failed: {e}")
        raise HTTPException(status_code=500, detail="Status check failed")


@app.get("/exports")
async def list_exports():
    try:
        export_dir = Path("C:/Logs/VoiceSQL/exports")
        if not export_dir.exists():
            return {"exports": [], "message": "No exports directory found"}
        exports = []
        for file in export_dir.glob("*.csv"):
            stat = file.stat()
            exports.append({
                "filename": file.name,
                "size_mb": round(stat.st_size / (1024 * 1024), 2),
                "created": stat.st_ctime,
                "download_url": f"/download/{file.name}"
            })
        for file in export_dir.glob("*.txt"):
            stat = file.stat()
            exports.append({
                "filename": file.name,
                "size_mb": round(stat.st_size / (1024 * 1024), 2),
                "created": stat.st_ctime,
                "download_url": f"/download/{file.name}"
            })
        exports.sort(key=lambda x: x["created"], reverse=True)
        return {
            "exports": exports,
            "count": len(exports),
            "total_size_mb": sum(e["size_mb"] for e in exports)
        }
    except Exception as e:
        logger.error(f"Error listing exports: {e}")
        raise HTTPException(status_code=500, detail=f"Error listing exports: {e}")


@app.get("/download/{filename}")
async def download_export(filename: str):
    try:
        export_dir = Path("C:/Logs/VoiceSQL/exports")
        file_path = export_dir / filename
        if not file_path.is_file() or not str(file_path).startswith(str(export_dir)):
            logger.warning(f"Download attempt for invalid file: {filename}")
            raise HTTPException(status_code=404, detail="File not found")
        logger.info(f"Serving download for file: {filename}")
        return FileResponse(
            path=file_path,
            filename=filename,
            media_type='application/octet-stream'
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error downloading file: {e}")
        raise HTTPException(status_code=500, detail=f"Error downloading file: {e}")


@app.delete("/exports/{filename}")
async def delete_export(filename: str):
    try:
        export_dir = Path("C:/Logs/VoiceSQL/exports")
        file_path = export_dir / filename
        if not file_path.is_file() or not str(file_path).startswith(str(export_dir)):
            raise HTTPException(status_code=404, detail="File not found")
        file_path.unlink()
        logger.info(f"Deleted export file: {filename}")
        return {"message": f"File {filename} deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting file: {e}")
        raise HTTPException(status_code=500, detail=f"Error deleting file: {e}")


def main():
    try:
        config = load_environment_config()
        logger.info(f"Starting production server on {config['server_host']}:{config['server_port']}")
        logger.info(f"Process ID: {os.getpid()}")
        uvicorn.run(
            "server_api:app",
            host=config['server_host'],
            port=config['server_port'],
            reload=False,
            log_level="warning",
            access_log=False,
            workers=1
        )
    except KeyboardInterrupt:
        logger.info("Server shutdown requested by user")
    except Exception as e:
        logger.error(f"Critical server error: {e}", exc_info=True)
        sys.exit(1)
    finally:
        logger.info("Server process ending")


if __name__ == "__main__":
    main()