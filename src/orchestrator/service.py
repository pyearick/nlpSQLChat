import logging

from semantic_kernel.contents.chat_history import ChatHistory

from src.speech import Speech
from src.kernel import Kernel


logger = logging.getLogger(__name__)


class Orchestrator:
    def __init__(self, speech_service: Speech, kernel: Kernel) -> None:
        self.speech_service = speech_service
        self.kernel = kernel

    async def run(self, chat_history: ChatHistory) -> None:
        if not self.speech_service:
            print("Speech input is not available. Switching to text input mode.")
            while True:
                try:
                    user_input = input("Enter your question (or type 'exit' to quit): ")
                    if user_input.lower() == "exit":
                        break

                    response = await self.kernel.message(user_input=user_input, chat_history=chat_history)
                    print("Assistant >", response)
                except Exception as e:
                    logger.error(f"Error during text interaction: {e}")
        else:
            while True:
                try:
                    self.speech_service.synthesize("Please ask your query through the Microphone:")
                    print("Listening:")

                    # Collect user input
                    user_input = self.speech_service.recognize()
                    print("User > " + user_input)

                    # Terminate the loop if the user says "exit"
                    if user_input == "exit":
                        break

                    response = await self.kernel.message(user_input=user_input, chat_history=chat_history)

                    print("Assistant > " + response)
                    self.speech_service.synthesize(response)

                    self.speech_service.synthesize("Do you have any other query? Say Yes to Continue")

                    # Taking Input from the user
                    print("Listening:")
                    user_input = self.speech_service.recognize()
                    print("User > " + user_input)
                    if user_input != 'Yes.':
                        self.speech_service.synthesize("Thank you for using the Kiosk Bot. Have a nice day.")
                        break
                except Exception as e:
                    logger.error("An exception occurred: {}".format(e))
                    self.speech_service.synthesize("An error occurred. Let's try again.")
                    continue
