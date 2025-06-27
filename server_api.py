# server_api.py - FastAPI server to add to your existing SQL host
import os
import sys
import asyncio
import logging
from typing import Dict, Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
from azure.identity import DefaultAzureCredential
from semantic_kernel.contents.chat_history import ChatHistory

# Import your existing components
from src.kernel import Kernel
from src.database import Database

# Load environment
load_dotenv()

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# FastAPI app
app = FastAPI(title="Voice SQL Server", version="1.0.0")

# Enable CORS for laptop clients
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify your laptop IPs
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global variables for your existing components
database_service = None
kernel = None
chat_history = ChatHistory()


class QuestionRequest(BaseModel):
    question: str


class QuestionResponse(BaseModel):
    answer: str
    query_used: str = None


@app.on_event("startup")
async def startup_event():
    """Initialize your existing components on startup"""
    global database_service, kernel

    try:
        logger.info("Initializing Voice SQL Server...")

        # Get configuration
        server_name = os.getenv("SQL_SERVER_NAME", "BI-SQL001")
        database_name = os.getenv("SQL_DATABASE_NAME", "CRPAF")
        openai_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
        openai_deployment_name = os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT_NAME")

        # Initialize database (your existing code)
        logger.info("Setting up database...")
        database_service = Database(server_name=server_name, database_name=database_name)
        database_service.setup()
        logger.info("✅ Database connected")

        # Initialize Azure credential (your existing code)
        logger.info("Setting up Azure credentials...")
        credential = DefaultAzureCredential()
        logger.info("✅ Azure credentials loaded")

        # Initialize kernel (your existing code)
        logger.info("Setting up AI kernel...")
        kernel = Kernel(
            database_service=database_service,
            credential=credential,
            openai_endpoint=openai_endpoint,
            openai_deployment_name=openai_deployment_name
        )
        logger.info("✅ AI kernel initialized")

        logger.info("🚀 Voice SQL Server ready!")

    except Exception as e:
        logger.error(f"Failed to initialize server: {e}")
        raise


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "database": "connected" if database_service else "disconnected",
        "ai_kernel": "ready" if kernel else "not_ready"
    }


@app.post("/ask", response_model=QuestionResponse)
async def ask_question(request: QuestionRequest):
    """Process a question using your existing NLP-to-SQL system"""
    global chat_history

    try:
        if not kernel:
            raise HTTPException(status_code=500, detail="AI kernel not initialized")

        logger.info(f"Processing question: {request.question}")

        # Use your existing kernel to process the question
        response = await kernel.message(user_input=request.question, chat_history=chat_history)
        answer = str(response)

        logger.info(f"Generated response: {answer}")

        return QuestionResponse(answer=answer)

    except Exception as e:
        logger.error(f"Error processing question: {e}")
        raise HTTPException(status_code=500, detail=f"Error processing question: {str(e)}")


@app.get("/")
async def root():
    """Root endpoint with API info"""
    return {
        "message": "Voice SQL Server API",
        "endpoints": {
            "health": "/health",
            "ask": "/ask (POST)",
        },
        "status": "running"
    }


if __name__ == "__main__":
    import uvicorn

    # Run the server
    uvicorn.run(
        "server_api:app",
        host="0.0.0.0",  # Listen on all interfaces
        port=8000,
        reload=False,
        log_level="info"
    )