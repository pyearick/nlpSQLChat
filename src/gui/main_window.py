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
from typing import List, Optional

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
        # Add conversational session management
        self.session_id = None  # Will be assigned by server
        self.conversation_active = False
        self.quick_buttons = []
        self.current_suggestions = []

        self.session.timeout = 30

        # Add conversational session management
        self.session_id = None  # Will be assigned by server
        self.conversation_active = False
        self.quick_buttons = []
        self.current_suggestions = []

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
        """Enhanced input area with conversational quick response buttons"""
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

        # Quick response buttons frame (NEW)
        self.quick_response_frame = ttk.LabelFrame(input_frame, text="Quick Responses", padding="5")
        self.quick_response_frame.grid(row=1, column=0, sticky=(tk.W, tk.E), pady=(5, 0))
        self.quick_response_frame.columnconfigure(0, weight=1)

        # Initially hidden
        self.quick_response_frame.grid_remove()

        # Voice controls (moved to row 2)
        voice_frame = ttk.Frame(input_frame)
        voice_frame.grid(row=2, column=0, sticky=(tk.W, tk.E), pady=(5, 0))

        self.voice_btn = ttk.Button(voice_frame, text="🎤 Start Voice Input", command=self.toggle_voice_input)
        self.voice_btn.grid(row=0, column=0, padx=(0, 5))

        # STOP/RESUME button
        self.stop_btn = ttk.Button(voice_frame, text="⏹️ STOP", command=self.toggle_speech_pause,
                                   style="Accent.TButton")
        self.stop_btn.grid(row=0, column=1, padx=(0, 5))

        self.speak_btn = ttk.Button(voice_frame, text="🔊 Read Last Response", command=self.speak_last_response)
        self.speak_btn.grid(row=0, column=2, padx=(0, 10))

        # Conversation controls (NEW)
        conversation_frame = ttk.Frame(voice_frame)
        conversation_frame.grid(row=0, column=3, padx=(10, 5))

        self.reset_conversation_btn = ttk.Button(conversation_frame, text="🔄 New Topic",
                                                 command=self.reset_conversation)
        self.reset_conversation_btn.grid(row=0, column=0, padx=(0, 5))

        # Voice status with more detailed feedback
        self.voice_status = ttk.Label(voice_frame, text="Ready")
        self.voice_status.grid(row=0, column=4, sticky=tk.W)

        # File management buttons (moved to row 3)
        file_frame = ttk.Frame(input_frame)
        file_frame.grid(row=3, column=0, sticky=(tk.W, tk.E), pady=(5, 0))

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
            self.voice_status.config(text="Speech paused")
        else:
            # Currently paused or stopped - check if we have paused text to resume
            if self.paused_text and hasattr(self, 'remaining_sentences') and self.remaining_sentences:
                # Resume from where we left off
                self.stop_btn.config(text="⏸️ PAUSE")
                self.speak_text(self.paused_text, resume=True)
            elif hasattr(self, 'last_response') and self.last_response:
                # No paused text, but we have a last response - restart from beginning
                self.stop_btn.config(text="⏸️ PAUSE")
                self.paused_text = None  # Clear any stale paused text
                self.speak_text(self.last_response)
            else:
                # Nothing to speak
                self.log_message("Nothing to resume or speak", "system")
                self.stop_btn.config(text="⏹️ STOP")

    def speak_text(self, text, resume=False):
        """Enhanced speak text with interruption and resume support"""
        if not self.tts_engine:
            return

        # If already speaking and not resuming, stop first
        if self.is_speaking and not resume:
            self.stop_all_speech()
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
                        self.root.after(0, lambda: self.stop_btn.config(text="▶️ RESUME"))
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
                    self.root.after(0, lambda: self.stop_btn.config(text="⏹️ STOP"))

            except Exception as e:
                self.root.after(0, lambda: self.log_message(f"TTS Error: {e}", "error"))
            finally:
                if not self.stop_speech_requested:
                    self.is_speaking = False
                    self.root.after(0, lambda: self.voice_status.config(text="Ready"))

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
        """Enhanced preprocessing for better speech comprehension"""

        # Handle financial amounts - convert large dollar amounts to millions/thousands
        def format_currency(match):
            amount_str = match.group(1).replace(',', '')
            try:
                amount = float(amount_str)
                if amount >= 1000000:
                    millions = amount / 1000000
                    if millions == int(millions):
                        return f"{int(millions)} million dollars"
                    else:
                        return f"{millions:.1f} million dollars"
                elif amount >= 1000:
                    thousands = amount / 1000
                    if thousands == int(thousands):
                        return f"{int(thousands)} thousand dollars"
                    else:
                        return f"{thousands:.1f} thousand dollars"
                else:
                    dollars = int(amount)
                    cents = int((amount - dollars) * 100)
                    if cents == 0:
                        return f"{dollars} dollars"
                    else:
                        return f"{dollars} dollars and {cents} cents"
            except ValueError:
                return match.group(0)

        # Apply currency formatting
        text = re.sub(r'\$([0-9,]+\.?[0-9]*)', format_currency, text)

        # Handle large numbers (non-currency)
        def format_large_number(match):
            number_str = match.group(0).replace(',', '')
            try:
                number = int(number_str)
                if number >= 1000000:
                    millions = number / 1000000
                    return f"{millions:.1f} million" if millions != int(millions) else f"{int(millions)} million"
                elif number >= 1000:
                    thousands = number / 1000
                    return f"{thousands:.1f} thousand" if thousands != int(thousands) else f"{int(thousands)} thousand"
                else:
                    return str(number)
            except ValueError:
                return match.group(0)

        text = re.sub(r'\b(?<!\$)[0-9]{1,3}(?:,[0-9]{3})+\b', format_large_number, text)

        # Add pauses for better flow
        text = text.replace(' dollars', '... dollars')
        text = text.replace(' percent', '... percent')
        text = text.replace(' records', '... records')
        text = text.replace(' units', '... units')

        return text

    def stop_all_speech(self):
        """Stop all speech operations immediately"""
        self.stop_speech_requested = True
        self.is_listening = False

        # Store current position if we're in the middle of speaking
        if self.is_speaking and hasattr(self, 'remaining_sentences') and hasattr(self, 'current_sentence_index'):
            if self.remaining_sentences and self.current_sentence_index < len(self.remaining_sentences):
                # Store remaining sentences for potential resume
                remaining = self.remaining_sentences[self.current_sentence_index:]
                self.paused_text = " ".join(remaining)

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
        """Enhanced message sending with session management"""
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
        export_format = None
        if self.export_var.get() == "Export CSV":
            export_format = "csv"
            self.log_message("🔄 Requesting CSV export...", "system")
        elif self.export_var.get() == "Export TXT":
            export_format = "txt"
            self.log_message("🔄 Requesting TXT export...", "system")

        # Reset export selection
        self.export_var.set("Display")

        # Send to server with session support
        threading.Thread(target=self.query_server_conversational,
                        args=(message, export_format), daemon=True).start()

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

        def create_enhanced_input_area(self, parent):
            """Enhanced input area with conversational quick response buttons"""
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

            # Quick response buttons frame (NEW)
            self.quick_response_frame = ttk.LabelFrame(input_frame, text="Quick Responses", padding="5")
            self.quick_response_frame.grid(row=1, column=0, sticky=(tk.W, tk.E), pady=(5, 0))
            self.quick_response_frame.columnconfigure(0, weight=1)

            # Initially hidden
            self.quick_response_frame.grid_remove()

            # Voice controls (moved to row 2)
            voice_frame = ttk.Frame(input_frame)
            voice_frame.grid(row=2, column=0, sticky=(tk.W, tk.E), pady=(5, 0))

            self.voice_btn = ttk.Button(voice_frame, text="🎤 Start Voice Input", command=self.toggle_voice_input)
            self.voice_btn.grid(row=0, column=0, padx=(0, 5))

            # STOP/RESUME button
            self.stop_btn = ttk.Button(voice_frame, text="⏹️ STOP", command=self.toggle_speech_pause,
                                       style="Accent.TButton")
            self.stop_btn.grid(row=0, column=1, padx=(0, 5))

            self.speak_btn = ttk.Button(voice_frame, text="🔊 Read Last Response", command=self.speak_last_response)
            self.speak_btn.grid(row=0, column=2, padx=(0, 10))

            # Conversation controls (NEW)
            conversation_frame = ttk.Frame(voice_frame)
            conversation_frame.grid(row=0, column=3, padx=(10, 5))

            self.reset_conversation_btn = ttk.Button(conversation_frame, text="🔄 New Topic",
                                                     command=self.reset_conversation)
            self.reset_conversation_btn.grid(row=0, column=0, padx=(0, 5))

            # Voice status with more detailed feedback
            self.voice_status = ttk.Label(voice_frame, text="Ready")
            self.voice_status.grid(row=0, column=4, sticky=tk.W)

            # File management buttons (moved to row 3)
            file_frame = ttk.Frame(input_frame)
            file_frame.grid(row=3, column=0, sticky=(tk.W, tk.E), pady=(5, 0))

            ttk.Button(file_frame, text="📁 Downloads", command=self.show_downloads).grid(row=0, column=0, padx=(0, 5))
            ttk.Button(file_frame, text="📊 Table Sizes", command=self.show_table_sizes).grid(row=0, column=1,
                                                                                             padx=(0, 5))

        def extract_follow_up_options(self, response: str) -> List[str]:
            """Extract follow-up options from AI response"""
            options = []

            # Look for numbered options
            option_pattern = r'[-\*]\s*\*\*Option\s+\d+\*\*:\s*([^\n]+)'
            matches = re.findall(option_pattern, response, re.IGNORECASE)

            if matches:
                options.extend(matches)
            else:
                # Look for bullet points after "Would you like to:"
                if "would you like to:" in response.lower() or "you might want to:" in response.lower():
                    lines = response.split('\n')
                    in_options = False
                    for line in lines:
                        line = line.strip()
                        if "would you like to:" in line.lower() or "you might want to:" in line.lower():
                            in_options = True
                            continue
                        if in_options and line.startswith('-'):
                            option_text = line[1:].strip()
                            if option_text and len(option_text) > 5:
                                options.append(option_text)
                        elif in_options and not line.startswith('-') and line:
                            break

            return options[:4]  # Limit to 4 options

        def handle_response(self, response):
            """Enhanced response handler with follow-up options"""
            self.log_message(response, "assistant")

            # Store for repeat speaking
            self.last_response = response

            # Extract and create follow-up buttons
            follow_ups = self.extract_follow_up_options(response)

            if follow_ups:
                self.create_quick_response_buttons(follow_ups)
                self.conversation_active = True

                # For voice mode, mention the options
                if self.auto_speak_responses.get() and self.tts_engine and not self.is_speaking:
                    # Speak the main response first
                    self.speak_text(response)

                    # Then mention options are available
                    self.root.after(3000, lambda: self.speak_text(
                        f"I've also prepared {len(follow_ups)} follow-up suggestions. "
                        "You can click the buttons or say 'option 1', 'option 2', etc."
                    ))
            else:
                # No follow-ups, clear any existing buttons
                self.clear_quick_responses()

                # Auto-speak if enabled and not already speaking
                if self.auto_speak_responses.get() and self.tts_engine and not self.is_speaking:
                    self.speak_text(response)

            # Check if this is an export response that needs download
            if self.is_export_response(response):
                self.handle_export_download(response)

        def enhanced_voice_workflow(self):
            """Enhanced voice workflow with conversation awareness"""
            if not self.conversation_active:
                # Start fresh conversation
                self.speak_text("Hello! I'm ready to help you analyze your data. What would you like to explore?")
            else:
                # Continue existing conversation
                if self.current_suggestions:
                    suggestions_text = "You can choose from the available options, or ask something new."
                    self.speak_text(suggestions_text)
                else:
                    self.speak_text("What would you like to explore next?")

        def handle_voice_input(self, text):
            """Enhanced voice input handling with conversation awareness"""
            self.log_message(f"🎤 Heard: {text}", "system")

            # Check for conversation control commands
            text_lower = text.lower().strip()

            if text_lower in ['stop', 'stop listening', 'quit', 'exit']:
                self.log_message("Voice input stopped by command", "system")
                self.stop_voice_input()
                return

            if text_lower in ['new topic', 'reset conversation', 'start over']:
                self.reset_conversation()
                self.stop_voice_input()
                return

            # Check for option selection
            option_match = re.match(r'option\s+(\d+)', text_lower)
            if option_match and self.current_suggestions:
                option_num = int(option_match.group(1))
                if 1 <= option_num <= len(self.current_suggestions):
                    self.send_follow_up(self.current_suggestions[option_num - 1], option_num)
                    self.stop_voice_input()
                    return

            # Put the recognized text in the input field
            self.input_entry.delete(0, tk.END)
            self.input_entry.insert(0, text)

            # For conversational flow, auto-send recognized speech
            if self.conversation_active:
                self.send_message()
            else:
                # Ask for confirmation for new conversations
                auto_send = messagebox.askyesno("Voice Input", f"Recognized: '{text}'\n\nSend this message?")
                if auto_send:
                    self.send_message()

            # Stop voice input after processing
            self.stop_voice_input()

        def show_conversation_help(self):
            """Show help dialog for conversational features"""
            help_window = tk.Toplevel(self.root)
            help_window.title("Conversational Features Help")
            help_window.geometry("600x500")
            help_window.transient(self.root)
            help_window.grab_set()

            # Create scrollable text widget
            text_frame = ttk.Frame(help_window)
            text_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

            text_widget = tk.Text(text_frame, wrap=tk.WORD, padx=10, pady=10, font=('Consolas', 10))
            scrollbar = ttk.Scrollbar(text_frame, orient=tk.VERTICAL, command=text_widget.yview)
            text_widget.configure(yscrollcommand=scrollbar.set)

            text_widget.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

            # Help content
            help_content = """🤖 Conversational Voice SQL Client Help

    CONVERSATIONAL FEATURES:
    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    🔄 Follow-up Suggestions:
    After each query, the AI will suggest relevant follow-up questions.
    Click the numbered buttons or say "option 1", "option 2", etc.

    💬 Natural Language:
    You can use pronouns and references:
    • "Show me Customer A's sales" → "How do they compare to others?"
    • "Check inventory for PFF5225R" → "What about that part's competitors?"

    🎤 Voice Commands:
    • "Option 1" / "Option 2" - Select follow-up suggestions
    • "New topic" - Reset conversation and start fresh
    • "Stop" - End voice input

    📊 Smart Context:
    The AI remembers:
    • Previous customers, parts, and dates mentioned
    • Query types (sales, inventory, competitor analysis)
    • Results from recent queries

    EXAMPLE CONVERSATION FLOW:
    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    You: "How many records are in ebayWT?"
    AI: "Found 2.1 million records. Would you like to:
         - See sample records to understand the data
         - Check the most recent activity
         - Compare to other tables?"

    You: "Option 1" (or click the button)
    AI: Shows sample data and offers more specific follow-ups

    You: "What about CustomerA's purchases?"
    AI: (Understands context) Shows CustomerA data with relevant suggestions

    QUICK TIPS:
    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    ✅ Let the AI guide you through data exploration
    ✅ Use the suggestion buttons for faster navigation  
    ✅ Mix voice and text input as preferred
    ✅ Say "new topic" to change subjects
    ✅ Export data when you find interesting insights

    The AI learns your interests and suggests increasingly relevant follow-ups!
    """

            text_widget.insert(tk.END, help_content)
            text_widget.config(state=tk.DISABLED)

            # Close button
            button_frame = ttk.Frame(help_window)
            button_frame.pack(fill=tk.X, padx=10, pady=(0, 10))

            ttk.Button(button_frame, text="Close", command=help_window.destroy).pack(side=tk.RIGHT)

    def query_server_conversational(self, question, export_format=None):
        """Enhanced query with conversational session management"""
        try:
            self.root.after(0, lambda: self.status_label.config(text="Processing query..."))

            # Prepare payload with session ID
            payload = {
                "question": question,
                "session_id": self.session_id
            }

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

                # Update session ID if provided
                if "session_id" in data:
                    self.session_id = data["session_id"]

                # Get follow-up suggestions if available
                suggestions = data.get("suggestions", [])

                # Handle the response with suggestions
                self.root.after(0, lambda: self.handle_conversational_response(answer, suggestions))

            else:
                error_msg = f"Server error: {response.status_code} - {response.text}"
                self.root.after(0, lambda: self.log_message(error_msg, "error"))

        except requests.exceptions.ConnectionError:
            self.root.after(0, lambda: self.log_message("Cannot connect to server. Is it running?", "error"))
        except Exception as e:
            self.root.after(0, lambda: self.log_message(f"Error: {e}", "error"))
        finally:
            self.root.after(0, lambda: self.status_label.config(text="Ready"))

    def handle_conversational_response(self, response: str, suggestions: List[str] = None):
        """Handle response with conversational features"""
        # Log the main response
        self.log_message(response, "assistant")

        # Store for repeat speaking
        self.last_response = response

        # Handle follow-up suggestions
        if suggestions:
            self.create_quick_response_buttons(suggestions)
            self.conversation_active = True

            # For voice mode, speak response and mention suggestions
            if self.auto_speak_responses.get() and self.tts_engine and not self.is_speaking:
                # Extract main answer without suggestions for speech
                main_answer = self.extract_main_answer(response)
                self.speak_text(main_answer)

                # Mention suggestions after a pause
                self.root.after(3000, lambda: self.speak_suggestions_available(len(suggestions)))
        else:
            # No suggestions, clear any existing ones
            self.clear_quick_responses()

            # Normal speech handling
            if self.auto_speak_responses.get() and self.tts_engine and not self.is_speaking:
                self.speak_text(response)

        # Check for export handling
        if self.is_export_response(response):
            self.handle_export_download(response)

    def extract_main_answer(self, response: str) -> str:
        """Extract the main answer, removing follow-up suggestions for cleaner speech"""
        lines = response.split('\n')
        main_lines = []

        for line in lines:
            line = line.strip()
            # Stop at follow-up indicators
            if any(indicator in line.lower() for indicator in [
                'would you like to:', 'you might want to:', 'building on this',
                'option 1:', 'option 2:', 'just say', 'based on this data'
            ]):
                break
            if line:
                main_lines.append(line)

        return '\n'.join(main_lines)

    def speak_suggestions_available(self, count: int):
        """Announce that follow-up suggestions are available"""
        if not self.is_speaking:  # Only if not already speaking
            suggestion_text = f"I've prepared {count} follow-up suggestions. "
            suggestion_text += "You can click the numbered buttons or say 'option 1', 'option 2', and so on."
            self.speak_text(suggestion_text)

    def reset_conversation(self):
        """Reset conversation context on both client and server"""
        # Clear local conversation state
        self.clear_quick_responses()
        self.conversation_active = False

        # Reset server session
        def reset_server_session():
            try:
                payload = {}
                if self.session_id:
                    payload["session_id"] = self.session_id

                response = self.session.post(
                    f"{self.server_url}/reset_conversation",
                    json=payload,
                    timeout=5
                )

                if response.status_code == 200:
                    data = response.json()
                    self.session_id = data.get("session_id")
                    self.root.after(0, lambda: self.log_message("🔄 Started new conversation topic", "system"))
                else:
                    self.root.after(0, lambda: self.log_message("🔄 Reset locally (server reset failed)", "system"))

            except Exception as e:
                self.root.after(0, lambda: self.log_message(f"🔄 Reset locally (server error: {e})", "system"))

        threading.Thread(target=reset_server_session, daemon=True).start()

        # Update UI state
        self.voice_status.config(text="Ready for new topic")

    def create_toolbar(self, parent):
        """Enhanced toolbar with conversation help"""
        toolbar = ttk.Frame(parent)
        toolbar.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=(0, 10))
        toolbar.columnconfigure(4, weight=1)

        # Mode buttons
        self.text_mode_btn = ttk.Button(toolbar, text="📝 Text Mode", command=self.set_text_mode)
        self.text_mode_btn.grid(row=0, column=0, padx=(0, 5))

        self.voice_mode_btn = ttk.Button(toolbar, text="🎤 Voice Mode", command=self.set_voice_mode)
        self.voice_mode_btn.grid(row=0, column=1, padx=(0, 5))

        # Settings button
        ttk.Button(toolbar, text="⚙️ Settings", command=self.show_settings).grid(row=0, column=2, padx=(0, 5))

        # NEW: Conversation help button
        ttk.Button(toolbar, text="❓ Help", command=self.show_conversation_help).grid(row=0, column=3, padx=(0, 10))

        # Connection status
        self.connection_label = ttk.Label(toolbar, text="🔴 Disconnected")
        self.connection_label.grid(row=0, column=5, sticky=tk.E)

    def handle_voice_input(self, text):
        """Enhanced voice input with conversational awareness"""
        self.log_message(f"🎤 Heard: {text}", "system")

        # Check for conversation control commands
        text_lower = text.lower().strip()

        if text_lower in ['stop', 'stop listening', 'quit', 'exit']:
            self.log_message("Voice input stopped by command", "system")
            self.stop_voice_input()
            return

        if text_lower in ['new topic', 'reset conversation', 'start over', 'new conversation']:
            self.reset_conversation()
            self.stop_voice_input()
            return

        # Check for option selection when suggestions are available
        # Check for option selection when suggestions are available
        if self.current_suggestions:
            option_patterns = [
                r'^option\s+(\d+)$',
                r'^(\d+)$',
                r'^number\s+(\d+)$',
                r'^choice\s+(\d+)$'
            ]

            for pattern in option_patterns:
                match = re.match(pattern, text_lower)
                if match:
                    option_num = int(match.group(1))
                    if 1 <= option_num <= len(self.current_suggestions):
                        self.send_follow_up(self.current_suggestions[option_num - 1], option_num)
                        self.stop_voice_input()
                        return

        # Handle affirmative responses to suggestions
        if text_lower in ['yes', 'sure', 'okay', 'ok', 'first one', 'first option'] and self.current_suggestions:
            self.send_follow_up(self.current_suggestions[0], 1)
            self.stop_voice_input()
            return

        # Put the recognized text in the input field
        self.input_entry.delete(0, tk.END)
        self.input_entry.insert(0, text)

        # For active conversations, auto-send to maintain flow
        if self.conversation_active:
            self.send_message()
            self.stop_voice_input()
        else:
            # For new conversations, ask for confirmation
            auto_send = messagebox.askyesno(
                "Voice Input",
                f"Recognized: '{text}'\n\nSend this message?",
                parent=self.root
            )
            if auto_send:
                self.send_message()
            self.stop_voice_input()

    def enhanced_voice_interaction(self):
        """Start enhanced voice interaction with conversational awareness"""
        if not STT_AVAILABLE:
            self.log_message("❌ Voice input not available", "error")
            return

        if not self.conversation_active:
            # Start new conversation
            welcome_msg = "Hello! I'm ready to help you explore your data. What would you like to analyze?"
            self.log_message(welcome_msg, "system")

            if self.auto_speak_responses.get():
                self.speak_text(welcome_msg)
        else:
            # Continue conversation
            if self.current_suggestions:
                continue_msg = "You can choose from the available options by saying 'option 1', 'option 2', etc., or ask something new."
            else:
                continue_msg = "What would you like to explore next?"

            self.log_message(continue_msg, "system")

            if self.auto_speak_responses.get():
                self.speak_text(continue_msg)

    def show_conversation_debug(self):
        """Show conversation state for debugging (dev feature)"""
        if not self.session_id:
            messagebox.showinfo("Debug", "No active conversation session")
            return

        def get_debug_info():
            try:
                response = self.session.get(f"{self.server_url}/conversation_state/{self.session_id}")
                if response.status_code == 200:
                    data = response.json()
                    self.root.after(0, lambda: self.show_debug_window(data))
                else:
                    self.root.after(0, lambda: messagebox.showerror("Error", "Failed to get conversation state"))
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("Error", f"Debug error: {e}"))

        threading.Thread(target=get_debug_info, daemon=True).start()

    def show_debug_window(self, debug_data):
        """Display conversation debug information"""
        debug_window = tk.Toplevel(self.root)
        debug_window.title("Conversation Debug Info")
        debug_window.geometry("600x400")
        debug_window.transient(self.root)

        # Create text widget with scrollbar
        text_frame = ttk.Frame(debug_window)
        text_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        text_widget = tk.Text(text_frame, wrap=tk.WORD, font=('Consolas', 9))
        scrollbar = ttk.Scrollbar(text_frame, orient=tk.VERTICAL, command=text_widget.yview)
        text_widget.configure(yscrollcommand=scrollbar.set)

        text_widget.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Format debug information
        import json
        debug_text = json.dumps(debug_data, indent=2, default=str)
        text_widget.insert(tk.END, debug_text)
        text_widget.config(state=tk.DISABLED)

        # Close button
        ttk.Button(debug_window, text="Close", command=debug_window.destroy).pack(pady=5)

    def create_conversation_status_bar(self, parent):
        """Create status bar with conversation indicators"""
        status_frame = ttk.Frame(parent)
        status_frame.grid(row=3, column=0, sticky=(tk.W, tk.E))
        status_frame.columnconfigure(1, weight=1)

        # Main status
        self.status_label = ttk.Label(status_frame, text="Ready")
        self.status_label.grid(row=0, column=0, sticky=tk.W)

        # Conversation status
        self.conversation_status = ttk.Label(status_frame, text="", foreground="blue")
        self.conversation_status.grid(row=0, column=1, sticky=tk.W, padx=(20, 0))

        # Session ID (for debugging)
        self.session_label = ttk.Label(status_frame, text="", foreground="gray", font=('Consolas', 8))
        self.session_label.grid(row=0, column=2, sticky=tk.E)

    def update_conversation_status(self):
        """Update conversation status indicators"""
        if self.conversation_active:
            if self.current_suggestions:
                status_text = f"💬 Conversation active ({len(self.current_suggestions)} suggestions)"
            else:
                status_text = "💬 Conversation active"
            self.conversation_status.config(text=status_text)
        else:
            self.conversation_status.config(text="")

        # Show session ID if available
        if self.session_id:
            session_text = f"Session: {self.session_id[:8]}..."
            self.session_label.config(text=session_text)
        else:
            self.session_label.config(text="")

    def send_follow_up(self, option_text: str, option_number: int):
        """Enhanced follow-up sending with better feedback"""
        # Log the selection with context
        self.log_message(f"💡 Selected Option {option_number}: {option_text}", "user")

        # For voice users, provide audio feedback
        if self.auto_speak_responses.get() and self.tts_engine:
            feedback = f"Option {option_number} selected."
            threading.Thread(target=lambda: self.tts_engine.say(feedback) or self.tts_engine.runAndWait(),
                             daemon=True).start()

        # Clear input and set the follow-up text (server will understand this)
        self.input_entry.delete(0, tk.END)
        self.input_entry.insert(0, f"Option {option_number}")

        # Send the message
        self.send_message()

        # Clear quick response buttons
        self.clear_quick_responses()

        # Update status
        self.update_conversation_status()

    def create_quick_response_buttons(self, options: List[str]):
        """Enhanced quick response button creation"""
        # Clear existing buttons
        for btn in self.quick_buttons:
            btn.destroy()
        self.quick_buttons.clear()

        if not options:
            self.quick_response_frame.grid_remove()
            return

        # Show the frame
        self.quick_response_frame.grid()

        # Create container with better layout
        button_container = ttk.Frame(self.quick_response_frame)
        button_container.grid(row=0, column=0, sticky=(tk.W, tk.E), padx=5, pady=5)

        # Create buttons with enhanced styling
        for i, option in enumerate(options):
            # Create more readable button text
            button_text = self.format_button_text(option, i + 1)

            btn = ttk.Button(
                button_container,
                text=button_text,
                command=lambda opt=option, num=i + 1: self.send_follow_up(opt, num),
                width=30  # Consistent width
            )

            # Arrange in 2 columns
            row = i // 2
            col = i % 2
            btn.grid(row=row, column=col, padx=3, pady=2, sticky=(tk.W, tk.E))
            self.quick_buttons.append(btn)

        # Configure column weights for better layout
        button_container.columnconfigure(0, weight=1)
        button_container.columnconfigure(1, weight=1)

        # Store current suggestions
        self.current_suggestions = options

        # Update status
        self.update_conversation_status()

        # Add keyboard shortcuts hint
        hint_label = ttk.Label(
            self.quick_response_frame,
            text="💡 Tip: Say 'option 1', 'option 2', etc. or use the buttons",
            font=('Arial', 8),
            foreground="gray"
        )
        hint_label.grid(row=1, column=0, pady=(5, 0))

    def format_button_text(self, option: str, number: int) -> str:
        """Format option text for button display"""
        # Remove any existing numbering
        clean_option = re.sub(r'^\d+[\.\)]\s*', '', option.strip())

        # Truncate long options intelligently
        if len(clean_option) > 45:
            # Try to break at word boundaries
            words = clean_option.split()
            truncated = ""
            for word in words:
                if len(truncated + word) < 42:
                    truncated += word + " "
                else:
                    break
            clean_option = truncated.strip() + "..."

        return f"{number}. {clean_option}"

    def clear_quick_responses(self):
        """Enhanced clearing of quick response elements"""
        for btn in self.quick_buttons:
            btn.destroy()
        self.quick_buttons.clear()
        self.current_suggestions.clear()
        self.quick_response_frame.grid_remove()

        # Update status
        self.update_conversation_status()



    def reset_conversation(self):
        """Reset conversation context on both client and server"""
        # Clear local conversation state
        self.clear_quick_responses()
        self.conversation_active = False

        # Reset server session
        def reset_server_session():
            try:
                payload = {}
                if self.session_id:
                    payload["session_id"] = self.session_id

                response = self.session.post(
                    f"{self.server_url}/reset_conversation",
                    json=payload,
                    timeout=5
                )

                if response.status_code == 200:
                    data = response.json()
                    self.session_id = data.get("session_id")
                    self.root.after(0, lambda: self.log_message("🔄 Started new conversation topic", "system"))
                else:
                    self.root.after(0, lambda: self.log_message("🔄 Reset locally (server reset failed)", "system"))

            except Exception as e:
                self.root.after(0, lambda: self.log_message(f"🔄 Reset locally (server error: {e})", "system"))

        threading.Thread(target=reset_server_session, daemon=True).start()

        # Update UI state
        self.voice_status.config(text="Ready for new topic")

    def show_conversation_help(self):
        """Show help dialog for conversational features"""
        help_window = tk.Toplevel(self.root)
        help_window.title("Conversational Features Help")
        help_window.geometry("600x500")
        help_window.transient(self.root)
        help_window.grab_set()

        # Create scrollable text widget
        text_frame = ttk.Frame(help_window)
        text_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        text_widget = tk.Text(text_frame, wrap=tk.WORD, padx=10, pady=10, font=('Consolas', 10))
        scrollbar = ttk.Scrollbar(text_frame, orient=tk.VERTICAL, command=text_widget.yview)
        text_widget.configure(yscrollcommand=scrollbar.set)

        text_widget.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Help content
        help_content = """🤖 Conversational Voice SQL Client Help

CONVERSATIONAL FEATURES:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🔄 Follow-up Suggestions:
After each query, the AI will suggest relevant follow-up questions.
Click the numbered buttons or say "option 1", "option 2", etc.

💬 Natural Language:
You can use pronouns and references:
• "Show me Customer A's sales" → "How do they compare to others?"
• "Check inventory for PFF5225R" → "What about that part's competitors?"

🎤 Voice Commands:
• "Option 1" / "Option 2" - Select follow-up suggestions
• "New topic" - Reset conversation and start fresh
• "Stop" - End voice input

📊 Smart Context:
The AI remembers:
• Previous customers, parts, and dates mentioned
• Query types (sales, inventory, competitor analysis)
• Results from recent queries

EXAMPLE CONVERSATION FLOW:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

You: "How many records are in ebayWT?"
AI: "Found 2.1 million records. Would you like to:
     - See sample records to understand the data
     - Check the most recent activity
     - Compare to other tables?"

You: "Option 1" (or click the button)
AI: Shows sample data and offers more specific follow-ups

You: "What about CustomerA's purchases?"
AI: (Understands context) Shows CustomerA data with relevant suggestions

QUICK TIPS:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

✅ Let the AI guide you through data exploration
✅ Use the suggestion buttons for faster navigation  
✅ Mix voice and text input as preferred
✅ Say "new topic" to change subjects
✅ Export data when you find interesting insights

The AI learns your interests and suggests increasingly relevant follow-ups!
"""

        text_widget.insert(tk.END, help_content)
        text_widget.config(state=tk.DISABLED)

        # Close button
        button_frame = ttk.Frame(help_window)
        button_frame.pack(fill=tk.X, padx=10, pady=(0, 10))

        ttk.Button(button_frame, text="Close", command=help_window.destroy).pack(side=tk.RIGHT)

    def clear_quick_responses(self):
        """Enhanced clearing of quick response elements"""
        for btn in self.quick_buttons:
            btn.destroy()
        self.quick_buttons.clear()
        self.current_suggestions.clear()
        self.quick_response_frame.grid_remove()

        # Update status
        self.update_conversation_status()

    def update_conversation_status(self):
        """Update conversation status indicators"""
        if self.conversation_active:
            if self.current_suggestions:
                status_text = f"💬 Conversation active ({len(self.current_suggestions)} suggestions)"
            else:
                status_text = "💬 Conversation active"
            if hasattr(self, 'conversation_status'):
                self.conversation_status.config(text=status_text)
        else:
            if hasattr(self, 'conversation_status'):
                self.conversation_status.config(text="")

        # Show session ID if available
        if hasattr(self, 'session_label') and hasattr(self, 'session_id') and self.session_id:
            session_text = f"Session: {self.session_id[:8]}..."
            self.session_label.config(text=session_text)
        elif hasattr(self, 'session_label'):
            self.session_label.config(text="")

    def create_quick_response_buttons(self, options):
        """Enhanced quick response button creation"""
        # Clear existing buttons
        for btn in self.quick_buttons:
            btn.destroy()
        self.quick_buttons.clear()

        if not options:
            self.quick_response_frame.grid_remove()
            return

        # Show the frame
        self.quick_response_frame.grid()

        # Create container with better layout
        button_container = ttk.Frame(self.quick_response_frame)
        button_container.grid(row=0, column=0, sticky=(tk.W, tk.E), padx=5, pady=5)

        # Create buttons with enhanced styling
        for i, option in enumerate(options):
            # Create more readable button text
            button_text = self.format_button_text(option, i + 1)

            btn = ttk.Button(
                button_container,
                text=button_text,
                command=lambda opt=option, num=i + 1: self.send_follow_up(opt, num),
                width=30  # Consistent width
            )

            # Arrange in 2 columns
            row = i // 2
            col = i % 2
            btn.grid(row=row, column=col, padx=3, pady=2, sticky=(tk.W, tk.E))
            self.quick_buttons.append(btn)

        # Configure column weights for better layout
        button_container.columnconfigure(0, weight=1)
        button_container.columnconfigure(1, weight=1)

        # Store current suggestions
        self.current_suggestions = options

        # Update status
        self.update_conversation_status()

        # Add keyboard shortcuts hint
        hint_label = ttk.Label(
            self.quick_response_frame,
            text="💡 Tip: Say 'option 1', 'option 2', etc. or use the buttons",
            font=('Arial', 8),
            foreground="gray"
        )
        hint_label.grid(row=1, column=0, pady=(5, 0))

    def format_button_text(self, option: str, number: int) -> str:
        """Format option text for button display"""
        # Remove any existing numbering
        clean_option = re.sub(r'^\d+[\.\)]\s*', '', option.strip())

        # Truncate long options intelligently
        if len(clean_option) > 45:
            # Try to break at word boundaries
            words = clean_option.split()
            truncated = ""
            for word in words:
                if len(truncated + word) < 42:
                    truncated += word + " "
                else:
                    break
            clean_option = truncated.strip() + "..."

        return f"{number}. {clean_option}"

    def send_follow_up(self, option_text: str, option_number: int):
        """Enhanced follow-up sending with better feedback"""
        # Log the selection with context
        self.log_message(f"💡 Selected Option {option_number}: {option_text}", "user")

        # For voice users, provide audio feedback
        if self.auto_speak_responses.get() and self.tts_engine:
            feedback = f"Option {option_number} selected."
            threading.Thread(target=lambda: self.tts_engine.say(feedback) or self.tts_engine.runAndWait(),
                            daemon=True).start()

        # Clear input and set the follow-up text (server will understand this)
        self.input_entry.delete(0, tk.END)
        self.input_entry.insert(0, f"Option {option_number}")

        # Send the message
        self.send_message()

        # Clear quick response buttons
        self.clear_quick_responses()

        # Update status
        self.update_conversation_status()

    def query_server_conversational(self, question, export_format=None):
        """Enhanced query with conversational session management"""
        try:
            self.root.after(0, lambda: self.status_label.config(text="Processing query..."))

            # Prepare payload with session ID
            payload = {
                "question": question,
                "session_id": getattr(self, 'session_id', None)
            }

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

                # Update session ID if provided
                if "session_id" in data:
                    self.session_id = data["session_id"]

                # Get follow-up suggestions if available
                suggestions = data.get("suggestions", [])

                # Handle the response with suggestions
                self.root.after(0, lambda: self.handle_conversational_response(answer, suggestions))

            else:
                error_msg = f"Server error: {response.status_code} - {response.text}"
                self.root.after(0, lambda: self.log_message(error_msg, "error"))

        except requests.exceptions.ConnectionError:
            self.root.after(0, lambda: self.log_message("Cannot connect to server. Is it running?", "error"))
        except Exception as e:
            self.root.after(0, lambda: self.log_message(f"Error: {e}", "error"))
        finally:
            self.root.after(0, lambda: self.status_label.config(text="Ready"))

    def handle_conversational_response(self, response: str, suggestions=None):
        """Handle response with conversational features"""
        # Log the main response
        self.log_message(response, "assistant")

        # Store for repeat speaking
        self.last_response = response

        # Handle follow-up suggestions
        if suggestions:
            self.create_quick_response_buttons(suggestions)
            self.conversation_active = True

            # For voice mode, speak response and mention suggestions
            if self.auto_speak_responses.get() and self.tts_engine and not self.is_speaking:
                # Extract main answer without suggestions for speech
                main_answer = self.extract_main_answer(response)
                self.speak_text(main_answer)

                # Mention suggestions after a pause
                self.root.after(3000, lambda: self.speak_suggestions_available(len(suggestions)))
        else:
            # No suggestions, clear any existing ones
            self.clear_quick_responses()

            # Normal speech handling
            if self.auto_speak_responses.get() and self.tts_engine and not self.is_speaking:
                self.speak_text(response)

        # Check for export handling
        if self.is_export_response(response):
            self.handle_export_download(response)

    def extract_main_answer(self, response: str) -> str:
        """Extract the main answer, removing follow-up suggestions for cleaner speech"""
        lines = response.split('\n')
        main_lines = []

        for line in lines:
            line = line.strip()
            # Stop at follow-up indicators
            if any(indicator in line.lower() for indicator in [
                'would you like to:', 'you might want to:', 'building on this',
                'option 1:', 'option 2:', 'just say', 'based on this data'
            ]):
                break
            if line:
                main_lines.append(line)

        return '\n'.join(main_lines)

    def speak_suggestions_available(self, count: int):
        """Announce that follow-up suggestions are available"""
        if not self.is_speaking:  # Only if not already speaking
            suggestion_text = f"I've prepared {count} follow-up suggestions. "
            suggestion_text += "You can click the numbered buttons or say 'option 1', 'option 2', and so on."
            self.speak_text(suggestion_text)


def main():
    """Enhanced main entry point with conversation features"""
    root = tk.Tk()

    app = VoiceClientGUI(root, auto_test_connection=True)

    # Enhanced welcome messages
    app.log_message("🤖 Voice SQL Client with Conversational AI started", "system")
    app.log_message("💡 New: I can now have multi-turn conversations and suggest follow-ups!", "system")
    app.log_message("🛑 Use PAUSE/RESUME to control speech, 'New Topic' to reset conversations", "system")

    if SPEECH_AVAILABLE:
        app.log_message("🎤 Voice commands: 'option 1/2/3', 'new topic', 'stop'", "system")

    # Set initial mode
    if SPEECH_AVAILABLE:
        app.set_voice_mode()
        app.log_message("🎤 Voice mode active - I'll guide you through data exploration", "system")
    else:
        app.set_text_mode()
        app.log_message(f"⚠️ Speech components not available: {speech_error}", "system")
        app.log_message("📝 Text mode active - Use the suggestion buttons for quick follow-ups", "system")

    # Focus on input
    app.input_entry.focus()

    try:
        root.mainloop()
    except KeyboardInterrupt:
        root.quit()


if __name__ == "__main__":
    main()