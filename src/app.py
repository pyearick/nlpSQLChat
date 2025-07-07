import os
import sys
import asyncio
import logging

from dotenv import load_dotenv
from azure.identity import DefaultAzureCredential
from semantic_kernel.contents.chat_history import ChatHistory

from src.speech import Speech
from src.kernel import Kernel
from src.database import Database
from src.orchestrator import Orchestrator

if getattr(sys, 'frozen', False):
    # PyInstaller temp path
    base_dir = sys._MEIPASS
else:
    base_dir = os.path.dirname(__file__)

log_path = os.path.join(os.path.dirname(sys.executable), "NLP_app.log")

logging.basicConfig(
    filename=log_path,
    format="[%(asctime)s - %(name)s:%(lineno)d - %(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


async def main():
    load_dotenv()

    server_name = os.getenv("SQL_SERVER_NAME", "BI-SQL001")
    database_name = os.getenv("SQL_DATABASE_NAME", "CRPAF")
    speech_service_id = os.getenv("SPEECH_SERVICE_ID")
    azure_location = os.getenv("AZURE_LOCATION")
    openai_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    openai_deployment_name = os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT_NAME")

    # Only used for OpenAI / Speech, not database anymore
    credential = DefaultAzureCredential()

    # Use trusted connection to internal SQL Server
    database_service = Database(server_name=server_name, database_name=database_name)
    database_service.setup()

    speech_service = None
    try:
        speech_service = Speech(credential=credential, resource_id=speech_service_id, region=azure_location)
    except RuntimeError as ex:
        logger.warning(f"Speech service not initialized (likely no microphone): {ex}")

    kernel = Kernel(database_service=database_service,
                    credential=credential,
                    openai_endpoint=openai_endpoint,
                    openai_deployment_name=openai_deployment_name)

    chat_history = ChatHistory()
    orchestrator = Orchestrator(speech_service=speech_service, kernel=kernel)

    await orchestrator.run(chat_history=chat_history)


if __name__ == "__main__":
    asyncio.run(main())
