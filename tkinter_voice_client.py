# tkinter_voice_client.py - GUI Voice SQL Client
import os
import sys
import json
import requests
import threading
import time
from typing import Optional
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
from datetime import datetime

# Speech imports with error handling
TTS_AVAILABLE = False
STT_AVAILABLE = False
speech_error = None

try:
    import pyttsx3

    TTS_AVAILABLE = True
except ImportError as e:
    speech_error = f"pyttsx3 not available: {e}"

try:
    import speech_recognition as sr
    import pyaudio

    STT_AVAILABLE = True
except ImportError as e:
    if speech_error:
        speech_error += f" | speech_recognition/pyaudio not available: {e}"
    else:
        speech_error = f"speech_recognition/pyaudio not available: {e}"

SPEECH_AVAILABLE = TTS_AVAILABLE and STT_AVAILABLE


class VoiceClientGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Voice SQL Client")
        self.root.geometry("800x600")
        self.root.minsize(600, 400)

        # Configuration
        self.server_url = os.getenv("VOICE_SQL_SERVER", "http://BI-SQL001:8000").rstrip('/')
        self.session = requests.Session()
        self.session.timeout = 30

        # Speech components
        self.tts_engine = None
        self.recognizer = None
        self.microphone = None
        self.is_listening = False
        self.is_speaking = False

        # Settings
        self.auto_speak_responses = tk.BooleanVar(value=True)
        self.voice_input_enabled = tk.BooleanVar(value=True)

        self.setup_speech()
        self.create_widgets()
        self.test_connection()

    def setup_speech(self):
        """Initialize speech components"""
        # Initialize TTS
        if TTS_AVAILABLE:
            try:
                self.tts_engine = pyttsx3.init()
                rate = self.tts_engine.getProperty('rate')
                self.tts_engine.setProperty('rate', rate - 30)
                voices = self.tts_engine.getProperty('voices')
                if voices:
                    # Try to use a female voice if available
                    for voice in voices:
                        if 'female' in voice.name.lower() or 'zira' in voice.name.lower():
                            self.tts_engine.setProperty('voice', voice.id)
                            break
            except Exception as e:
                self.log_message(f"TTS initialization failed: {e}", "error")
                self.tts_engine = None

        # Initialize STT
        if STT_AVAILABLE:
            try:
                self.recognizer = sr.Recognizer()
                self.recognizer.energy_threshold = 300
                self.recognizer.dynamic_energy_threshold = True
                self.recognizer.pause_threshold = 0.8
                self.microphone = sr.Microphone()

                # Adjust for ambient noise in background
                threading.Thread(target=self.calibrate_microphone, daemon=True).start()
            except Exception as e:
                self.log_message(f"Speech recognition initialization failed: {e}", "error")
                self.recognizer = None
                self.microphone = None

    def calibrate_microphone(self):
        """Calibrate microphone for ambient noise"""
        try:
            with self.microphone as source:
                self.recognizer.adjust_for_ambient_noise(source, duration=1)
            self.log_message("Microphone calibrated", "info")
        except Exception as e:
            self.log_message(f"Microphone calibration failed: {e}", "error")

    def create_widgets(self):
        """Create the GUI layout"""
        # Main container
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # Configure grid weights
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(1, weight=1)

        # Top toolbar
        self.create_toolbar(main_frame)

        # Chat history area
        self.create_chat_area(main_frame)

        # Input area
        self.create_input_area(main_frame)

        # Status bar
        self.create_status_bar(main_frame)

        # Update GUI state
        self.update_speech_status()

    def create_toolbar(self, parent):
        """Create the top toolbar"""
        toolbar = ttk.Frame(parent)
        toolbar.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=(0, 10))
        toolbar.columnconfigure(3, weight=1)

        # Mode buttons
        self.text_mode_btn = ttk.Button(toolbar, text="📝 Text Mode", command=self.set_text_mode)
        self.text_mode_btn.grid(row=0, column=0, padx=(0, 5))

        self.voice_mode_btn = ttk.Button(toolbar, text="🎤 Voice Mode", command=self.set_voice_mode)
        self.voice_mode_btn.grid(row=0, column=1, padx=(0, 5))

        # Settings button
        ttk.Button(toolbar, text="⚙️ Settings", command=self.show_settings).grid(row=0, column=2, padx=(0, 10))

        # Connection status
        self.connection_label = ttk.Label(toolbar, text="🔴 Disconnected")
        self.connection_label.grid(row=0, column=4, sticky=tk.E)

    def create_chat_area(self, parent):
        """Create the chat history area"""
        chat_frame = ttk.LabelFrame(parent, text="Conversation", padding="5")
        chat_frame.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 10))
        chat_frame.columnconfigure(0, weight=1)
        chat_frame.rowconfigure(0, weight=1)

        # Chat display
        self.chat_display = scrolledtext.ScrolledText(
            chat_frame,
            wrap=tk.WORD,
            height=15,
            font=('Consolas', 10),
            state=tk.DISABLED
        )
        self.chat_display.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # Configure text tags for styling
        self.chat_display.tag_configure("user", foreground="blue", font=('Consolas', 10, 'bold'))
        self.chat_display.tag_configure("assistant", foreground="green", font=('Consolas', 10))
        self.chat_display.tag_configure("system", foreground="gray", font=('Consolas', 9, 'italic'))
        self.chat_display.tag_configure("error", foreground="red", font=('Consolas', 10))

        # Context menu for chat
        self.create_chat_context_menu()

    def create_chat_context_menu(self):
        """Create right-click context menu for chat"""
        self.chat_menu = tk.Menu(self.root, tearoff=0)
        self.chat_menu.add_command(label="Copy", command=self.copy_selection)
        self.chat_menu.add_command(label="Select All", command=self.select_all_chat)
        self.chat_menu.add_separator()
        self.chat_menu.add_command(label="Clear History", command=self.clear_chat)

        self.chat_display.bind("<Button-3>", self.show_chat_context_menu)

    def create_input_area(self, parent):
        """Create the input area"""
        input_frame = ttk.LabelFrame(parent, text="Input", padding="5")
        input_frame.grid(row=2, column=0, sticky=(tk.W, tk.E), pady=(0, 10))
        input_frame.columnconfigure(0, weight=1)

        # Text input
        text_input_frame = ttk.Frame(input_frame)
        text_input_frame.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=(0, 5))
        text_input_frame.columnconfigure(0, weight=1)

        self.input_entry = ttk.Entry(text_input_frame, font=('Consolas', 10))
        self.input_entry.grid(row=0, column=0, sticky=(tk.W, tk.E), padx=(0, 5))
        self.input_entry.bind('<Return>', self.send_message)
        self.input_entry.bind('<Control-Return>', self.send_message)

        self.send_btn = ttk.Button(text_input_frame, text="Send", command=self.send_message)
        self.send_btn.grid(row=0, column=1)

        # Voice controls
        voice_frame = ttk.Frame(input_frame)
        voice_frame.grid(row=1, column=0, sticky=(tk.W, tk.E))

        self.voice_btn = ttk.Button(voice_frame, text="🎤 Start Voice Input", command=self.toggle_voice_input)
        self.voice_btn.grid(row=0, column=0, padx=(0, 5))

        self.stop_btn = ttk.Button(voice_frame, text="⏹️ Stop", command=self.stop_all, state=tk.DISABLED)
        self.stop_btn.grid(row=0, column=1, padx=(0, 5))

        self.speak_btn = ttk.Button(voice_frame, text="🔊 Read Last Response", command=self.speak_last_response)
        self.speak_btn.grid(row=0, column=2, padx=(0, 10))

        # Voice status
        self.voice_status = ttk.Label(voice_frame, text="Ready")
        self.voice_status.grid(row=0, column=3, sticky=tk.W)

    def create_status_bar(self, parent):
        """Create the status bar"""
        status_frame = ttk.Frame(parent)
        status_frame.grid(row=3, column=0, sticky=(tk.W, tk.E))
        status_frame.columnconfigure(0, weight=1)

        self.status_label = ttk.Label(status_frame, text="Ready")
        self.status_label.grid(row=0, column=0, sticky=tk.W)

        # Speech capabilities indicator
        capabilities = []
        if TTS_AVAILABLE:
            capabilities.append("TTS")
        if STT_AVAILABLE:
            capabilities.append("STT")

        caps_text = f"Speech: {', '.join(capabilities) if capabilities else 'None'}"
        if speech_error and not capabilities:
            caps_text += f" ({speech_error.split('|')[0]})"

        ttk.Label(status_frame, text=caps_text).grid(row=0, column=1, sticky=tk.E)

    def update_speech_status(self):
        """Update the visual state based on speech availability"""
        if not STT_AVAILABLE:
            self.voice_btn.config(state=tk.DISABLED, text="🎤 Voice Unavailable")
            self.voice_mode_btn.config(state=tk.DISABLED)

        if not TTS_AVAILABLE:
            self.speak_btn.config(state=tk.DISABLED, text="🔊 TTS Unavailable")
            self.auto_speak_responses.set(False)

    def test_connection(self):
        """Test server connection"""

        def test():
            try:
                response = self.session.get(f"{self.server_url}/health", timeout=5)
                if response.status_code == 200:
                    self.root.after(0, lambda: self.connection_label.config(text="🟢 Connected", foreground="green"))
                    self.log_message("Connected to server successfully", "system")
                else:
                    self.root.after(0, lambda: self.connection_label.config(text="🟡 Server Error", foreground="orange"))
                    self.log_message(f"Server returned {response.status_code}", "error")
            except Exception as e:
                self.root.after(0, lambda: self.connection_label.config(text="🔴 Disconnected", foreground="red"))
                self.log_message(f"Connection failed: {e}", "error")

        threading.Thread(target=test, daemon=True).start()

    def log_message(self, message, msg_type="info"):
        """Add a message to the chat display"""
        timestamp = datetime.now().strftime("%H:%M:%S")

        self.chat_display.config(state=tk.NORMAL)

        if msg_type == "user":
            self.chat_display.insert(tk.END, f"[{timestamp}] You: ", "system")
            self.chat_display.insert(tk.END, f"{message}\n", "user")
        elif msg_type == "assistant":
            self.chat_display.insert(tk.END, f"[{timestamp}] Assistant: ", "system")
            self.chat_display.insert(tk.END, f"{message}\n", "assistant")
        elif msg_type == "error":
            self.chat_display.insert(tk.END, f"[{timestamp}] Error: ", "system")
            self.chat_display.insert(tk.END, f"{message}\n", "error")
        else:  # system/info
            self.chat_display.insert(tk.END, f"[{timestamp}] {message}\n", "system")

        self.chat_display.config(state=tk.DISABLED)
        self.chat_display.see(tk.END)

        # Store last response for repeat speaking
        if msg_type == "assistant":
            self.last_response = message

    def send_message(self, event=None):
        """Send a message to the server"""
        message = self.input_entry.get().strip()
        if not message:
            return

        self.input_entry.delete(0, tk.END)
        self.log_message(message, "user")

        # Check for exit
        if message.lower() in ['exit', 'quit', 'goodbye']:
            self.root.quit()
            return

        # Send to server in background
        threading.Thread(target=self.query_server, args=(message,), daemon=True).start()

    def query_server(self, question):
        """Query the server and handle response"""
        try:
            self.root.after(0, lambda: self.status_label.config(text="Sending query..."))

            payload = {"question": question}
            response = self.session.post(
                f"{self.server_url}/ask",
                json=payload,
                headers={"Content-Type": "application/json"}
            )

            if response.status_code == 200:
                data = response.json()
                answer = data.get("answer", "No answer received")
                self.root.after(0, lambda: self.handle_response(answer))
            else:
                error_msg = f"Server error: {response.status_code} - {response.text}"
                self.root.after(0, lambda: self.log_message(error_msg, "error"))

        except requests.exceptions.ConnectionError:
            self.root.after(0, lambda: self.log_message("Cannot connect to server. Is it running?", "error"))
        except requests.exceptions.Timeout:
            self.root.after(0, lambda: self.log_message("Server timeout. Please try again.", "error"))
        except Exception as e:
            self.root.after(0, lambda: self.log_message(f"Error: {e}", "error"))
        finally:
            self.root.after(0, lambda: self.status_label.config(text="Ready"))

    def handle_response(self, response):
        """Handle server response"""
        self.log_message(response, "assistant")

        # Auto-speak if enabled
        if self.auto_speak_responses.get() and self.tts_engine:
            self.speak_text(response)

    def speak_text(self, text):
        """Speak text using TTS"""
        if not self.tts_engine or self.is_speaking:
            return

        def speak():
            try:
                self.is_speaking = True
                self.root.after(0, lambda: self.voice_status.config(text="Speaking..."))
                self.tts_engine.say(text)
                self.tts_engine.runAndWait()
            except Exception as e:
                self.root.after(0, lambda: self.log_message(f"TTS Error: {e}", "error"))
            finally:
                self.is_speaking = False
                self.root.after(0, lambda: self.voice_status.config(text="Ready"))

        threading.Thread(target=speak, daemon=True).start()

    def speak_last_response(self):
        """Speak the last assistant response"""
        if hasattr(self, 'last_response'):
            self.speak_text(self.last_response)
        else:
            self.log_message("No response to speak", "system")

    def toggle_voice_input(self):
        """Toggle voice input on/off"""
        if not self.recognizer or not self.microphone:
            self.log_message("Voice input not available", "error")
            return

        if self.is_listening:
            self.stop_voice_input()
        else:
            self.start_voice_input()

    def start_voice_input(self):
        """Start listening for voice input"""
        if self.is_listening:
            return

        def listen():
            try:
                self.is_listening = True
                self.root.after(0, lambda: self.voice_btn.config(text="🎤 Listening...", state=tk.DISABLED))
                self.root.after(0, lambda: self.stop_btn.config(state=tk.NORMAL))
                self.root.after(0, lambda: self.voice_status.config(text="Listening..."))

                with self.microphone as source:
                    audio = self.recognizer.listen(source, timeout=15, phrase_time_limit=10)

                self.root.after(0, lambda: self.voice_status.config(text="Processing..."))
                text = self.recognizer.recognize_google(audio)

                # Put text in input field
                self.root.after(0, lambda: self.input_entry.delete(0, tk.END))
                self.root.after(0, lambda: self.input_entry.insert(0, text))
                self.root.after(0, lambda: self.log_message(f"Voice recognized: {text}", "system"))

            except sr.WaitTimeoutError:
                self.root.after(0, lambda: self.log_message("Voice timeout - no speech detected", "system"))
            except sr.UnknownValueError:
                self.root.after(0, lambda: self.log_message("Could not understand speech", "system"))
            except sr.RequestError as e:
                self.root.after(0, lambda: self.log_message(f"Speech recognition error: {e}", "error"))
            except Exception as e:
                self.root.after(0, lambda: self.log_message(f"Voice error: {e}", "error"))
            finally:
                self.is_listening = False
                self.root.after(0, lambda: self.voice_btn.config(text="🎤 Start Voice Input", state=tk.NORMAL))
                self.root.after(0, lambda: self.stop_btn.config(state=tk.DISABLED))
                self.root.after(0, lambda: self.voice_status.config(text="Ready"))

        threading.Thread(target=listen, daemon=True).start()

    def stop_voice_input(self):
        """Stop voice input"""
        self.is_listening = False
        self.voice_status.config(text="Stopping...")

    def stop_all(self):
        """Stop all speech operations"""
        self.is_listening = False
        if self.tts_engine:
            try:
                self.tts_engine.stop()
            except:
                pass
        self.is_speaking = False
        self.voice_status.config(text="Stopped")

    def set_text_mode(self):
        """Set to text input mode"""
        self.voice_input_enabled.set(False)
        self.input_entry.focus()
        self.log_message("Switched to text input mode", "system")

    def set_voice_mode(self):
        """Set to voice input mode"""
        if STT_AVAILABLE:
            self.voice_input_enabled.set(True)
            self.log_message("Switched to voice input mode", "system")
        else:
            self.log_message("Voice input not available", "error")

    def show_settings(self):
        """Show settings dialog"""
        settings_window = tk.Toplevel(self.root)
        settings_window.title("Settings")
        settings_window.geometry("400x300")
        settings_window.resizable(False, False)
        settings_window.transient(self.root)
        settings_window.grab_set()

        # Center the window
        settings_window.geometry("+%d+%d" % (
            self.root.winfo_rootx() + 50,
            self.root.winfo_rooty() + 50
        ))

        notebook = ttk.Notebook(settings_window)
        notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Speech settings
        speech_frame = ttk.Frame(notebook)
        notebook.add(speech_frame, text="Speech")

        ttk.Checkbutton(
            speech_frame,
            text="Auto-speak responses",
            variable=self.auto_speak_responses
        ).pack(anchor=tk.W, pady=5)

        # Server settings
        server_frame = ttk.Frame(notebook)
        notebook.add(server_frame, text="Server")

        ttk.Label(server_frame, text="Server URL:").pack(anchor=tk.W, pady=(5, 0))
        server_entry = ttk.Entry(server_frame, width=50)
        server_entry.pack(fill=tk.X, pady=5)
        server_entry.insert(0, self.server_url)

        def save_settings():
            self.server_url = server_entry.get().strip().rstrip('/')
            self.test_connection()
            settings_window.destroy()

        ttk.Button(server_frame, text="Test Connection", command=self.test_connection).pack(pady=5)

        # Buttons
        button_frame = ttk.Frame(settings_window)
        button_frame.pack(fill=tk.X, padx=10, pady=(0, 10))

        ttk.Button(button_frame, text="Save", command=save_settings).pack(side=tk.RIGHT, padx=(5, 0))
        ttk.Button(button_frame, text="Cancel", command=settings_window.destroy).pack(side=tk.RIGHT)

    def show_chat_context_menu(self, event):
        """Show context menu for chat area"""
        try:
            self.chat_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.chat_menu.grab_release()

    def copy_selection(self):
        """Copy selected text from chat"""
        try:
            selection = self.chat_display.selection_get()
            self.root.clipboard_clear()
            self.root.clipboard_append(selection)
        except tk.TclError:
            pass

    def select_all_chat(self):
        """Select all text in chat"""
        self.chat_display.tag_add(tk.SEL, "1.0", tk.END)

    def clear_chat(self):
        """Clear chat history"""
        if messagebox.askyesno("Clear History", "Are you sure you want to clear the conversation history?"):
            self.chat_display.config(state=tk.NORMAL)
            self.chat_display.delete(1.0, tk.END)
            self.chat_display.config(state=tk.DISABLED)
            self.log_message("Chat history cleared", "system")


def main():
    """Main entry point"""
    # Create the main window
    root = tk.Tk()

    # Set icon and styling
    try:
        root.iconbitmap(default='python.ico')  # If you have an icon file
    except:
        pass

    # Create and run the application
    app = VoiceClientGUI(root)

    # Welcome message
    app.log_message("Voice SQL Client started", "system")
    app.log_message("Type your questions or use voice input to query the database", "system")
    app.log_message("Examples: 'How many wells?', 'Show OE12345678', 'Top 5 operators'", "system")

    # Focus on input
    app.input_entry.focus()

    # Start the GUI
    try:
        root.mainloop()
    except KeyboardInterrupt:
        root.quit()


if __name__ == "__main__":
    main()