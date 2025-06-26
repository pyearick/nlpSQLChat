# thin_voice_client.py - Lightweight client for laptops
import os
import sys
import json
import requests
from typing import Optional

# Import Windows speech service with better error handling
SPEECH_AVAILABLE = False
speech_error = None

try:
    import pyttsx3

    TTS_AVAILABLE = True
except ImportError as e:
    TTS_AVAILABLE = False
    speech_error = f"pyttsx3 not available: {e}"

try:
    import speech_recognition as sr
    import pyaudio  # Explicitly check for pyaudio

    STT_AVAILABLE = True
except ImportError as e:
    STT_AVAILABLE = False
    if speech_error:
        speech_error += f" | speech_recognition/pyaudio not available: {e}"
    else:
        speech_error = f"speech_recognition/pyaudio not available: {e}"

SPEECH_AVAILABLE = TTS_AVAILABLE and STT_AVAILABLE


class VoiceClient:
    def __init__(self, server_url: str):
        self.server_url = server_url.rstrip('/')
        self.session = requests.Session()
        self.session.timeout = 30
        self.tts_engine = None
        self.recognizer = None
        self.microphone = None

        # Initialize TTS if available
        if TTS_AVAILABLE:
            try:
                self.tts_engine = pyttsx3.init()
                rate = self.tts_engine.getProperty('rate')
                self.tts_engine.setProperty('rate', rate - 50)
            except Exception as e:
                print(f"Warning: TTS initialization failed: {e}")
                self.tts_engine = None

        # Initialize STT if available
        if STT_AVAILABLE:
            try:
                self.recognizer = sr.Recognizer()
                self.recognizer.energy_threshold = 300
                self.recognizer.dynamic_energy_threshold = True
                self.recognizer.pause_threshold = 0.8
                self.microphone = sr.Microphone()

                # Adjust for ambient noise
                print("Adjusting for ambient noise... Please wait.")
                with self.microphone as source:
                    self.recognizer.adjust_for_ambient_noise(source, duration=2)
                print(f"Ready! Energy threshold: {self.recognizer.energy_threshold}")
            except Exception as e:
                print(f"Warning: Speech recognition initialization failed: {e}")
                self.recognizer = None
                self.microphone = None

    def speak(self, text: str) -> None:
        """Convert text to speech"""
        print(f"Assistant: {text}")

        if self.tts_engine:
            try:
                self.tts_engine.say(text)
                self.tts_engine.runAndWait()
            except Exception as e:
                print(f"TTS Error: {e}")

    def listen(self) -> Optional[str]:
        """Listen for speech and convert to text"""
        if not self.recognizer or not self.microphone:
            return input("You: ")

        try:
            print("🎤 Listening... (speak now)")
            with self.microphone as source:
                audio = self.recognizer.listen(source, timeout=15, phrase_time_limit=10)

            print("🔄 Processing speech...")
            text = self.recognizer.recognize_google(audio)
            print(f"You: {text}")
            return text

        except sr.WaitTimeoutError:
            print("⏰ Timeout - no speech detected")
            return None
        except sr.UnknownValueError:
            print("❓ Could not understand speech")
            return None
        except sr.RequestError as e:
            print(f"🌐 Speech recognition error: {e}")
            return None
        except Exception as e:
            print(f"❌ Error: {e}")
            return None

    def query_server(self, question: str) -> str:
        """Send question to server and get response"""
        try:
            payload = {"question": question}

            print("📡 Sending to server...")
            response = self.session.post(
                f"{self.server_url}/ask",
                json=payload,
                headers={"Content-Type": "application/json"}
            )

            if response.status_code == 200:
                data = response.json()
                return data.get("answer", "No answer received")
            else:
                return f"Server error: {response.status_code} - {response.text}"

        except requests.exceptions.ConnectionError:
            return "❌ Cannot connect to server. Is the server running?"
        except requests.exceptions.Timeout:
            return "⏰ Server timeout. Please try again."
        except Exception as e:
            return f"❌ Error communicating with server: {e}"

    def test_connection(self) -> bool:
        """Test connection to server"""
        try:
            response = self.session.get(f"{self.server_url}/health", timeout=5)
            return response.status_code == 200
        except:
            return False

    def run(self):
        """Main application loop"""
        print("=== Voice SQL Client ===")

        # Show speech status
        if speech_error:
            print(f"⚠️ Speech libraries issue: {speech_error}")

        if SPEECH_AVAILABLE:
            print("🎤 Full voice mode enabled")
        elif TTS_AVAILABLE:
            print("🔊 Text-to-speech available, speech recognition disabled")
        else:
            print("⌨️ Text-only mode")

        # Test server connection
        print(f"Testing connection to {self.server_url}...")
        if not self.test_connection():
            print("❌ Cannot connect to server!")
            print("Make sure the server is running and accessible.")
            print(f"Expected server URL: {self.server_url}")
            input("Press Enter to exit...")
            return

        print("✅ Connected to server successfully!")

        if SPEECH_AVAILABLE:
            self.speak("Voice SQL Client ready. What would you like to know about the database?")
        else:
            print("Voice SQL Client ready. What would you like to know about the database?")

        print("\nYou can ask questions like:")
        print("- 'How many records are in the ExplorationProduction table?'")
        print("- 'Show me the top 5 wells by production volume'")
        print("- 'What operators are in the database?'")
        print("- Type 'exit' to quit")
        print()

        while True:
            try:
                # Get user input (voice or text)
                user_input = self.listen()

                if user_input is None:
                    continue

                if user_input.lower() in ['exit', 'quit', 'goodbye']:
                    if self.tts_engine:
                        self.speak("Goodbye!")
                    else:
                        print("Goodbye!")
                    break

                # Send to server and get response
                answer = self.query_server(user_input)

                # Speak/display the response
                self.speak(answer)

                if SPEECH_AVAILABLE:
                    print("\n" + "=" * 50)

            except KeyboardInterrupt:
                print("\nExiting...")
                break
            except Exception as e:
                print(f"Error: {e}")
                continue


def main():
    """Main entry point"""
    # Default server URL - can be configured via environment variable
    server_url = os.getenv("VOICE_SQL_SERVER", "http://BI-SQL001:8000")

    print(f"Voice SQL Client starting...")
    print(f"Server URL: {server_url}")

    client = VoiceClient(server_url)
    client.run()


if __name__ == "__main__":
    main()