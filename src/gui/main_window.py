# main_window.py - Modularized and refactored for streamlined voice/text workflow

import os
import sys
import json
import requests
import threading
import time
import webbrowser
import re
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional, List
from datetime import datetime
from pathlib import Path

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog

# ----- Speech Capability Detection -----
TTS_AVAILABLE = False
STT_AVAILABLE = False
SPEECH_ERROR = None

try:
    import pyttsx3
    TTS_AVAILABLE = True
except ImportError as e:
    SPEECH_ERROR = f"pyttsx3 not available: {e}"

try:
    import speech_recognition as sr
    import pyaudio
    STT_AVAILABLE = True
except ImportError as e:
    if SPEECH_ERROR:
        SPEECH_ERROR += f" | speech_recognition/pyaudio not available: {e}"
    else:
        SPEECH_ERROR = f"speech_recognition/pyaudio not available: {e}"

SPEECH_AVAILABLE = TTS_AVAILABLE and STT_AVAILABLE

# -------- Main GUI Class --------
class VoiceClientGUI:
    def __init__(self, root, auto_test_connection=True):
        self.root = root
        self.root.title("Voice SQL Client")
        self.root.geometry("800x600")
        self.root.minsize(600, 400)
        # --- Config ---
        self.server_url = os.getenv("VOICE_SQL_SERVER", "http://BI-SQL001:8000").rstrip('/')
        self.session = requests.Session()
        self.session.timeout = 60
        self.session_id = None
        self.conversation_active = False
        self.current_suggestions = []

        # --- ADD THESE NEW VARIABLES FOR FEEDBACK TRACKING ---
        self.last_query_sql = None
        self.last_query_question = None
        self.last_query_response = None
        self.last_query_timestamp = None

        # Email configuration for feedback notifications
        self.feedback_email_config = {
            'smtp_server': os.getenv('RELAY_IP', 'localhost'),
            'smtp_port': int(os.getenv('SMTP_PORT', '25')),
            'from_address': os.getenv('MONITOR_FROM_EMAIL', 'pyearick@crpindustries.com'),
            'to_addresses': os.getenv('FEEDBACK_TO_EMAILS', '').split(','),
        }

        # --- Speech flags ---
        self.speech_capable = SPEECH_AVAILABLE
        self.tts_engine = None
        self.recognizer = None
        self.microphone = None
        self.is_listening = False
        self.is_speaking = False
        self.speech_thread = None
        self.stop_speech_requested = False

        # --- GUI State ---
        self.last_response = ""
        self.paused_text = None
        self.remaining_sentences = None
        self.current_sentence_index = 0

        # --- UI variables ---
        self.auto_speak_responses = tk.BooleanVar(value=self.speech_capable)
        self.voice_input_enabled = tk.BooleanVar(value=self.speech_capable)
        self.tts_engine_valid = True

        # --- Setup ---
        self.create_widgets()
        self.setup_speech()
        if auto_test_connection:
            self.test_connection()

    # ... Next segment: setup_speech, calibrate_microphone, create_widgets, and GUI layout ...
    # ----- Speech Initialization -----
    def setup_speech(self):
        """Initialize speech components if available."""
        # Text-to-speech setup
        if TTS_AVAILABLE:
            self.initialize_tts_engine()

        # Speech recognition setup (unchanged)
        if STT_AVAILABLE:
            try:
                self.recognizer = sr.Recognizer()
                self.recognizer.energy_threshold = 300
                self.recognizer.dynamic_energy_threshold = True
                self.recognizer.pause_threshold = 0.8
                self.microphone = sr.Microphone()
                # Calibrate in background
                threading.Thread(target=self.calibrate_microphone, daemon=True).start()
            except Exception as e:
                self.log_message(f"Speech recognition initialization failed: {e}", "error")
                self.recognizer = None
                self.microphone = None

    def calibrate_microphone(self):
        """Calibrate microphone for ambient noise."""
        try:
            with self.microphone as source:
                self.recognizer.adjust_for_ambient_noise(source, duration=1)
            self.log_message("Microphone calibrated", "system")
        except Exception as e:
            self.log_message(f"Microphone calibration failed: {e}", "error")

    # ----- Widget Creation -----
    def create_widgets(self):
        """Create all main GUI elements."""
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky="nsew")
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(1, weight=1)

        # Chat area (history)
        self.create_chat_area(main_frame)

        # Input area (with Voice Input button, send, etc.)
        self.create_input_area(main_frame)

        # Status bar at the bottom
        self.create_status_bar(main_frame)

    def create_chat_area(self, parent):
        """Chat display area."""
        chat_frame = ttk.LabelFrame(parent, text="Conversation", padding="5")
        chat_frame.grid(row=1, column=0, sticky="nsew", pady=(0, 10))
        chat_frame.columnconfigure(0, weight=1)
        chat_frame.rowconfigure(0, weight=1)

        self.chat_display = scrolledtext.ScrolledText(
            chat_frame, wrap=tk.WORD, height=15,
            font=('Consolas', 10), state=tk.DISABLED
        )
        self.chat_display.grid(row=0, column=0, sticky="nsew")
        self.chat_display.tag_configure("user", foreground="blue", font=('Consolas', 10, 'bold'))
        self.chat_display.tag_configure("assistant", foreground="green", font=('Consolas', 10))
        self.chat_display.tag_configure("system", foreground="gray", font=('Consolas', 9, 'italic'))
        self.chat_display.tag_configure("error", foreground="red", font=('Consolas', 10))

    def create_input_area(self, parent):
        """Entry, Send, and Voice Input buttons."""
        input_frame = ttk.LabelFrame(parent, text="Input", padding="5")
        input_frame.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        input_frame.columnconfigure(0, weight=1)

        # Text entry
        self.input_entry = ttk.Entry(input_frame, font=('Consolas', 10))
        self.input_entry.grid(row=0, column=0, sticky="ew", padx=(0, 5))
        self.input_entry.bind('<Return>', self.send_message)
        input_frame.columnconfigure(0, weight=1)

        # Send button
        self.send_btn = ttk.Button(input_frame, text="Send", command=self.send_message)
        self.send_btn.grid(row=0, column=1, padx=(0, 2))

        # Voice Input button (conditionally)
        if self.speech_capable:
            self.voice_btn = ttk.Button(input_frame, text="🎤 Voice Input", command=self.start_voice_input)
            self.voice_btn.grid(row=0, column=2, padx=(0, 2))
        else:
            # Optional: Show disabled button or a label
            self.voice_btn = ttk.Button(input_frame, text="🎤 Voice Input (Unavailable)", state=tk.DISABLED)
            self.voice_btn.grid(row=0, column=2, padx=(0, 2))

        # ADD FEEDBACK BUTTON HERE
        self.feedback_button = ttk.Button(
            input_frame,
            text="⚠️ Wrong Answer",
            command=self.report_wrong_answer,
            state='disabled'  # Initially disabled
        )
        self.feedback_button.grid(row=0, column=3, padx=(5, 0))
    def create_status_bar(self, parent):
        status_frame = ttk.Frame(parent)
        status_frame.grid(row=3, column=0, sticky="ew")
        status_frame.columnconfigure(0, weight=1)
        self.status_label = ttk.Label(status_frame, text="Ready")
        self.status_label.grid(row=0, column=0, sticky=tk.W)
        self.voice_status = ttk.Label(status_frame, text="")  # Used for voice status updates
        self.voice_status.grid(row=0, column=1, sticky=tk.E)

        # Add Stop Speaking button (TTS only)
        if TTS_AVAILABLE:
            self.stop_speaking_btn = ttk.Button(
                status_frame,
                text="Stop Speaking",
                command=self.stop_speaking,
                state=tk.DISABLED
            )
            self.stop_speaking_btn.grid(row=0, column=2, padx=(10, 0))

            # Add TTS toggle button
            self.tts_toggle_btn = ttk.Button(
                status_frame,
                text="🔈 Auto-Speak: On" if self.auto_speak_responses.get() else "🔇 Auto-Speak: Off",
                command=self.toggle_auto_speak
            )
            self.tts_toggle_btn.grid(row=0, column=3, padx=(10, 0))
        else:
            self.stop_speaking_btn = None
            self.tts_toggle_btn = None

    def toggle_auto_speak(self):
        """Toggle automatic TTS of responses."""
        current = self.auto_speak_responses.get()
        self.auto_speak_responses.set(not current)
        if self.auto_speak_responses.get():
            self.tts_toggle_btn.config(text="🔈 Auto-Speak: On")
            self.log_message("Auto-read responses: ON", "system")
        else:
            self.tts_toggle_btn.config(text="🔇 Auto-Speak: Off")
            self.log_message("Auto-read responses: OFF", "system")

    # ----- VOICE INPUT WORKFLOW -----
    def start_voice_input(self):
        """Begin voice recognition and paste result into entry box."""
        if not self.speech_capable or not self.recognizer or not self.microphone:
            messagebox.showwarning("Voice Not Available", "Speech recognition is not available on this system.")
            return

        def recognize_and_insert():
            self.voice_status.config(text="Listening...")
            try:
                with self.microphone as source:
                    self.recognizer.adjust_for_ambient_noise(source, duration=0.5)
                    audio = self.recognizer.listen(source)
                self.voice_status.config(text="Recognizing...")
                try:
                    # You can replace 'recognize_google' with another recognizer if you use Azure/other.
                    result = self.recognizer.recognize_google(audio)
                    self.input_entry.delete(0, tk.END)
                    self.input_entry.insert(0, result)
                    self.input_entry.focus_set()
                    self.voice_status.config(text="Voice input ready for editing")
                except Exception as e:
                    self.voice_status.config(text="Recognition failed")
                    self.log_message(f"Speech recognition error: {e}", "error")
            except Exception as e:
                self.voice_status.config(text="Microphone error")
                self.log_message(f"Microphone error: {e}", "error")

        threading.Thread(target=recognize_and_insert, daemon=True).start()

    def initialize_tts_engine(self):
        """Initialize or reinitialize the TTS engine."""
        try:
            # Clean up existing engine if any
            if hasattr(self, 'tts_engine') and self.tts_engine:
                try:
                    self.tts_engine.stop()
                except:
                    pass
                del self.tts_engine

            # Create new engine
            self.tts_engine = pyttsx3.init()

            # Configure voice (prefer female voice)
            voices = self.tts_engine.getProperty('voices')
            if voices:
                for voice in voices:
                    if 'female' in voice.name.lower() or 'zira' in voice.name.lower():
                        self.tts_engine.setProperty('voice', voice.id)
                        break

            # Set properties
            self.tts_engine.setProperty('rate', 165)
            self.tts_engine.setProperty('volume', 0.9)

            self.tts_engine_valid = True
            self.log_message("TTS engine initialized", "system")

        except Exception as e:
            self.log_message(f"TTS initialization failed: {e}", "error")
            self.tts_engine = None
            self.tts_engine_valid = False

    # ----- SENDING MESSAGES TO SERVER -----
    def send_message(self, event=None):
        """Send the current input text to the server."""
        text = self.input_entry.get().strip()
        if not text:
            return

        # TRACK THE QUERY FOR FEEDBACK
        self.last_query_question = text
        self.last_query_timestamp = datetime.now()
        self.last_query_sql = None  # Will be populated if we get SQL info back

        # Disable feedback button during query processing
        self.feedback_button.config(state='disabled')

        self.log_message(text, "user")
        self.input_entry.delete(0, tk.END)
        self.status_label.config(text="Waiting for response...")
        threading.Thread(target=self.query_server, args=(text,), daemon=True).start()

    def query_server(self, text):
        """POST a message to the server, show response, and maybe speak it."""
        try:
            payload = {"question": text, "session_id": self.session_id}
            url = f"{self.server_url}/ask"
            response = self.session.post(url, json=payload, timeout=90)
            if response.status_code == 200:
                data = response.json()
                answer = data.get("answer", "")
                self.session_id = data.get("session_id", self.session_id)

                # STORE RESPONSE AND EXTRACT SQL IF AVAILABLE
                self.last_query_response = answer
                self.extract_sql_from_response(answer)

                self.show_response(answer)

                # ENABLE FEEDBACK BUTTON AFTER SUCCESSFUL RESPONSE
                self.feedback_button.config(state='normal')
            else:
                error = f"Server error: {response.status_code} {response.text}"
                self.last_query_response = error
                self.show_response(error, is_error=True)
        except Exception as e:
            error = f"Connection failed: {e}"
            self.last_query_response = error
            self.show_response(error, is_error=True)

    # ----- SHOW RESPONSE -----
    def show_response(self, text, is_error=False):
        """Display the server response in the chat and (optionally) speak it."""
        tag = "assistant" if not is_error else "error"
        self.log_message(text, tag)
        self.last_response = text
        self.status_label.config(text="Ready")
        if self.auto_speak_responses.get() and self.tts_engine and not is_error:
            threading.Thread(target=self.speak_text, args=(text,), daemon=True).start()

    def log_message(self, message, tag="system"):
        """Append a message to the chat window."""
        self.chat_display.config(state=tk.NORMAL)
        if tag == "user":
            self.chat_display.insert(tk.END, "\nYou: ", "user")
            self.chat_display.insert(tk.END, f"{message}\n", "user")
        elif tag == "assistant":
            self.chat_display.insert(tk.END, "Assistant: ", "assistant")
            self.chat_display.insert(tk.END, f"{message}\n", "assistant")
        elif tag == "error":
            self.chat_display.insert(tk.END, "Error: ", "error")
            self.chat_display.insert(tk.END, f"{message}\n", "error")
        else:
            self.chat_display.insert(tk.END, f"{message}\n", tag)
        self.chat_display.config(state=tk.DISABLED)
        self.chat_display.see(tk.END)

    # ----- TEXT-TO-SPEECH FOR RESPONSES -----
    def speak_text(self, text):
        """Speak the provided text using TTS (for responses only)."""
        if not TTS_AVAILABLE:
            return

        # Reinitialize engine if needed
        if not self.tts_engine_valid or not self.tts_engine:
            self.initialize_tts_engine()

        if not self.tts_engine:
            return

        try:
            self.is_speaking = True
            self.stop_speech_requested = False  # Add this flag to track stop requests

            # Update UI
            self.voice_status.config(text="Speaking response...")
            if self.stop_speaking_btn:
                self.stop_speaking_btn.config(state=tk.NORMAL)

            # Split text into sentences for better stop control
            sentences = self.split_text_for_speech(text)

            for sentence in sentences:
                # Check if stop was requested
                if self.stop_speech_requested:
                    break

                try:
                    self.tts_engine.say(sentence)
                    self.tts_engine.runAndWait()
                except Exception as e:
                    self.log_message(f"TTS sentence error: {e}", "error")
                    # Try to reinitialize for next time
                    self.tts_engine_valid = False
                    break

        except Exception as e:
            self.log_message(f"TTS Error: {e}", "error")
            # Mark engine as needing reinitialization
            self.tts_engine_valid = False
        except RuntimeError as e:
            if "run loop already started" in str(e):
                # Just log it and continue - don't break the user experience
                self.log_message("TTS temporarily unavailable", "system")
            else:
                self.log_message(f"TTS Error: {e}", "error")
        finally:
            # Clean up UI state
            self.is_speaking = False
            self.stop_speech_requested = False
            self.voice_status.config(text="")
            if self.stop_speaking_btn:
                self.stop_speaking_btn.config(state=tk.DISABLED)

    def split_text_for_speech(self, text):
        """Split text into manageable chunks for speaking."""
        # Simple sentence splitting
        sentences = re.split(r'[.!?]+', text)
        # Clean up and filter
        sentences = [s.strip() for s in sentences if s.strip()]
        # If no sentences found, return the whole text
        if not sentences:
            return [text]
        return sentences

    def speak_last_response(self):
        """Speak the last assistant response again."""
        if self.last_response and not self.is_speaking:
            threading.Thread(target=self.speak_text, args=(self.last_response,), daemon=True).start()
        elif self.is_speaking:
            self.log_message("Already speaking - stop current speech first", "system")

    # ----- SETTINGS DIALOG -----
    def show_settings(self):
        """Show settings for server URL and speech options."""
        settings_window = tk.Toplevel(self.root)
        settings_window.title("Settings")
        settings_window.geometry("400x300")
        settings_window.transient(self.root)
        settings_window.grab_set()

        notebook = ttk.Notebook(settings_window)
        notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # --- Connection tab ---
        conn_frame = ttk.Frame(notebook)
        notebook.add(conn_frame, text="Connection")

        ttk.Label(conn_frame, text="Server URL:").grid(row=0, column=0, sticky=tk.W, padx=10, pady=5)
        server_var = tk.StringVar(value=self.server_url)
        server_entry = ttk.Entry(conn_frame, textvariable=server_var, width=40)
        server_entry.grid(row=0, column=1, padx=10, pady=5)

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

        ttk.Button(conn_frame, text="Test Connection", command=test_new_connection).grid(row=1, column=1, pady=10)

        # --- Speech tab (only if TTS available) ---
        if TTS_AVAILABLE:
            speech_frame = ttk.Frame(notebook)
            notebook.add(speech_frame, text="Speech")

            ttk.Checkbutton(
                speech_frame,
                text="Auto-read responses aloud",
                variable=self.auto_speak_responses
            ).grid(row=0, column=0, columnspan=2, sticky=tk.W, padx=10, pady=5)

            # Test voice button
            def test_voice():
                if self.tts_engine:
                    self.tts_engine.setProperty('rate', 165)
                    self.tts_engine.setProperty('volume', 0.9)
                    test_text = "This is a test of the text-to-speech feature."
                    self.tts_engine.say(test_text)
                    self.tts_engine.runAndWait()
            ttk.Button(speech_frame, text="Test Voice", command=test_voice).grid(row=2, column=1, pady=20)

        # Save/Cancel
        button_frame = ttk.Frame(settings_window)
        button_frame.pack(fill=tk.X, padx=10, pady=(0, 10))
        def save_settings():
            self.server_url = server_var.get()
            settings_window.destroy()
            self.test_connection()
            self.log_message("Settings saved", "system")
        ttk.Button(button_frame, text="Save", command=save_settings).pack(side=tk.RIGHT, padx=(5, 0))
        ttk.Button(button_frame, text="Cancel", command=settings_window.destroy).pack(side=tk.RIGHT)

    def stop_speaking(self):
        """Stop speaking the current response."""
        if not self.is_speaking:
            return

        try:
            # Set flag to stop speaking loop
            self.stop_speech_requested = True

            # Force stop the engine
            if self.tts_engine:
                try:
                    self.tts_engine.stop()
                except Exception as e:
                    self.log_message(f"Error stopping TTS engine: {e}", "error")

            # Update UI immediately
            self.voice_status.config(text="Speech stopped")
            if self.stop_speaking_btn:
                self.stop_speaking_btn.config(state=tk.DISABLED)

            # Mark for reinitialization (this ensures fresh engine next time)
            self.tts_engine_valid = False
            self.is_speaking = False

            self.log_message("Speech stopped by user", "system")

        except Exception as e:
            self.log_message(f"Failed to stop TTS: {e}", "error")

    def reset_server_session(self):
        """Reset session when server is restarted"""
        self.session_id = None  # Clear old session
        self.conversation_active = False
        self.current_suggestions = []

        # RESET FEEDBACK TRACKING
        self.last_query_sql = None
        self.last_query_question = None
        self.last_query_response = None
        self.last_query_timestamp = None

        # Disable feedback button
        self.feedback_button.config(state='disabled')

        self.log_message("Server session reset - starting fresh conversation", "system")

# Reset the stop request flag
    # ----- TEST SERVER CONNECTION -----
    def test_connection(self):
        """Test connection and reset session if server restarted"""
        try:
            url = f"{self.server_url}/health"
            response = self.session.get(url, timeout=5)
            if response.status_code == 200:
                # Check if our session_id is still valid
                if self.session_id:
                    status_url = f"{self.server_url}/conversation_state/{self.session_id}"
                    try:
                        session_check = self.session.get(status_url, timeout=5)
                        if session_check.status_code == 404:
                            # Session doesn't exist on server - reset
                            self.reset_server_session()
                            self.log_message("Detected server restart - session reset", "system")
                    except:
                        # Assume server restart if we can't check session
                        self.reset_server_session()

                self.status_label.config(text="Connected to server.")
                self.log_message("Connected to server.", "system")
            else:
                self.status_label.config(text=f"Server error: {response.status_code}")
                self.log_message(f"Server error: {response.status_code}", "error")
        except Exception as e:
            self.status_label.config(text=f"Connection failed: {e}")
            self.log_message(f"Connection failed: {e}", "error")

    def extract_sql_from_response(self, response_text):
        """Extract SQL query from the response if present"""

        # Look for SQL patterns in the response
        sql_patterns = [
            r'```sql\n(.*?)\n```',  # Markdown SQL blocks
            r'```\n(SELECT.*?)\n```',  # Generic code blocks with SELECT
            r'(SELECT\s+.*?;)',  # Standalone SELECT statements
            r'SQL:\s*(SELECT.*?)(?:\n|$)',  # SQL: prefix
        ]

        for pattern in sql_patterns:
            matches = re.findall(pattern, response_text, re.DOTALL | re.IGNORECASE)
            if matches:
                # Take the first match and clean it up
                sql = matches[0].strip()
                if sql:
                    self.last_query_sql = sql
                    break

    def report_wrong_answer(self):
        """Send feedback to server instead of handling locally"""
        if not self.last_query_question:
            messagebox.showwarning("No Query", "No recent query to report on.")
            return

        try:
            # Prepare feedback data
            feedback_data = {
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "event_type": "WRONG_ANSWER_FEEDBACK",
                "session_id": self.session_id,
                "user_question": self.last_query_question,
                "system_response": self.last_query_response,
                "sql_query": self.last_query_sql if self.last_query_sql else "No SQL available",
                "query_timestamp": self.last_query_timestamp.strftime(
                    "%Y-%m-%d %H:%M:%S") if self.last_query_timestamp else "Unknown"
            }

            # Send to server
            response = self.session.post(
                f"{self.server_url}/feedback",
                json=feedback_data,
                timeout=10
            )

            if response.status_code == 200:
                messagebox.showinfo("Feedback Submitted",
                                    "Thank you for the feedback! The issue has been logged and an administrator has been notified.")
            else:
                messagebox.showerror("Error", "Failed to submit feedback. Please try again.")

        except Exception as e:
            messagebox.showerror("Error", f"Failed to submit feedback: {e}")

        # Disable button regardless
        self.feedback_button.config(state='disabled')

    def log_wrong_answer_feedback(self):
        """Log the wrong answer feedback to the system log"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        log_entry = {
            "timestamp": timestamp,
            "event_type": "WRONG_ANSWER_FEEDBACK",
            "session_id": self.session_id,
            "user_question": self.last_query_question,
            "system_response": self.last_query_response,
            "sql_query": self.last_query_sql if self.last_query_sql else "No SQL available",
            "query_timestamp": self.last_query_timestamp.strftime(
                "%Y-%m-%d %H:%M:%S") if self.last_query_timestamp else "Unknown"
        }

        # Log to the standard logger (you might want to set up logging if not already done)
        print(f"WRONG ANSWER REPORTED: {json.dumps(log_entry, indent=2)}")

        # Also write to a dedicated feedback log file
        try:
            feedback_log_dir = Path("C:/Logs")
            feedback_log_dir.mkdir(exist_ok=True)

            feedback_log_file = feedback_log_dir / "voice_sql_feedback.log"

            with open(feedback_log_file, 'a', encoding='utf-8') as f:
                f.write(f"{json.dumps(log_entry)}\n")

        except Exception as e:
            print(f"Failed to write to feedback log file: {e}")

    def send_feedback_email(self):
        """Send email notification about wrong answer feedback"""
        # Check if email is configured
        to_addresses = [addr.strip() for addr in self.feedback_email_config['to_addresses'] if addr.strip()]

        if not to_addresses:
            # Log that email wasn't sent due to missing configuration
            print("Feedback email not sent - no recipient addresses configured")
            return

        try:
            # Prepare email content
            subject = f"[Voice SQL] Wrong Answer Reported - {datetime.now().strftime('%Y-%m-%d %H:%M')}"

            body = f"""
A user has reported a wrong answer from the Voice SQL system.

Session Details:
- Session ID: {self.session_id}
- Timestamp: {self.last_query_timestamp.strftime('%Y-%m-%d %H:%M:%S') if self.last_query_timestamp else 'Unknown'}

User Question:
{self.last_query_question}

System Response:
{self.last_query_response}

SQL Query Used:
{self.last_query_sql if self.last_query_sql else 'No SQL query information available'}

Please review the feedback log for additional details:
C:/Logs/voice_sql_feedback.log

This feedback was automatically generated by the Voice SQL Client.
            """

            # Create email message
            msg = MIMEMultipart()
            msg['From'] = self.feedback_email_config['from_address']
            msg['To'] = ', '.join(to_addresses)
            msg['Subject'] = subject
            msg.attach(MIMEText(body, 'plain'))

            # Send email
            with smtplib.SMTP(
                    self.feedback_email_config['smtp_server'],
                    self.feedback_email_config['smtp_port']
            ) as server:
                server.send_message(msg)

            # Log successful email send
            print(f"Feedback email sent successfully to {to_addresses}")

        except Exception as e:
            # Log email failure but don't fail the feedback process
            print(f"Failed to send feedback email: {e}")

# ---- MAIN APP ENTRY ----
if __name__ == "__main__":
    root = tk.Tk()
    app = VoiceClientGUI(root)
    root.mainloop()
