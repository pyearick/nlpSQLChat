# tkinter_voice_client.py - Enhanced Voice SQL Client

import os
import sys
import json
import requests
import threading
import time
import webbrowser
import re
from typing import Optional
from datetime import datetime
from pathlib import Path

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog

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
    def __init__(self, root, auto_test_connection=True):
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
        self.speech_thread = None
        self.stop_speech_requested = False

        # Speech position tracking for pause/resume
        self.remaining_sentences = None
        self.current_sentence_index = 0
        self.paused_text = None
        self.last_response = ""

        # Settings
        self.auto_speak_responses = tk.BooleanVar(value=True)
        self.voice_input_enabled = tk.BooleanVar(value=True)

        # TTS settings
        self.tts_rate = tk.IntVar(value=165)
        self.tts_volume = tk.DoubleVar(value=0.9)

        self.setup_speech()
        self.create_widgets()

        # Only test connection if not in testing mode
        if auto_test_connection:
            self.test_connection()

    def setup_speech(self):
        """Initialize speech components"""
        # Initialize TTS
        if TTS_AVAILABLE:
            try:
                self.tts_engine = pyttsx3.init()

                # Get available voices
                voices = self.tts_engine.getProperty('voices')
                self.available_voices = {}

                if voices:
                    for voice in voices:
                        self.available_voices[voice.name] = voice.id
                        # Try to use a female voice if available
                        if 'female' in voice.name.lower() or 'zira' in voice.name.lower():
                            self.tts_engine.setProperty('voice', voice.id)

                # Set initial properties
                self.tts_engine.setProperty('rate', self.tts_rate.get())
                self.tts_engine.setProperty('volume', self.tts_volume.get())

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
            self.log_message("Microphone calibrated", "system")
        except Exception as e:
            self.log_message(f"Microphone calibration failed: {e}", "error")

    def create_widgets(self):
        """Create the GUI layout with enhanced speech controls"""
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

        # Input area with enhanced speech controls
        self.create_enhanced_input_area(main_frame)

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

    def create_enhanced_input_area(self, parent):
        """Create the input area with enhanced speech controls"""
        input_frame = ttk.LabelFrame(parent, text="Input", padding="5")
        input_frame.grid(row=2, column=0, sticky=(tk.W, tk.E), pady=(0, 10))
        input_frame.columnconfigure(0, weight=1)

        # Text input with export options
        text_input_frame = ttk.Frame(input_frame)
        text_input_frame.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=(0, 5))
        text_input_frame.columnconfigure(0, weight=1)

        self.input_entry = ttk.Entry(text_input_frame, font=('Consolas', 10))
        self.input_entry.grid(row=0, column=0, sticky=(tk.W, tk.E), padx=(0, 5))
        self.input_entry.bind('<Return>', self.send_message)
        self.input_entry.bind('<Control-Return>', self.send_message)

        # Send button and export options
        send_frame = ttk.Frame(text_input_frame)
        send_frame.grid(row=0, column=1)

        self.send_btn = ttk.Button(send_frame, text="Send", command=self.send_message)
        self.send_btn.grid(row=0, column=0, padx=(0, 2))

        # Export options dropdown
        self.export_var = tk.StringVar(value="Display")
        export_menu = ttk.Combobox(send_frame, textvariable=self.export_var, width=10,
                                   values=["Display", "Export CSV", "Export TXT"], state="readonly")
        export_menu.grid(row=0, column=1)

        # Enhanced voice controls with STOP button
        voice_frame = ttk.Frame(input_frame)
        voice_frame.grid(row=1, column=0, sticky=(tk.W, tk.E))

        self.voice_btn = ttk.Button(voice_frame, text="🎤 Start Voice Input", command=self.toggle_voice_input)
        self.voice_btn.grid(row=0, column=0, padx=(0, 5))

        # STOP/RESUME button
        self.stop_btn = ttk.Button(voice_frame, text="⏹️ STOP", command=self.toggle_speech_pause,
                                   style="Accent.TButton")
        self.stop_btn.grid(row=0, column=1, padx=(0, 5))

        self.speak_btn = ttk.Button(voice_frame, text="🔊 Read Last Response", command=self.speak_last_response)
        self.speak_btn.grid(row=0, column=2, padx=(0, 10))

        # Voice status with more detailed feedback
        self.voice_status = ttk.Label(voice_frame, text="Ready")
        self.voice_status.grid(row=0, column=3, sticky=tk.W)

        # File management buttons
        file_frame = ttk.Frame(input_frame)
        file_frame.grid(row=2, column=0, sticky=(tk.W, tk.E), pady=(5, 0))

        ttk.Button(file_frame, text="📁 Downloads", command=self.show_downloads).grid(row=0, column=0, padx=(0, 5))
        ttk.Button(file_frame, text="📊 Table Sizes", command=self.show_table_sizes).grid(row=0, column=1, padx=(0, 5))

    def create_status_bar(self, parent):
        """Create the status bar"""
        status_frame = ttk.Frame(parent)
        status_frame.grid(row=3, column=0, sticky=(tk.W, tk.E))
        status_frame.columnconfigure(0, weight=1)

        self.status_label = ttk.Label(status_frame, text="Ready")
        self.status_label.grid(row=0, column=0, sticky=tk.W)

    def set_text_mode(self):
        """Switch to text-only mode"""
        self.voice_input_enabled.set(False)
        self.auto_speak_responses.set(False)

        # Update button states
        if STT_AVAILABLE:
            self.voice_btn.config(state=tk.DISABLED)
        if TTS_AVAILABLE:
            self.speak_btn.config(state=tk.DISABLED)

        # Update button styles to show active mode
        self.text_mode_btn.config(style="Accent.TButton")
        self.voice_mode_btn.config(style="TButton")

        self.log_message("📝 Switched to text-only mode", "system")
        self.voice_status.config(text="Text mode")

    def set_voice_mode(self):
        """Switch to voice mode"""
        if not SPEECH_AVAILABLE:
            messagebox.showwarning("Voice Unavailable",
                                   "Speech components are not available on this system.\n\n"
                                   f"Error: {speech_error}")
            return

        self.voice_input_enabled.set(True)
        self.auto_speak_responses.set(True)

        # Update button states
        self.voice_btn.config(state=tk.NORMAL)
        self.speak_btn.config(state=tk.NORMAL)

        # Update button styles to show active mode
        self.voice_mode_btn.config(style="Accent.TButton")
        self.text_mode_btn.config(style="TButton")

        self.log_message("🎤 Switched to voice mode", "system")
        self.voice_status.config(text="Voice mode")

    def show_settings(self):
        """Show settings dialog"""
        settings_window = tk.Toplevel(self.root)
        settings_window.title("Settings")
        settings_window.geometry("450x400")
        settings_window.transient(self.root)
        settings_window.grab_set()

        notebook = ttk.Notebook(settings_window)
        notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Connection tab
        conn_frame = ttk.Frame(notebook)
        notebook.add(conn_frame, text="Connection")

        ttk.Label(conn_frame, text="Server URL:").grid(row=0, column=0, sticky=tk.W, padx=10, pady=5)
        server_var = tk.StringVar(value=self.server_url)
        server_entry = ttk.Entry(conn_frame, textvariable=server_var, width=40)
        server_entry.grid(row=0, column=1, padx=10, pady=5)

        # Test connection button
        def test_new_connection():
            test_url = server_var.get()
            try:
                response = self.session.get(f"{test_url}/health", timeout=5)
                if response.status_code == 200:
                    messagebox.showinfo("Success", "Connection successful!")
                else:
                    messagebox.showerror("Error", f"Connection failed: {response.status_code}")
            except Exception as e:
                messagebox.showerror("Error", f"Connection failed: {e}")

        ttk.Button(conn_frame, text="Test Connection",
                   command=test_new_connection).grid(row=1, column=1, pady=10)

        # Speech tab (only show if TTS available)
        if TTS_AVAILABLE:
            speech_frame = ttk.Frame(notebook)
            notebook.add(speech_frame, text="Speech")

            ttk.Checkbutton(speech_frame, text="Auto-speak responses",
                            variable=self.auto_speak_responses).grid(row=0, column=0, columnspan=2,
                                                                     sticky=tk.W, padx=10, pady=5)

            if STT_AVAILABLE:
                ttk.Checkbutton(speech_frame, text="Enable voice input",
                                variable=self.voice_input_enabled).grid(row=1, column=0, columnspan=2,
                                                                        sticky=tk.W, padx=10, pady=5)

            # Speech Rate
            ttk.Label(speech_frame, text="Speech Rate:").grid(row=3, column=0, sticky=tk.W, padx=10, pady=5)

            rate_frame = ttk.Frame(speech_frame)
            rate_frame.grid(row=3, column=1, sticky=(tk.W, tk.E), padx=10, pady=5)

            rate_scale = ttk.Scale(rate_frame, from_=100, to=300, variable=self.tts_rate,
                                   orient=tk.HORIZONTAL, length=200)
            rate_scale.pack(side=tk.LEFT)

            rate_label = ttk.Label(rate_frame, text=f"{self.tts_rate.get()} wpm")
            rate_label.pack(side=tk.LEFT, padx=(10, 0))

            def update_rate_label(val):
                rate_label.config(text=f"{int(float(val))} wpm")

            rate_scale.config(command=update_rate_label)

            # Test voice button
            def test_voice():
                if self.tts_engine:
                    self.tts_engine.setProperty('rate', self.tts_rate.get())
                    self.tts_engine.setProperty('volume', self.tts_volume.get())

                    test_text = "This is a test of the selected voice settings."
                    self.tts_engine.say(test_text)
                    self.tts_engine.runAndWait()

            ttk.Button(speech_frame, text="Test Voice",
                       command=test_voice).grid(row=5, column=1, pady=20)

        # Button frame
        button_frame = ttk.Frame(settings_window)
        button_frame.pack(fill=tk.X, padx=10, pady=(0, 10))

        # Save button
        def save_settings():
            self.server_url = server_var.get()

            # Apply TTS settings
            if self.tts_engine:
                self.tts_engine.setProperty('rate', self.tts_rate.get())
                self.tts_engine.setProperty('volume', self.tts_volume.get())

            settings_window.destroy()
            self.test_connection()  # Retest with new URL
            self.log_message("⚙️ Settings saved", "system")

        ttk.Button(button_frame, text="Save", command=save_settings).pack(side=tk.RIGHT, padx=(5, 0))
        ttk.Button(button_frame, text="Cancel",
                   command=settings_window.destroy).pack(side=tk.RIGHT)

    def toggle_speech_pause(self):
        """Toggle between pause and resume speech"""
        if self.is_speaking:
            # Currently speaking - pause it
            self.stop_all_speech()
            self.stop_btn.config(text="▶️ RESUME")
        else:
            # Currently paused - resume if we have paused text
            if self.paused_text:
                self.stop_btn.config(text="⏸️ PAUSE")
                self.speak_text(self.paused_text, resume=True)
                self.paused_text = None
            else:
                self.log_message("Nothing to resume", "system")

    def speak_text(self, text, resume=False):
        """Enhanced speak text with interruption and resume support"""
        if not self.tts_engine or (self.is_speaking and not resume):
            return

        def speak_with_interruption():
            try:
                self.is_speaking = True
                self.stop_speech_requested = False

                if not resume:
                    # Fresh start - split all sentences
                    self.remaining_sentences = self.split_into_sentences(text)
                    self.current_sentence_index = 0
                    self.paused_text = text  # Store full text for potential resume

                self.root.after(0, lambda: self.voice_status.config(text="Speaking... (click PAUSE to interrupt)"))
                self.root.after(0, lambda: self.stop_btn.config(state=tk.NORMAL, text="⏸️ PAUSE"))

                start_index = self.current_sentence_index if resume else 0

                for i in range(start_index, len(self.remaining_sentences)):
                    self.current_sentence_index = i

                    # Check if stop was requested
                    if self.stop_speech_requested:
                        # Store remaining text for resume
                        remaining = self.remaining_sentences[i:]
                        self.paused_text = " ".join(remaining)
                        self.root.after(0, lambda: self.voice_status.config(text="Speech paused"))
                        break

                    # Update progress
                    progress = f"Speaking... ({i + 1}/{len(self.remaining_sentences)})"
                    self.root.after(0, lambda p=progress: self.voice_status.config(text=p))

                    # Speak this sentence
                    try:
                        self.tts_engine.say(self.remaining_sentences[i])
                        self.tts_engine.runAndWait()

                        # Brief pause between sentences
                        if not self.stop_speech_requested and i < len(self.remaining_sentences) - 1:
                            time.sleep(0.2)

                    except Exception as e:
                        self.root.after(0, lambda: self.log_message(f"TTS Error: {e}", "error"))
                        break

                if not self.stop_speech_requested:
                    # Completed successfully
                    self.root.after(0, lambda: self.voice_status.config(text="Speech completed"))
                    self.paused_text = None
                    self.remaining_sentences = None
                    self.current_sentence_index = 0

            except Exception as e:
                self.root.after(0, lambda: self.log_message(f"TTS Error: {e}", "error"))
            finally:
                self.is_speaking = False
                if not self.stop_speech_requested:
                    self.stop_speech_requested = False
                    self.root.after(0, lambda: self.voice_status.config(text="Ready"))
                    self.root.after(0, lambda: self.stop_btn.config(text="⏹️ STOP", state=tk.NORMAL))

        # Start speech in a separate thread
        self.speech_thread = threading.Thread(target=speak_with_interruption, daemon=True)
        self.speech_thread.start()

    def split_into_sentences(self, text):
        """Split text into sentences for interruptible speech"""
        # Preprocess text for better speech
        text = self.preprocess_text_for_speech(text)

        # Split on sentence endings
        sentences = re.split(r'(?<=[.!?])\s+', text)

        # Filter out empty sentences
        sentences = [s.strip() for s in sentences if s.strip() and len(s.strip()) > 3]

        # If no clear sentences, split by commas or into chunks
        if len(sentences) <= 1:
            sentences = [chunk.strip() for chunk in text.split(',') if chunk.strip()]

        # If still too long, split into smaller chunks
        final_sentences = []
        for sentence in sentences:
            if len(sentence) > 200:  # Split very long sentences
                words = sentence.split()
                chunk_size = 20  # About 20 words per chunk
                for i in range(0, len(words), chunk_size):
                    chunk = ' '.join(words[i:i + chunk_size])
                    final_sentences.append(chunk)
            else:
                final_sentences.append(sentence)

        return final_sentences if final_sentences else [text]

    def preprocess_text_for_speech(self, text):
        """Add pauses and emphasis for better speech comprehension"""
        # Add pauses after numbers
        text = re.sub(r'(\d+)', r'\1,', text)

        # Add pauses before units
        text = text.replace(' dollars', '... dollars')
        text = text.replace(' percent', '... percent')
        text = text.replace(' records', '... records')
        text = text.replace(' rows', '... rows')

        return text

    def stop_all_speech(self):
        """Stop all speech operations immediately"""
        self.stop_speech_requested = True
        self.is_listening = False

        # Stop TTS engine
        if self.tts_engine:
            try:
                self.tts_engine.stop()
            except:
                pass

        # Force stop speaking flag
        self.is_speaking = False

        # Update UI
        self.voice_status.config(text="Stopped")
        self.voice_btn.config(text="🎤 Start Voice Input", state=tk.NORMAL)

        self.log_message("⏹️ Speech stopped", "system")

    def speak_last_response(self):
        """Speak the last assistant response"""
        if hasattr(self, 'last_response') and self.last_response:
            if self.is_speaking:
                # If already speaking, stop first
                self.stop_all_speech()
                time.sleep(0.1)

            self.paused_text = None  # Clear any paused text
            self.speak_text(self.last_response)
        else:
            self.log_message("No response to speak", "system")

    def update_speech_status(self):
        """Update UI based on speech availability"""
        if not STT_AVAILABLE:
            self.voice_btn.config(state=tk.DISABLED, text="🎤 Voice Unavailable")
            self.voice_mode_btn.config(state=tk.DISABLED)

        if not TTS_AVAILABLE:
            self.speak_btn.config(state=tk.DISABLED, text="🔊 TTS Unavailable")
            self.auto_speak_responses.set(False)

    def log_message(self, message, msg_type="info"):
        """Add a message to the chat display"""
        timestamp = datetime.now().strftime("%H:%M:%S")

        # Configure chat display if not already done
        if not hasattr(self, 'chat_display'):
            return

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
            except Exception:
                self.root.after(0, lambda: self.connection_label.config(text="🔴 Disconnected", foreground="red"))

        threading.Thread(target=test, daemon=True).start()

    def send_message(self, event=None):
        """Send message with proper export handling"""
        message = self.input_entry.get().strip()
        if not message:
            return

        # Stop any current speech
        if self.is_speaking:
            self.stop_all_speech()
            time.sleep(0.1)

        self.input_entry.delete(0, tk.END)
        self.log_message(message, "user")

        # Check for exit
        if message.lower() in ['exit', 'quit', 'goodbye']:
            self.root.quit()
            return

        # Handle export selection
        if self.export_var.get() == "Export CSV":
            message += " Please export the results to CSV format."
            self.log_message("🔄 Requesting CSV export...", "system")
        elif self.export_var.get() == "Export TXT":
            message += " Please export the results to TXT format."
            self.log_message("🔄 Requesting TXT export...", "system")

        # Reset export selection
        self.export_var.set("Display")

        # Send to server
        threading.Thread(target=self.query_server_enhanced, args=(message,), daemon=True).start()

    def query_server_enhanced(self, question, export_format=None):
        """Enhanced query with export handling"""
        try:
            self.root.after(0, lambda: self.status_label.config(text="Processing query..."))

            payload = {"question": question}
            if export_format:
                payload["export_format"] = export_format

            response = self.session.post(
                f"{self.server_url}/ask",
                json=payload,
                headers={"Content-Type": "application/json"}
            )

            if response.status_code == 200:
                data = response.json()
                answer = data.get("answer", "No answer received")

                # Check if this was an export operation
                if self.is_export_response(answer):
                    self.root.after(0, lambda: self.handle_export_response(answer))
                else:
                    self.root.after(0, lambda: self.handle_response(answer))
            else:
                error_msg = f"Server error: {response.status_code} - {response.text}"
                self.root.after(0, lambda: self.log_message(error_msg, "error"))

        except requests.exceptions.ConnectionError:
            self.root.after(0, lambda: self.log_message("Cannot connect to server. Is it running?", "error"))
        except Exception as e:
            self.root.after(0, lambda: self.log_message(f"Error: {e}", "error"))
        finally:
            self.root.after(0, lambda: self.status_label.config(text="Ready"))

    def handle_response(self, response):
        """Handle server response with download detection"""
        self.log_message(response, "assistant")

        # Store for repeat speaking
        self.last_response = response

        # Check if this is an export response that needs download
        if self.is_export_response(response):
            self.handle_export_download(response)

        # Auto-speak if enabled and not already speaking
        elif self.auto_speak_responses.get() and self.tts_engine and not self.is_speaking:
            self.speak_text(response)

    def is_export_response(self, response):
        """Check if response indicates a file export"""
        export_indicators = [
            "Exported" in response and "rows to" in response,
            "File:" in response and "Ready for download" in response,
            "query_export_" in response and (".csv" in response or ".txt" in response)
        ]
        return any(export_indicators)

    def handle_export_download(self, response):
        """Handle export response and offer download"""
        try:
            # Extract filename from various response formats
            filename = self.extract_filename_from_export_response(response)

            if filename:
                self.log_message(f"🔽 File ready for download: {filename}", "system")

                # Offer immediate download
                self.root.after(500, lambda: self.offer_download_dialog(filename))
            else:
                self.log_message("⚠️ Export completed but filename not found", "error")

        except Exception as e:
            self.log_message(f"Error handling export: {e}", "error")

    def extract_filename_from_export_response(self, response):
        """Extract filename from export response"""
        try:
            # Method 1: Look for "File: filename"
            if "File: " in response:
                parts = response.split("File: ")[1].split()[0]
                return parts.strip()

            # Method 2: Look for query_export pattern
            pattern = r'query_export_\d{8}_\d{6}\.(csv|txt)'
            match = re.search(pattern, response)
            if match:
                return match.group(0)

            # Method 3: Extract from full path (old format)
            if "rows to:" in response and "query_export_" in response:
                path_part = response.split("rows to:")[1].strip()
                return os.path.basename(path_part.strip('`'))

        except Exception as e:
            print(f"Error extracting filename: {e}")

        return None

    def offer_download_dialog(self, filename):
        """Show download dialog immediately"""
        result = messagebox.askyesno(
            "Export Complete! 📁",
            f"Your data has been exported successfully!\n\n"
            f"File: {filename}\n\n"
            f"Would you like to download it now?",
            icon='question'
        )

        if result:
            self.download_file_with_save_dialog(filename)
        else:
            self.log_message("💡 Use 'View Downloads' button to download later", "system")

    def download_file_with_save_dialog(self, filename):
        """Download file with save location dialog"""
        try:
            # Determine file type for dialog
            file_extension = os.path.splitext(filename)[1].lower()
            if file_extension == '.csv':
                file_types = [("CSV files", "*.csv"), ("All files", "*.*")]
                default_name = filename.replace('.csv', '_data.csv')
            else:
                file_types = [("Text files", "*.txt"), ("All files", "*.*")]
                default_name = filename.replace('.txt', '_data.txt')

            # Ask user where to save
            save_path = filedialog.asksaveasfilename(
                title="Save exported data as...",
                defaultextension=file_extension,
                filetypes=file_types,
                initialfile=default_name
            )

            if not save_path:
                self.log_message("Download cancelled", "system")
                return

            # Download file
            self.status_label.config(text="Downloading file...")

            def download_worker():
                try:
                    response = self.session.get(f"{self.server_url}/download/{filename}", timeout=120)

                    if response.status_code == 200:
                        # Save to user's location
                        with open(save_path, 'wb') as f:
                            f.write(response.content)

                        # Calculate file size
                        file_size = len(response.content)
                        size_mb = round(file_size / (1024 * 1024), 2)

                        # Success notification
                        self.root.after(0, lambda: self.download_completed(save_path, size_mb))
                    else:
                        error_msg = f"Download failed: {response.status_code} - {response.text}"
                        self.root.after(0, lambda: self.log_message(error_msg, "error"))

                except Exception as e:
                    error_msg = f"Download error: {e}"
                    self.root.after(0, lambda: self.log_message(error_msg, "error"))
                finally:
                    self.root.after(0, lambda: self.status_label.config(text="Ready"))

            # Start download in background
            threading.Thread(target=download_worker, daemon=True).start()

        except Exception as e:
            self.log_message(f"Error starting download: {e}", "error")
            self.status_label.config(text="Ready")

    def download_completed(self, save_path, size_mb):
        """Handle successful download"""
        filename = os.path.basename(save_path)
        self.log_message(f"✅ Downloaded: {filename} ({size_mb} MB)", "system")
        self.log_message(f"📁 Saved to: {save_path}", "system")

        # Offer to open file
        def ask_open():
            if messagebox.askyesno(
                    "Download Complete! 🎉",
                    f"File downloaded successfully!\n\n"
                    f"Saved to: {save_path}\n"
                    f"Size: {size_mb} MB\n\n"
                    f"Open the file now?",
                    icon='info'
            ):
                self.open_downloaded_file(save_path)

        self.root.after(100, ask_open)

    def open_downloaded_file(self, file_path):
        """Open the downloaded file"""
        try:
            if os.name == 'nt':  # Windows
                os.startfile(file_path)
            else:  # Mac/Linux
                import subprocess
                subprocess.run(['open' if sys.platform == 'darwin' else 'xdg-open', file_path])

            self.log_message(f"📂 Opened: {os.path.basename(file_path)}", "system")

        except Exception as e:
            self.log_message(f"Could not open file: {e}", "error")
            # Show location instead
            messagebox.showinfo("File Location", f"File saved to:\n{file_path}")

    def handle_export_response(self, response):
        """Handle export completion response"""
        self.log_message(response, "assistant")

        # Store for speaking
        self.last_response = response

        # Extract filename and offer download
        filename = self.extract_filename_from_export_response(response)
        if filename:
            self.root.after(500, lambda: self.offer_download_dialog(filename))

        # Auto-speak export confirmation if enabled
        if self.auto_speak_responses.get() and self.tts_engine and not self.is_speaking:
            # Shorter version for speaking
            speak_text = "Export completed successfully. Check downloads for the file."
            self.speak_text(speak_text)

    def toggle_voice_input(self):
        """Toggle voice input on/off"""
        if not self.recognizer or not self.microphone:
            self.log_message("❌ Voice input not available - microphone or speech recognition not initialized", "error")
            return

        if self.is_listening:
            # Stop listening
            self.stop_voice_input()
        else:
            # Start listening
            self.start_voice_input()

    def start_voice_input(self):
        """Start voice input"""
        if self.is_listening:
            self.log_message("Voice input already active", "system")
            return

        if not STT_AVAILABLE:
            self.log_message("Speech recognition not available", "error")
            return

        self.is_listening = True
        self.voice_btn.config(text="🎤 Listening...", state=tk.DISABLED)
        self.voice_status.config(text="Listening for speech...")

        # Start voice recognition in a separate thread
        threading.Thread(target=self.voice_recognition_worker, daemon=True).start()

    def stop_voice_input(self):
        """Stop voice input"""
        self.is_listening = False
        self.voice_btn.config(text="🎤 Start Voice Input", state=tk.NORMAL)
        self.voice_status.config(text="Voice input stopped")

    def voice_recognition_worker(self):
        """Voice recognition worker thread"""
        try:
            self.root.after(0, lambda: self.log_message("🎤 Listening... Say your question or 'stop' to end", "system"))

            with self.microphone as source:
                # Listen for audio
                self.root.after(0, lambda: self.voice_status.config(text="Listening for speech..."))

                # Adjust for ambient noise
                self.recognizer.adjust_for_ambient_noise(source, duration=0.5)

                # Listen for speech
                audio = self.recognizer.listen(source, timeout=10, phrase_time_limit=10)

            if not self.is_listening:  # Check if we were stopped
                return

            self.root.after(0, lambda: self.voice_status.config(text="Processing speech..."))

            # Recognize speech
            try:
                text = self.recognizer.recognize_google(audio)
                self.root.after(0, lambda: self.handle_voice_input(text))
            except sr.UnknownValueError:
                self.root.after(0, lambda: self.log_message("Could not understand speech. Please try again.", "system"))
            except sr.RequestError as e:
                self.root.after(0, lambda: self.log_message(f"Speech recognition error: {e}", "error"))

        except sr.WaitTimeoutError:
            self.root.after(0, lambda: self.log_message("No speech detected. Voice input stopped.", "system"))
        except Exception as e:
            self.root.after(0, lambda: self.log_message(f"Voice input error: {e}", "error"))
        finally:
            # Always reset the UI
            self.root.after(0, lambda: self.stop_voice_input())

    def handle_voice_input(self, text):
        """Handle recognized voice input"""
        self.log_message(f"🎤 Heard: {text}", "system")

        # Check for stop command
        if text.lower() in ['stop', 'stop listening', 'quit', 'exit']:
            self.log_message("Voice input stopped by command", "system")
            self.stop_voice_input()
            return

        # Put the recognized text in the input field
        self.input_entry.delete(0, tk.END)
        self.input_entry.insert(0, text)

        # Optionally auto-send the message
        auto_send = messagebox.askyesno("Voice Input", f"Recognized: '{text}'\n\nSend this message?")
        if auto_send:
            self.send_message()

        # Stop voice input after one command
        self.stop_voice_input()

    def show_downloads(self):
        """Show available downloads window"""

        def get_downloads():
            try:
                response = self.session.get(f"{self.server_url}/exports")
                if response.status_code == 200:
                    data = response.json()
                    exports = data.get('exports', [])
                    self.root.after(0, lambda: self.show_downloads_window(exports))
                else:
                    self.root.after(0,
                                    lambda: messagebox.showerror("Error", f"Failed to get downloads: {response.text}"))
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("Error", f"Connection error: {e}"))

        threading.Thread(target=get_downloads, daemon=True).start()

    def show_downloads_window(self, exports):
        """Display available downloads in a window"""
        download_window = tk.Toplevel(self.root)
        download_window.title("Available Downloads")
        download_window.geometry("700x400")
        download_window.transient(self.root)
        download_window.grab_set()

        # Info label
        info_label = ttk.Label(download_window, text=f"Export files available on server ({len(exports)} files):")
        info_label.pack(pady=10)

        # File list frame
        list_frame = ttk.Frame(download_window)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=10)

        # Treeview for file list
        columns = ("filename", "size_mb", "created")
        tree = ttk.Treeview(list_frame, columns=columns, show="headings", height=12)

        tree.heading("filename", text="File Name")
        tree.heading("size_mb", text="Size (MB)")
        tree.heading("created", text="Created")

        tree.column("filename", width=400)
        tree.column("size_mb", width=100)
        tree.column("created", width=150)

        # Scrollbar
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)

        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Populate list
        if exports:
            for export in exports:
                size_mb = export['size_mb']
                created = datetime.fromtimestamp(export['created']).strftime("%Y-%m-%d %H:%M")
                tree.insert(tk.END, values=(export['filename'], size_mb, created))
        else:
            # Show message if no files
            tree.insert(tk.END, values=("No export files found", "", ""))

        # Buttons
        button_frame = ttk.Frame(download_window)
        button_frame.pack(fill=tk.X, padx=10, pady=10)

        def download_selected():
            selection = tree.selection()
            if not selection:
                messagebox.showwarning("No Selection", "Please select a file to download")
                return

            item = tree.item(selection[0])
            filename = item['values'][0]

            if filename == "No export files found":
                return

            download_window.destroy()
            self.download_file_with_save_dialog(filename)

        def delete_selected():
            selection = tree.selection()
            if not selection:
                messagebox.showwarning("No Selection", "Please select a file to delete")
                return

            item = tree.item(selection[0])
            filename = item['values'][0]

            if filename == "No export files found":
                return

            if messagebox.askyesno("Confirm Delete", f"Delete {filename} from server?"):
                try:
                    response = self.session.delete(f"{self.server_url}/exports/{filename}")
                    if response.status_code == 200:
                        self.log_message(f"🗑️ Deleted: {filename}", "system")
                        # Refresh the list
                        download_window.destroy()
                        self.show_downloads()
                    else:
                        messagebox.showerror("Error", f"Failed to delete: {response.text}")
                except Exception as e:
                    messagebox.showerror("Error", f"Delete error: {e}")

        def refresh_list():
            download_window.destroy()
            self.show_downloads()

        ttk.Button(button_frame, text="Download", command=download_selected).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(button_frame, text="Delete", command=delete_selected).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(button_frame, text="Refresh", command=refresh_list).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(button_frame, text="Close", command=download_window.destroy).pack(side=tk.RIGHT)

    def show_table_sizes(self):
        """Show table sizes to help users understand data volumes"""

        def get_sizes():
            tables = ["ebayWT", "ebayWT_NF", "ebayNF_SupplierMatch"]
            sizes = {}

            for table in tables:
                try:
                    response = self.session.post(
                        f"{self.server_url}/ask",
                        json={"question": f"What is the size of table {table}?"}
                    )
                    if response.status_code == 200:
                        data = response.json()
                        sizes[table] = data.get("answer", "Unknown")
                    else:
                        sizes[table] = "Error getting size"
                except:
                    sizes[table] = "Connection error"

            # Display results
            self.root.after(0, lambda: self.show_sizes_window(sizes))

        # Show loading message
        self.log_message("📊 Getting table sizes...", "system")
        threading.Thread(target=get_sizes, daemon=True).start()

    def show_sizes_window(self, sizes):
        """Display table sizes in a window"""
        size_window = tk.Toplevel(self.root)
        size_window.title("Database Table Sizes")
        size_window.geometry("500x400")
        size_window.transient(self.root)
        size_window.grab_set()

        # Create scrollable text widget
        text_frame = ttk.Frame(size_window)
        text_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        text_widget = tk.Text(text_frame, wrap=tk.WORD, padx=10, pady=10, font=('Consolas', 10))
        scrollbar = ttk.Scrollbar(text_frame, orient=tk.VERTICAL, command=text_widget.yview)
        text_widget.configure(yscrollcommand=scrollbar.set)

        text_widget.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Content
        content = "📊 Database Table Sizes\n" + "=" * 40 + "\n\n"

        for table, size_info in sizes.items():
            content += f"🗃️ {table}:\n"
            content += f"   {size_info}\n\n"

        content += "\n💡 Query Tips:\n" + "-" * 20 + "\n"
        content += "• Use 'TOP 100' for large tables\n"
        content += "• Add WHERE conditions to filter data\n"
        content += "• Use 'Export CSV' for large result sets\n"
        content += "• Ask for table sizes before querying\n"
        content += "\n📝 Example Queries:\n" + "-" * 20 + "\n"
        content += "• 'Show me top 10 records from ebayWT'\n"
        content += "• 'Export records where OEAN = PFF5225R'\n"
        content += "• 'How many records in ebayWT_NF'\n"

        text_widget.insert(tk.END, content)
        text_widget.config(state=tk.DISABLED)

        # Close button
        button_frame = ttk.Frame(size_window)
        button_frame.pack(fill=tk.X, padx=10, pady=(0, 10))

        ttk.Button(button_frame, text="Close", command=size_window.destroy).pack(side=tk.RIGHT)
        ttk.Button(button_frame, text="Refresh",
                   command=lambda: [size_window.destroy(), self.show_table_sizes()]).pack(side=tk.RIGHT, padx=(0, 5))


def main():
    """Main entry point"""
    root = tk.Tk()

    app = VoiceClientGUI(root, auto_test_connection=True)  # Enable connection testing in normal mode

    # Welcome message
    app.log_message("Voice SQL Client started", "system")
    app.log_message("🛑 Use the PAUSE/RESUME button to control speech", "system")
    app.log_message("Type your questions or use voice input to query the database", "system")

    # Set initial mode
    if SPEECH_AVAILABLE:
        app.set_voice_mode()
    else:
        app.set_text_mode()
        app.log_message(f"⚠️ Speech components not available: {speech_error}", "system")

    # Focus on input
    app.input_entry.focus()

    try:
        root.mainloop()
    except KeyboardInterrupt:
        root.quit()


if __name__ == "__main__":
    main()