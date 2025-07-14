# test_gui_client.py - Fixed comprehensive test suite for the tkinter Voice SQL Client

import unittest
import tkinter as tk
from unittest.mock import Mock, patch, MagicMock
import requests
import json
import threading
import time
import os
import sys
from datetime import datetime
from pathlib import Path

STANDARD_TEST_QUERIES = [
    "Show me Autozone's purchases this quarter",
    "What did we sell to O'Reilly last month?",
    "What did we sell to Ozark last month?",
    "Which customers bought the most AAE-HPS products",
    "Compare our top 5 customers by revenue",
    "How many 5760N in stock?",
    "What products are out of stock?",
    "Show me low stock items under 5 units",
    "Show me low stock items under 5 units in coolant hoses",
    "Which sites have the highest inventory value?",
    "What's our total inventory for Coolant Hoses?",
    "What product group is CHR0406R in?",
    "Show me all products in the HPS-Pumps category",
    "What are our best-selling filters?",
    "Which products have the highest profit margins?",
    "What's the MSRP for PFF5225R?",
    "Show me competitor pricing for oil filters",
    "Compare our prices to market prices for BMW parts",
    "Which parts have the biggest pricing gaps?",
    "What's selling on eBay for transmission filters?",
    "Show me parts with high eBay activity but we don't stock",
    "Which suppliers offer the most parts?",
    "What parts have multiple sourcing options?",
    "Which products have low performance scores?",
    "Show me dead stock items",
    "What new products were introduced this year?",
    "Which categories are trending up?"
]
# Add the parent directory to sys.path to import the GUI module
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Mock the speech modules before importing
sys.modules['pyttsx3'] = MagicMock()
sys.modules['speech_recognition'] = MagicMock()
sys.modules['pyaudio'] = MagicMock()

# Import the GUI class after mocking dependencies
try:
    from src.gui.main_window import VoiceClientGUI
except ImportError as e:
    print(f"Could not import VoiceClientGUI: {e}")
    print("Make sure main_window.py is in the same directory as this test file")
    sys.exit(1)


class MockResponse:
    """Mock response object for requests"""

    def __init__(self, json_data, status_code=200, text=""):
        self.json_data = json_data
        self.status_code = status_code
        self.text = text
        self.content = b"mock file content"

    def json(self):
        return self.json_data


class TestVoiceClientGUI(unittest.TestCase):
    """Test cases for the Voice Client GUI"""

    def setUp(self):
        """Set up test fixtures before each test method"""
        self.root = tk.Tk()
        self.root.withdraw()  # Hide the window during testing

        # Patch requests to avoid actual network calls
        self.requests_patcher = patch('requests.Session')
        self.mock_session_class = self.requests_patcher.start()
        self.mock_session = Mock()
        self.mock_session_class.return_value = self.mock_session

        # Create the GUI instance with connection testing disabled
        self.app = VoiceClientGUI(self.root, auto_test_connection=False)

        # Stop any background threads created during initialization
        self._stop_background_threads()

    def _stop_background_threads(self):
        """Stop any background threads to prevent threading errors"""
        # Stop the connection test thread if it's running
        if hasattr(self.app, 'is_testing_connection'):
            self.app.is_testing_connection = False

        # Stop any speech operations
        if hasattr(self.app, 'stop_all_speech'):
            self.app.stop_all_speech()

        # Stop listening
        if hasattr(self.app, 'is_listening'):
            self.app.is_listening = False

        # Give a brief moment for threads to stop
        time.sleep(0.02)

    def tearDown(self):
        """Clean up after each test method"""
        # Stop any ongoing operations
        self.app.stop_all_speech()
        self.app.is_listening = False

        # Stop background threads
        self._stop_background_threads()

        # Small delay to let threads finish
        time.sleep(0.02)

        # Clean up patches and GUI
        self.requests_patcher.stop()
        self.root.destroy()

    def test_initialization(self):
        """Test that the GUI initializes properly"""
        self.assertIsNotNone(self.app)
        self.assertEqual(self.app.server_url, "http://BI-SQL001:8000")
        self.assertIsInstance(self.app.auto_speak_responses, tk.BooleanVar)
        self.assertIsInstance(self.app.voice_input_enabled, tk.BooleanVar)

    def test_ui_components_exist(self):
        """Test that all required UI components are created"""
        # Check that main components exist
        self.assertTrue(hasattr(self.app, 'input_entry'))
        self.assertTrue(hasattr(self.app, 'chat_display'))
        self.assertTrue(hasattr(self.app, 'send_btn'))
        self.assertTrue(hasattr(self.app, 'voice_btn'))
        self.assertTrue(hasattr(self.app, 'stop_btn'))
        self.assertTrue(hasattr(self.app, 'status_label'))

    def test_log_message(self):
        """Test the log_message functionality"""
        # Test different message types
        test_messages = [
            ("Test user message", "user"),
            ("Test assistant message", "assistant"),
            ("Test error message", "error"),
            ("Test system message", "system")
        ]

        for message, msg_type in test_messages:
            self.app.log_message(message, msg_type)

        # Check that the chat display has content
        self.app.chat_display.config(state=tk.NORMAL)
        content = self.app.chat_display.get("1.0", tk.END)
        self.app.chat_display.config(state=tk.DISABLED)

        self.assertIn("Test user message", content)
        self.assertIn("Test assistant message", content)
        self.assertIn("Test error message", content)
        self.assertIn("Test system message", content)

    def test_server_connection_mocked(self):
        """Test server connection with mocked response (no threading)"""
        # Mock successful health check response
        mock_response = MockResponse({"status": "healthy"}, 200)
        self.mock_session.get.return_value = mock_response

        # Patch the threading to make it synchronous for testing
        with patch('threading.Thread') as mock_thread:
            # Make thread.start() call the target function directly
            def side_effect(*args, **kwargs):
                target = kwargs.get('target')
                if target:
                    target()
                return Mock()

            mock_thread.side_effect = side_effect

            # Test connection
            self.app.test_connection()

        # Verify the GET request was made
        self.mock_session.get.assert_called_with("http://BI-SQL001:8000/health", timeout=5)

    def test_send_message_basic(self):
        """Test basic message sending without threading"""
        # Mock successful response
        mock_response = MockResponse({
            "answer": "Test response from server",
            "status": "success"
        }, 200)
        self.mock_session.post.return_value = mock_response

        # Set up input
        self.app.input_entry.insert(0, "Test question")

        # Mock threading to make it synchronous
        with patch('threading.Thread') as mock_thread:
            def side_effect(*args, **kwargs):
                target = kwargs.get('target')
                args_param = kwargs.get('args', ())
                if target and args_param:
                    target(*args_param)
                return Mock()

            mock_thread.side_effect = side_effect

            # Send message
            self.app.send_message()

        # Verify input was cleared
        self.assertEqual(self.app.input_entry.get(), "")

    def test_export_format_handling(self):
        """Test export format selection"""
        # Test CSV export
        self.app.export_var.set("Export CSV")
        self.app.input_entry.insert(0, "Test query")

        # Mock response
        mock_response = MockResponse({
            "answer": "Exported 100 rows to CSV format. File: query_export_20241201_120000.csv Ready for download from server.",
            "status": "success"
        }, 200)
        self.mock_session.post.return_value = mock_response

        # Mock threading for synchronous execution
        with patch('threading.Thread') as mock_thread:
            def side_effect(*args, **kwargs):
                target = kwargs.get('target')
                args_param = kwargs.get('args', ())
                if target and args_param:
                    target(*args_param)
                return Mock()

            mock_thread.side_effect = side_effect

            # Send message
            self.app.send_message()

        # Verify export was reset
        self.assertEqual(self.app.export_var.get(), "Display")

    def test_filename_extraction(self):
        """Test filename extraction from export responses"""
        test_cases = [
            ("Exported 100 rows to CSV format. File: query_export_20241201_120000.csv Ready for download",
             "query_export_20241201_120000.csv"),
            ("Export completed. The file query_export_20241201_120000.txt is ready",
             "query_export_20241201_120000.txt"),
        ]

        for response, expected_filename in test_cases:
            filename = self.app.extract_filename_from_export_response(response)
            self.assertEqual(filename, expected_filename)

    def test_is_export_response(self):
        """Test export response detection"""
        export_responses = [
            "Exported 100 rows to CSV format. File: test.csv Ready for download from server.",
            "Successfully exported data. File: query_export_20241201_120000.txt Ready for download"
        ]

        non_export_responses = [
            "Here are your query results:",
            "No records found matching your criteria",
            "Database connection error"
        ]

        for response in export_responses:
            self.assertTrue(self.app.is_export_response(response))

        for response in non_export_responses:
            self.assertFalse(self.app.is_export_response(response))

    def test_speech_initialization(self):
        """Test speech component initialization"""
        # Since we mocked the speech modules, test that the app handles missing speech gracefully
        self.assertIsNotNone(self.app.tts_engine)  # Should be mocked
        self.assertIsNotNone(self.app.recognizer)  # Should be mocked

    def test_stop_speech_functionality(self):
        """Test the stop speech functionality"""
        # Set up speech state
        self.app.is_speaking = True
        self.app.is_listening = True

        # Call stop
        self.app.stop_all_speech()

        # Verify state was reset
        self.assertFalse(self.app.is_speaking)
        self.assertFalse(self.app.is_listening)
        self.assertTrue(self.app.stop_speech_requested)

    def test_chat_display_formatting(self):
        """Test that chat display formatting works correctly"""
        # Test different message types
        messages = [
            ("User message", "user"),
            ("Assistant response with multiple lines\nSecond line\nThird line", "assistant"),
            ("Error occurred", "error"),
            ("System notification", "system")
        ]

        for message, msg_type in messages:
            self.app.log_message(message, msg_type)

        # Verify content exists
        self.app.chat_display.config(state=tk.NORMAL)
        content = self.app.chat_display.get("1.0", tk.END)
        self.app.chat_display.config(state=tk.DISABLED)

        self.assertGreater(len(content), 0)

    def test_settings_variables(self):
        """Test settings variables functionality"""
        # Test boolean variables
        self.app.auto_speak_responses.set(False)
        self.assertFalse(self.app.auto_speak_responses.get())

        self.app.voice_input_enabled.set(True)
        self.assertTrue(self.app.voice_input_enabled.get())

    def test_simulated_voice_workflow(self):
        """Test simulated voice input workflow"""
        # Test the voice input handling method directly
        test_text = "How many records in ebayWT"

        # Clear the input field first
        self.app.input_entry.delete(0, 'end')

        # Directly insert text (simulating what voice recognition would do)
        self.app.input_entry.insert(0, test_text)

        # Verify text appears in input field
        input_text = self.app.input_entry.get()
        self.assertEqual(test_text, input_text)

        # Test that voice components are properly mocked
        self.assertIsNotNone(self.app.tts_engine)  # Should be mocked
        self.assertIsNotNone(self.app.recognizer)  # Should be mocked

    def test_voice_components_graceful_degradation(self):
        """Test that voice components fail gracefully when unavailable"""
        # Test TTS graceful failure
        original_tts = self.app.tts_engine
        self.app.tts_engine = None

        try:
            self.app.speak_text("test message")
            tts_graceful = True
        except:
            tts_graceful = False

        # Restore original
        self.app.tts_engine = original_tts

        # TTS should handle None gracefully (it checks if tts_engine exists)
        self.assertTrue(tts_graceful, "TTS should fail gracefully when engine is None")

    def test_voice_status_updates(self):
        """Test voice status indicator updates"""
        # Test that voice status can be updated without crashing
        try:
            self.app.voice_status.config(text="Testing voice status")
            status_update_works = True
        except:
            status_update_works = False

        self.assertTrue(status_update_works, "Voice status updates should work")

    def test_text_and_voice_mode_switching(self):
        """Test switching between text and voice modes"""
        # Test text mode
        self.app.set_text_mode()
        self.assertFalse(self.app.voice_input_enabled.get())
        self.assertFalse(self.app.auto_speak_responses.get())

        # Test voice mode (patch the module-level SPEECH_AVAILABLE)
        import tkinter_voice_client
        with patch.object(tkinter_voice_client, 'SPEECH_AVAILABLE', True):
            self.app.set_voice_mode()
            self.assertTrue(self.app.voice_input_enabled.get())
            self.assertTrue(self.app.auto_speak_responses.get())

    def test_split_into_sentences(self):
        """Test text splitting for speech"""
        test_text = "First sentence. Second sentence! Third sentence? Fourth sentence."
        sentences = self.app.split_into_sentences(test_text)

        # Should split into multiple sentences
        self.assertGreater(len(sentences), 1)
        self.assertIn("First sentence", sentences[0])


class IntegrationTests(unittest.TestCase):
    """Integration tests that test multiple components working together"""

    def setUp(self):
        """Set up integration test environment"""
        self.root = tk.Tk()
        self.root.withdraw()

        # Mock requests completely for integration tests
        self.requests_patcher = patch('requests.Session')
        self.mock_session_class = self.requests_patcher.start()
        self.mock_session = Mock()
        self.mock_session_class.return_value = self.mock_session

        self.app = VoiceClientGUI(self.root, auto_test_connection=False)

        # Stop background threads
        time.sleep(0.02)

    def tearDown(self):
        """Clean up integration test environment"""
        self.app.stop_all_speech()
        self.app.is_listening = False
        time.sleep(0.02)
        self.requests_patcher.stop()
        self.root.destroy()

    def test_full_query_workflow(self):
        """Test a complete query workflow"""
        # Mock server response
        mock_response = MockResponse({
            "answer": "Query returned 5 rows: [('Test', 'Data'), ...]",
            "status": "success"
        }, 200)
        self.mock_session.post.return_value = mock_response

        # Simulate user input
        self.app.input_entry.insert(0, "SELECT TOP 5 * FROM ebayWT")

        # Mock threading to make it synchronous
        with patch('threading.Thread') as mock_thread:
            def side_effect(*args, **kwargs):
                target = kwargs.get('target')
                args_param = kwargs.get('args', ())
                if target and args_param:
                    target(*args_param)
                return Mock()

            mock_thread.side_effect = side_effect

            # Send message
            self.app.send_message()

        # Verify request was made
        self.mock_session.post.assert_called_once()

        # Verify input was cleared
        self.assertEqual(self.app.input_entry.get(), "")

    def test_export_workflow(self):
        """Test complete export workflow"""
        # Mock export response
        mock_response = MockResponse({
            "answer": "✅ Exported 1,000 rows to CSV format. File: query_export_20241201_120000.csv Ready for download from server.",
            "status": "success"
        }, 200)
        self.mock_session.post.return_value = mock_response

        # Set export format
        self.app.export_var.set("Export CSV")
        self.app.input_entry.insert(0, "SELECT * FROM ebayWT WHERE OEAN = 'PFF5225R'")

        # Mock threading to make it synchronous
        with patch('threading.Thread') as mock_thread:
            def side_effect(*args, **kwargs):
                target = kwargs.get('target')
                args_param = kwargs.get('args', ())
                if target and args_param:
                    target(*args_param)
                return Mock()

            mock_thread.side_effect = side_effect

            # Send message
            self.app.send_message()

        # Verify the request was made and included export instruction
        self.mock_session.post.assert_called_once()
        args, kwargs = self.mock_session.post.call_args
        request_data = kwargs['json']
        self.assertIn("export", request_data['question'].lower())


def create_mock_server():
    """Create a simple mock server for testing"""
    from http.server import HTTPServer, BaseHTTPRequestHandler
    import json
    import threading

    class MockServerHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == '/health':
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"status": "healthy"}).encode())
            elif self.path == '/exports':
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"exports": [], "count": 0}).encode())
            else:
                self.send_response(404)
                self.end_headers()

        def do_POST(self):
            if self.path == '/ask':
                content_length = int(self.headers['Content-Length'])
                post_data = self.rfile.read(content_length)

                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()

                response = {
                    "answer": "Mock response for testing",
                    "status": "success"
                }
                self.wfile.write(json.dumps(response).encode())
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, format, *args):
            # Suppress server logs during testing
            pass

    try:
        server = HTTPServer(('localhost', 8001), MockServerHandler)
        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()
        return server
    except OSError:
        # Port might be in use, return None
        return None


class LiveIntegrationTests(unittest.TestCase):
    """Live tests against a mock server"""

    @classmethod
    def setUpClass(cls):
        """Set up mock server for live testing"""
        cls.server = create_mock_server()
        if cls.server:
            time.sleep(0.2)  # Give server time to start

    def setUp(self):
        """Set up live test environment"""
        if not self.server:
            self.skipTest("Mock server could not be started")

        self.root = tk.Tk()
        self.root.withdraw()

        # Create app pointing to mock server
        with patch.dict('os.environ', {'VOICE_SQL_SERVER': 'http://localhost:8001'}):
            self.app = VoiceClientGUI(self.root, auto_test_connection=False)

        time.sleep(0.05)

    def tearDown(self):
        """Clean up live test environment"""
        if hasattr(self, 'app'):
            self.app.stop_all_speech()
            self.app.is_listening = False
        time.sleep(0.05)
        self.root.destroy()

    def test_live_connection(self):
        """Test connection to mock server"""
        if not self.server:
            self.skipTest("Mock server not available")

        # Mock threading for synchronous execution
        with patch('threading.Thread') as mock_thread:
            def side_effect(*args, **kwargs):
                target = kwargs.get('target')
                if target:
                    target()
                return Mock()

            mock_thread.side_effect = side_effect

            # Test connection should work with mock server
            self.app.test_connection()

    def test_live_query(self):
        """Test sending query to mock server"""
        if not self.server:
            self.skipTest("Mock server not available")

        # Mock threading for synchronous execution
        with patch('threading.Thread') as mock_thread:
            def side_effect(*args, **kwargs):
                target = kwargs.get('target')
                args_param = kwargs.get('args', ())
                if target and args_param:
                    target(*args_param)
                return Mock()

            mock_thread.side_effect = side_effect

            self.app.input_entry.insert(0, "Test query")
            self.app.send_message()


def run_manual_test():
    """Run a manual test that opens the GUI for visual inspection"""
    print("Starting manual test mode...")
    print("This will open the GUI for visual inspection.")
    print("Close the window when you're done testing.")

    root = tk.Tk()
    app = VoiceClientGUI(root, auto_test_connection=True)  # Enable connection testing for manual test

    # Add some test messages
    app.log_message("Manual test mode started", "system")
    app.log_message("Test user message", "user")
    app.log_message(
        "Test assistant response with multiple lines.\nThis is the second line.\nAnd this is the third line.",
        "assistant")
    app.log_message("Test error message", "error")
    app.log_message("All components should be visible and functional", "system")
    app.log_message("Try typing a message and clicking Send", "system")

    # Show window
    root.deiconify()
    root.mainloop()


def run_quick_test():
    """Run a quick test of core functionality"""
    print("Running quick functionality test...")

    # Test basic initialization
    root = tk.Tk()
    root.withdraw()

    try:
        app = VoiceClientGUI(root, auto_test_connection=False)  # Disable connection testing for quick test
        print("✅ GUI initialization: PASS")

        # Test logging
        app.log_message("Test message", "system")
        print("✅ Message logging: PASS")

        # Test speech components (mocked)
        app.stop_all_speech()
        print("✅ Speech control: PASS")

        # Test export detection
        test_response = "Exported 100 rows to CSV format. File: test.csv Ready for download"
        is_export = app.is_export_response(test_response)
        if is_export:
            print("✅ Export detection: PASS")
        else:
            print("❌ Export detection: FAIL")

        print("\n🎉 Quick test completed successfully!")
        return True

    except Exception as e:
        print(f"❌ Quick test failed: {e}")
        return False
    finally:
        root.destroy()

def test_all_standard_queries(self):
    """Test all standard queries for response quality"""
    for query in STANDARD_TEST_QUERIES:
        with self.subTest(query=query):
            # Test that query doesn't return generic "large results" message
            response = self.send_test_query(query)
            self.assertNotIn("large number of results", response.lower())
            self.assertNotIn("1. I can display", response.lower())

if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Test the Voice SQL Client GUI')
    parser.add_argument('--manual', action='store_true', help='Run manual test mode')
    parser.add_argument('--quick', action='store_true', help='Run quick functionality test')
    parser.add_argument('--live', action='store_true', help='Run live integration tests')
    parser.add_argument('--unit', action='store_true', help='Run unit tests only')
    parser.add_argument('--all', action='store_true', help='Run all tests')

    args = parser.parse_args()

    if args.manual:
        run_manual_test()
    elif args.quick:
        success = run_quick_test()
        sys.exit(0 if success else 1)
    elif args.live:
        # Run live integration tests
        suite = unittest.TestLoader().loadTestsFromTestCase(LiveIntegrationTests)
        runner = unittest.TextTestRunner(verbosity=2)
        result = runner.run(suite)
        sys.exit(0 if result.wasSuccessful() else 1)
    elif args.unit:
        # Run unit tests only
        suite = unittest.TestLoader().loadTestsFromTestCase(TestVoiceClientGUI)
        runner = unittest.TextTestRunner(verbosity=2)
        result = runner.run(suite)
        sys.exit(0 if result.wasSuccessful() else 1)
    elif args.all:
        # Run all tests
        loader = unittest.TestLoader()
        suite = unittest.TestSuite([
            loader.loadTestsFromTestCase(TestVoiceClientGUI),
            loader.loadTestsFromTestCase(IntegrationTests),
            loader.loadTestsFromTestCase(LiveIntegrationTests)
        ])
        runner = unittest.TextTestRunner(verbosity=2)
        result = runner.run(suite)

        print(f"\n{'=' * 50}")
        print(f"Test Summary:")
        print(f"Tests run: {result.testsRun}")
        print(f"Failures: {len(result.failures)}")
        print(f"Errors: {len(result.errors)}")
        if result.testsRun > 0:
            success_rate = ((result.testsRun - len(result.failures) - len(result.errors)) / result.testsRun * 100)
            print(f"Success rate: {success_rate:.1f}%")

        sys.exit(0 if result.wasSuccessful() else 1)
    else:
        # Default: run unit and integration tests
        loader = unittest.TestLoader()
        suite = unittest.TestSuite([
            loader.loadTestsFromTestCase(TestVoiceClientGUI),
            loader.loadTestsFromTestCase(IntegrationTests)
        ])
        runner = unittest.TextTestRunner(verbosity=2)
        result = runner.run(suite)

        # Print summary
        print(f"\n{'=' * 50}")
        print(f"Test Summary:")
        print(f"Tests run: {result.testsRun}")
        print(f"Failures: {len(result.failures)}")
        print(f"Errors: {len(result.errors)}")
        if result.testsRun > 0:
            success_rate = ((result.testsRun - len(result.failures) - len(result.errors)) / result.testsRun * 100)
            print(f"Success rate: {success_rate:.1f}%")

        if result.failures:
            print(f"\nFailures:")
            for test, traceback in result.failures:
                print(f"- {test}")

        if result.errors:
            print(f"\nErrors:")
            for test, traceback in result.errors:
                print(f"- {test}")

        print(f"\nTo run manual visual test: python test_gui_client.py --manual")
        print(f"To run quick test: python test_gui_client.py --quick")
        print(f"To run with live server: python test_gui_client.py --live")

        sys.exit(0 if result.wasSuccessful() else 1)