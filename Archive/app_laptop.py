# src/speech/windows_service.py
# Drop-in replacement for Azure Speech service using Windows native speech APIs
import logging

try:
    import pyttsx3
    import speech_recognition as sr

    SPEECH_AVAILABLE = True
except ImportError:
    SPEECH_AVAILABLE = False

logger = logging.getLogger(__name__)


class WindowsSpeech:
    """
    Drop-in replacement for Azure Speech service using Windows native speech APIs.
    Maintains the same interface as the original Speech class.
    """

    def __init__(self, **kwargs) -> None:
        """
        Initialize Windows speech service.
        **kwargs allows this to accept any parameters (for compatibility with Azure Speech)
        but we ignore them since we're using local speech.
        """
        if not SPEECH_AVAILABLE:
            raise RuntimeError(
                "Windows speech libraries not available. Install with: pip install pyttsx3 SpeechRecognition")

        # Initialize text-to-speech engine
        try:
            self.tts_engine = pyttsx3.init()

            # Configure speech rate for better understanding
            rate = self.tts_engine.getProperty('rate')
            self.tts_engine.setProperty('rate', rate - 50)  # Slower speech

            # Set voice to female if available (optional)
            voices = self.tts_engine.getProperty('voices')
            if voices and len(voices) > 1:
                # Try to find a female voice
                for voice in voices:
                    if 'female' in voice.name.lower() or 'zira' in voice.name.lower():
                        self.tts_engine.setProperty('voice', voice.id)
                        break

        except Exception as e:
            logger.error(f"Failed to initialize text-to-speech: {e}")
            raise RuntimeError(f"Text-to-speech initialization failed: {e}")

        # Initialize speech recognition
        try:
            self.recognizer = sr.Recognizer()

            # Configure recognizer for better accuracy
            self.recognizer.energy_threshold = 300  # Minimum audio energy
            self.recognizer.dynamic_energy_threshold = True
            self.recognizer.pause_threshold = 0.8  # Seconds of silence to mark end

            # List available microphones for debugging
            logger.info("Available microphones:")
            for index, name in enumerate(sr.Microphone.list_microphone_names()):
                logger.info(f"  {index}: {name}")

            # Use default microphone
            self.microphone = sr.Microphone()

            # Adjust for ambient noise
            logger.info("Adjusting for ambient noise...")
            with self.microphone as source:
                self.recognizer.adjust_for_ambient_noise(source, duration=2)
            logger.info(f"Set minimum energy threshold to {self.recognizer.energy_threshold}")

        except Exception as e:
            logger.error(f"Failed to initialize speech recognition: {e}")
            raise RuntimeError(f"Speech recognition initialization failed: {e}")

        logger.info("Windows speech service initialized successfully")

    def recognize(self) -> str:
        """
        Recognize speech from the microphone and convert it to text.
        Maintains the same interface as Azure Speech service.
        """
        try:
            logger.debug("Starting speech recognition...")

            with self.microphone as source:
                logger.debug(f"Listening with energy threshold: {self.recognizer.energy_threshold}")
                # Listen for audio input with generous timeouts
                audio = self.recognizer.listen(source, timeout=15, phrase_time_limit=10)

            logger.debug("Processing speech...")

            # Try Google Speech Recognition first (requires internet)
            try:
                text = self.recognizer.recognize_google(audio)
                logger.info(f"Recognized text: {text}")
                return text

            except sr.RequestError:
                # If Google fails (no internet), try Windows Speech Recognition
                logger.warning("Google speech recognition failed, trying Windows Speech Recognition...")
                try:
                    text = self.recognizer.recognize_sphinx(audio)
                    logger.info(f"Recognized text (Windows): {text}")
                    return text
                except:
                    # If both fail, return a generic error
                    logger.error("Both speech recognition methods failed")
                    return "speech recognition error"

        except sr.WaitTimeoutError:
            logger.warning("Speech recognition timeout - no speech detected")
            return "timeout"

        except sr.UnknownValueError:
            logger.warning("Could not understand audio")
            return "unknown"

        except Exception as e:
            logger.error(f"Speech recognition error: {e}")
            return "error"

    def synthesize(self, text: str) -> None:
        """
        Synthesize text to speech and play it through the speaker.
        Maintains the same interface as Azure Speech service.
        """
        try:
            logger.debug(f"Synthesizing speech for: {text}")

            # Speak the text
            self.tts_engine.say(text)
            self.tts_engine.runAndWait()

            logger.info(f"Speech synthesized for text [{text}]")

        except Exception as e:
            logger.error(f"Speech synthesis failed: {e}")
            # Don't raise exception - just log the error and continue
            print(f"Speech synthesis error: {e}")


# Compatibility wrapper - allows existing code to work unchanged
class Speech(WindowsSpeech):
    """
    Compatibility wrapper that maintains the original class name and interface.
    This allows existing code to work without any changes.
    """

    def __init__(self, credential=None, resource_id=None, region=None, **kwargs):
        """
        Accept the same parameters as Azure Speech service but ignore them.
        This allows the existing app.py to work without modification.
        """
        # Log that we're using Windows speech instead of Azure
        if credential or resource_id or region:
            logger.info("Azure Speech parameters provided but using Windows native speech instead")

        # Initialize with Windows speech
        super().__init__(**kwargs)