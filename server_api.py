# server_api.py - Updated with secure database connection
import os
import sys
import asyncio
import logging
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv
from azure.identity import DefaultAzureCredential
from semantic_kernel.contents.chat_history import ChatHistory

# Import your existing modules
from src.speech import Speech
from src.kernel import Kernel
from src.orchestrator import Orchestrator

# NEW: Import the secure database service
from src.database.secure_service import create_database_service, get_database_credentials

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s - %(name)s:%(lineno)d - %(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# FastAPI app
app = FastAPI(title="Voice SQL API", version="1.0.0")

# Global variables
kernel = None
chat_history = None


class QueryRequest(BaseModel):
    question: str


class QueryResponse(BaseModel):
    answer: str
    status: str = "success"


@app.on_event("startup")
async def startup_event():
    """Initialize the application on startup"""
    global kernel, chat_history

    try:
        logger.info("Starting Voice SQL API server...")

        # Load environment variables
        load_dotenv()

        # Get database configuration
        server_name = os.getenv("SQL_SERVER_NAME", "BI-SQL001")
        database_name = os.getenv("SQL_DATABASE_NAME", "CRPAF")

        # Check for database credentials
        username, password = get_database_credentials()
        if username:
            logger.info(f"Using secure database connection with user: {username}")
        else:
            logger.warning("No database credentials found - using trusted connection")
            logger.info("To set up secure credentials, run: python setup_credentials.py")

        # UPDATED: Create secure database service
        try:
            database_service = create_database_service(server_name, database_name)

            # Test the connection
            if database_service.test_connection():
                logger.info("✅ Database connection successful")
            else:
                logger.error("❌ Database connection failed")
                raise Exception("Database connection test failed")

        except Exception as e:
            logger.error(f"❌ Failed to create database service: {e}")
            raise

        # Initialize Azure services (optional for speech/AI)
        speech_service_id = os.getenv("SPEECH_SERVICE_ID")
        azure_location = os.getenv("AZURE_LOCATION")
        openai_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
        openai_deployment_name = os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT_NAME")

        credential = None
        speech_service = None

        # Try to initialize Azure services (optional)
        try:
            if openai_endpoint and openai_deployment_name:
                credential = DefaultAzureCredential()
                logger.info("Azure credentials initialized")
            else:
                logger.warning("Azure OpenAI not configured - some features may be limited")
        except Exception as e:
            logger.warning(f"Azure credential initialization failed: {e}")

        # Initialize speech service (optional)
        try:
            if credential and speech_service_id and azure_location:
                speech_service = Speech(
                    credential=credential,
                    resource_id=speech_service_id,
                    region=azure_location
                )
                logger.info("Speech service initialized")
        except Exception as e:
            logger.warning(f"Speech service initialization failed: {e}")

        # Initialize the semantic kernel
        if credential and openai_endpoint and openai_deployment_name:
            kernel = Kernel(
                database_service=database_service,
                credential=credential,
                openai_endpoint=openai_endpoint,
                openai_deployment_name=openai_deployment_name
            )
            logger.info("✅ Semantic kernel initialized with AI")
        else:
            # Fallback: create a simple kernel without AI (for testing)
            logger.warning("⚠️ Creating basic kernel without AI services")
            kernel = SimpleKernel(database_service=database_service)

        # Initialize chat history
        chat_history = ChatHistory()

        logger.info("🚀 Voice SQL API server ready!")
        logger.info(f"Database: {database_name} on {server_name}")
        logger.info(f"Security: {'✅ Secure user' if username else '⚠️ Trusted connection'}")

    except Exception as e:
        logger.error(f"❌ Failed to initialize server: {e}")
        raise


class SimpleKernel:
    """Fallback kernel for when AI services aren't available"""

    def __init__(self, database_service):
        self.database_service = database_service

    async def message(self, user_input: str, chat_history: ChatHistory) -> str:
        """Simple message handler that directly queries the database"""
        try:
            # For now, treat the input as a direct SQL query
            # In production, you'd want to add SQL generation logic here
            result = self.database_service.query(user_input)

            if isinstance(result, str):
                return result  # Error message
            elif result:
                return f"Query returned {len(result)} rows: {str(result[:5])}"  # Show first 5 rows
            else:
                return "Query executed successfully but returned no results."

        except Exception as e:
            return f"Error executing query: {str(e)}"


@app.get("/")
async def root():
    """Root endpoint"""
    return {"message": "Voice SQL API is running", "status": "healthy"}


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    try:
        # Test database connection
        if kernel and hasattr(kernel, 'database_service'):
            db_status = kernel.database_service.test_connection()
        else:
            db_status = False

        return {
            "status": "healthy" if db_status else "degraded",
            "database": "connected" if db_status else "disconnected",
            "ai_enabled": hasattr(kernel, 'chat_completion') if kernel else False
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=500, detail="Health check failed")


@app.post("/ask")
async def ask_question(request: QueryRequest) -> QueryResponse:
    """Process a natural language question"""
    try:
        if not kernel:
            raise HTTPException(status_code=503, detail="Service not initialized")

        logger.info(f"Processing question: {request.question}")

        # Process the question through the kernel
        response = await kernel.message(request.question, chat_history)

        logger.info(f"Response generated successfully")

        return QueryResponse(
            answer=str(response),
            status="success"
        )

    except Exception as e:
        logger.error(f"Error processing question: {e}")
        raise HTTPException(status_code=500, detail=f"Error processing question: {str(e)}")


@app.get("/status")
async def get_status():
    """Get detailed server status"""
    try:
        username, _ = get_database_credentials()

        return {
            "server": "running",
            "database_user": username if username else "trusted_connection",
            "security_mode": "authenticated" if username else "trusted",
            "kernel_type": "ai_enabled" if hasattr(kernel, 'chat_completion') else "basic",
            "chat_history_length": len(chat_history) if chat_history else 0
        }
    except Exception as e:
        logger.error(f"Status check failed: {e}")
        raise HTTPException(status_code=500, detail="Status check failed")


def main():
    """Main entry point for running the server"""
    import uvicorn

    # Get configuration
    host = os.getenv("SERVER_HOST", "0.0.0.0")
    port = int(os.getenv("SERVER_PORT", "8000"))
    debug = os.getenv("DEBUG", "false").lower() == "true"

    logger.info(f"Starting server on {host}:{port}")

    try:
        uvicorn.run(
            "server_api:app",
            host=host,
            port=port,
            reload=debug,
            log_level="info"
        )
    except KeyboardInterrupt:
        logger.info("Server shutdown requested")
    except Exception as e:
        logger.error(f"Server error: {e}")
        raise


if __name__ == "__main__":
    main()