# server_api.py - Cleaned up version without TokenManager

import os
import sys
import asyncio
import logging
import time
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from dotenv import load_dotenv
from azure.identity import DefaultAzureCredential
from semantic_kernel.contents.chat_history import ChatHistory

# Import your existing modules
from src.speech import Speech
from src.kernel import Kernel
from src.orchestrator import Orchestrator
from src.database.secure_service import create_database_service, get_database_credentials, SecureDatabase

# Load environment variables FIRST
load_dotenv()

# Configure logging
def setup_production_logging():
    """Setup logging for Windows service environment"""

    # Use the standard server log directory
    log_dir = Path("C:/Logs")
    log_dir.mkdir(exist_ok=True)

    # Log file with rotation
    log_file = log_dir / "voice_sql_api.log"

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s - %(name)s:%(lineno)d - %(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.FileHandler(log_file, mode='a'),
            logging.StreamHandler(sys.stdout)
        ]
    )

    # Prevent excessive logging from some libraries
    logging.getLogger("azure").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    return logging.getLogger(__name__)

# Initialize logging first
logger = setup_production_logging()

# FastAPI app
app = FastAPI(
    title="Voice SQL API",
    version="1.0.0",
    description="Production Voice SQL API Service"
)

# Global variables
kernel = None
chat_history = None
shutdown_requested = False

# Fixed model definitions with proper imports
class QueryRequest(BaseModel):
    question: str
    export_format: Optional[str] = None  # 'csv', 'txt', or None for display

class QueryResponse(BaseModel):
    answer: str
    status: str = "success"

def load_environment_config():
    """Load and validate environment configuration for production"""

    # Find and load .env file
    env_paths = [
        Path(".env"),  # Current directory
        Path(__file__).parent / ".env",  # Script directory
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
        'speech_service_id': os.getenv("SPEECH_SERVICE_ID"),
        'azure_location': os.getenv("AZURE_LOCATION"),
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
    logger.info(f"  Speech Service: {'Yes' if config['speech_service_id'] else 'No'}")
    logger.info(f"  Server: {config['server_host']}:{config['server_port']}")

    return config

class SimpleKernel:
    """Fallback kernel for when AI services aren't available"""

    def __init__(self, database_service):
        self.database_service = database_service

    async def message(self, user_input: str, chat_history: ChatHistory) -> str:
        """Simple message handler that directly queries the database"""
        try:
            # Basic SQL query processing
            result = self.database_service.query(user_input)

            if isinstance(result, str):
                return result  # Error message
            elif result:
                return f"Query returned {len(result)} rows: {str(result[:3])}"
            else:
                return "Query executed successfully but returned no results."

        except Exception as e:
            logger.error(f"SimpleKernel error: {e}")
            return f"Error executing query: {str(e)}"

def initialize_database_service(config):
    """Initialize database service with proper error handling"""
    try:
        # Get credentials - prioritize environment variables
        if config['db_username'] and config['db_password']:
            logger.info(f"Using database credentials from environment for user: {config['db_username']}")
            database_service = SecureDatabase(
                server_name=config['server_name'],
                database_name=config['database_name'],
                username=config['db_username'],
                password=config['db_password']
            )
        else:
            # Try encrypted storage fallback
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

        # Test connection
        if database_service.test_connection():
            logger.info("✅ Database connection successful")
            return database_service
        else:
            raise Exception("Database connection test failed")

    except Exception as e:
        logger.error(f"Failed to initialize database service: {e}")
        raise

def initialize_azure_services(config):
    """Initialize Azure services (optional)"""
    credential = None
    speech_service = None

    # Initialize Azure credential
    try:
        if config['openai_endpoint'] and config['openai_deployment_name']:
            credential = DefaultAzureCredential()
            logger.info("✅ Azure credentials initialized")
        else:
            logger.info("Azure OpenAI not configured")
    except Exception as e:
        logger.warning(f"Azure credential initialization failed: {e}")

    # Initialize speech service
    try:
        if credential and config['speech_service_id'] and config['azure_location']:
            speech_service = Speech(
                credential=credential,
                resource_id=config['speech_service_id'],
                region=config['azure_location']
            )
            logger.info("✅ Speech service initialized")
    except Exception as e:
        logger.warning(f"Speech service initialization failed: {e}")

    return credential, speech_service

@app.on_event("startup")
async def startup_event():
    """Initialize the application on startup"""
    global kernel, chat_history

    try:
        logger.info("🚀 Starting Voice SQL API server...")

        # Load configuration
        config = load_environment_config()

        # Initialize database service
        database_service = initialize_database_service(config)

        # Initialize Azure services (optional)
        credential, speech_service = initialize_azure_services(config)

        # Initialize the semantic kernel (now with built-in token refresh)
        if credential and config['openai_endpoint'] and config['openai_deployment_name']:
            try:
                kernel = Kernel(
                    database_service=database_service,
                    credential=credential,
                    openai_endpoint=config['openai_endpoint'],
                    openai_deployment_name=config['openai_deployment_name']
                )
                logger.info("✅ Semantic kernel initialized with automatic token refresh")
            except Exception as e:
                logger.error(f"AI kernel initialization failed: {e}")
                logger.info("Falling back to simple kernel")
                kernel = SimpleKernel(database_service=database_service)
        else:
            logger.info("Using simple kernel (no AI services)")
            kernel = SimpleKernel(database_service=database_service)

        # Initialize chat history
        chat_history = ChatHistory()

        # Log startup summary
        username = config['db_username'] or "trusted_connection"
        logger.info("✅ Voice SQL API server ready!")
        logger.info(f"   Database: {config['database_name']} on {config['server_name']}")
        logger.info(f"   Security: {'Authenticated user' if config['db_username'] else 'Trusted connection'}")
        logger.info(f"   AI: {'Enabled with auto token refresh' if hasattr(kernel, 'chat_completion') else 'Disabled'}")
        logger.info(f"   Speech: {'Enabled' if speech_service else 'Disabled'}")

    except Exception as e:
        logger.error(f"❌ Critical startup failure: {e}")
        # Create minimal functionality
        try:
            config = load_environment_config()
            database_service = initialize_database_service(config)
            kernel = SimpleKernel(database_service=database_service)
            chat_history = ChatHistory()
            logger.info("✅ Minimal server functionality initialized")
        except Exception as minimal_error:
            logger.error(f"❌ Even minimal initialization failed: {minimal_error}")
            raise

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    global shutdown_requested
    shutdown_requested = True
    logger.info("Voice SQL API server shutting down...")

# Health and status endpoints
@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "Voice SQL API is running",
        "status": "healthy",
        "mode": "production"
    }

@app.get("/health")
async def health_check():
    """Health check endpoint for monitoring"""
    try:
        # Test database connection
        db_status = False
        if kernel and hasattr(kernel, 'database_service'):
            db_status = kernel.database_service.test_connection()

        # Get credential info
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
                "token_refresh": "automatic" if hasattr(kernel, '_refresh_token_and_reinitialize') else "manual"
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
    """Process a natural language question with optional export"""
    try:
        if not kernel:
            raise HTTPException(status_code=503, detail="Service not initialized")

        logger.info(f"Processing question: {request.question}")

        # If user specifically requested export, modify the question
        if request.export_format:
            export_instruction = f" Please export the results to {request.export_format} format."
            enhanced_question = request.question + export_instruction
        else:
            enhanced_question = request.question

        # Process the question through the kernel (now with automatic token refresh)
        response = await kernel.message(enhanced_question, chat_history)

        logger.info("Response generated successfully")

        return QueryResponse(
            answer=str(response),
            status="success"
        )

    except Exception as e:
        logger.error(f"Error processing question: {e}")
        raise HTTPException(status_code=500, detail=f"Error processing question: {str(e)}")

@app.get("/status")
async def get_detailed_status():
    """Get detailed server status for monitoring"""
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
                "speech_service": "configured" if config['speech_service_id'] else "not_configured",
                "token_management": "automatic" if hasattr(kernel, '_refresh_token_and_reinitialize') else "none"
            },
            "environment": {
                "env_file_loaded": any(Path(p).exists() for p in [".env", Path(__file__).parent / ".env"]),
                "credentials_in_env": bool(config['db_username'] and config['db_password'])
            },
            "chat_history_length": len(chat_history) if chat_history else 0
        }
    except Exception as e:
        logger.error(f"Status check failed: {e}")
        raise HTTPException(status_code=500, detail="Status check failed")

@app.get("/exports")
async def list_exports():
    """List available export files"""
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

        # Also include TXT files
        for file in export_dir.glob("*.txt"):
            stat = file.stat()
            exports.append({
                "filename": file.name,
                "size_mb": round(stat.st_size / (1024 * 1024), 2),
                "created": stat.st_ctime,
                "download_url": f"/download/{file.name}"
            })

        # Sort by creation time, newest first
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
    """Download an exported file"""
    try:
        export_dir = Path("C:/Logs/VoiceSQL/exports")
        file_path = export_dir / filename

        # Security: ensure the file is in the exports directory
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
    """Delete an exported file"""
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
    """Main entry point for production server"""
    import uvicorn

    try:
        # Load configuration
        config = load_environment_config()

        logger.info(f"Starting production server on {config['server_host']}:{config['server_port']}")
        logger.info(f"Process ID: {os.getpid()}")
        logger.info(f"Working directory: {os.getcwd()}")

        # Run the server
        uvicorn.run(
            "server_api:app",
            host=config['server_host'],
            port=config['server_port'],
            reload=False,  # Never reload in production
            log_level="info",
            access_log=True
        )

    except KeyboardInterrupt:
        logger.info("Server shutdown requested by user")
    except Exception as e:
        logger.error(f"Critical server error: {e}")
        logger.error("Server will exit and be restarted by Task Scheduler")
        sys.exit(1)  # Exit with error code so Task Scheduler restarts
    finally:
        logger.info("Server process ending")

if __name__ == "__main__":
    main()