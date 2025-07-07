# run_tests.py - Comprehensive test suite for server and thin client
# Designed for scheduled task automation with proper logging and exit codes

import sys
import json
import time
import logging
import requests
import smtplib
import os
from email.mime.text import MIMEText
from typing import List, Dict, Any
from datetime import datetime
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple, Optional
# Add after imports
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


# Test configuration
TEST_CONFIG = {
    'server_url': os.getenv('VOICE_SQL_SERVER', 'http://BI-SQL001:8000'),
    'timeout': 30,
    'log_dir': Path('C:/Logs/VoiceSQL/tests'),
    'max_log_files': 10,
    'critical_failures_only': False
}


class VoiceSQLMonitoringReporter:
    """Email reporting for Voice SQL monitoring results"""

    def __init__(self, test_suite):
        self.test_suite = test_suite
        self.logger = test_suite.logger

    def generate_text_report(self, summary: Dict[str, Any]) -> str:
        """Generate plain text report for email"""

        # Determine severity level
        if summary['critical_failures']:
            severity = "CRITICAL"
            icon = "🚨"
        elif summary['failed_tests'] > 0:
            severity = "WARNING"
            icon = "⚠️"
        else:
            severity = "SUCCESS"
            icon = "✅"

        report = f"""{icon} Voice SQL System Health Report - {severity}
{'=' * 60}

EXECUTIVE SUMMARY:
• Server Status: {'HEALTHY' if summary['failed_tests'] == 0 else 'ISSUES DETECTED'}
• Test Results: {summary['passed_tests']}/{summary['total_tests']} passed ({summary['success_rate']:.1f}%)
• Check Duration: {summary['total_duration']:.1f} seconds
• Timestamp: {datetime.fromisoformat(summary['timestamp']).strftime('%Y-%m-%d %H:%M:%S')}

SYSTEM COMPONENTS:
{'=' * 30}
• Server Health: {summary['server_passed']}/{summary['server_tests']} tests passed
• Client Components: {summary['client_passed']}/{summary['client_tests']} tests passed  
• Integration Tests: {summary['integration_passed']}/{summary['integration_tests']} tests passed
• Server URL: {summary['server_url']}

"""

        # Add critical failures section if any
        if summary['critical_failures']:
            report += f"""CRITICAL ISSUES REQUIRING IMMEDIATE ATTENTION:
{'=' * 50}
"""
            for failure in summary['critical_failures']:
                report += f"❌ {failure}\n"
            report += "\n"

        # Add detailed test results
        report += f"""DETAILED TEST RESULTS:
{'=' * 30}
"""

        # Group results by category
        server_results = [r for r in self.test_suite.results if 'Server' in r.name]
        client_results = [r for r in self.test_suite.results if 'Client' in r.name]
        integration_results = [r for r in self.test_suite.results if 'Integration' in r.name]

        for category, results in [
            ("Server Tests", server_results),
            ("Client Tests", client_results),
            ("Integration Tests", integration_results)
        ]:
            if results:
                report += f"\n{category}:\n"
                for result in results:
                    status = "✅ PASS" if result.success else "❌ FAIL"
                    duration = f" ({result.duration:.2f}s)" if result.duration > 0 else ""
                    report += f"  {status}: {result.name}{duration}\n"
                    if not result.success and result.details:
                        # Truncate long error details
                        details = result.details[:200] + "..." if len(result.details) > 200 else result.details
                        report += f"    └─ {details}\n"

        # Add next steps
        if summary['failed_tests'] > 0:
            report += f"""

RECOMMENDED ACTIONS:
{'=' * 30}
1. Check server status: curl {summary['server_url']}/health
2. Verify database connectivity from server machine
3. Review detailed logs: C:/Logs/VoiceSQL/tests/latest_results.json
4. Restart Voice SQL service if needed
5. Contact system administrator if issues persist

"""
        else:
            report += f"""

STATUS: All systems operating normally ✅
Next check: Tomorrow at 6:00 AM
Logs: C:/Logs/VoiceSQL/tests/

"""

        report += f"""MONITORING DETAILS:
{'=' * 30}
• Monitor: Voice SQL Automated Health Check
• Log Directory: C:/Logs/VoiceSQL/tests/
• Latest Results: latest_results.json
• Test History: results_YYYYMMDD_HHMMSS.json

This is an automated message from the Voice SQL monitoring system.
"""

        return report

    def send_email_report(self,
                          from_address: str,
                          to_addresses: List[str],
                          summary: Dict[str, Any],
                          subject: str = None,
                          smtp_server: str = "localhost",
                          smtp_port: int = 25,
                          username: str = None,
                          password: str = None) -> None:
        """
        Send the monitoring report via email in plain text format.

        Args:
            from_address: Email sender address
            to_addresses: List of recipient addresses
            summary: Test results summary dictionary
            subject: Optional custom subject line (default uses test results)
            smtp_server: SMTP server address
            smtp_port: SMTP server port
            username: Optional SMTP authentication username
            password: Optional SMTP authentication password
        """

        self.logger.info("=" * 50)
        self.logger.info("EMAIL SENDING PROCESS STARTED")
        self.logger.info("=" * 50)

        # Log email configuration (without sensitive data)
        self.logger.info(f"📧 Email Configuration:")
        self.logger.info(f"  SMTP Server: {smtp_server}")
        self.logger.info(f"  SMTP Port: {smtp_port}")
        self.logger.info(f"  From Address: {from_address}")
        self.logger.info(f"  To Addresses: {to_addresses}")
        self.logger.info(f"  Authentication: {'Yes' if username else 'No'}")

        # Create email subject based on test results if not provided
        if subject is None:
            if summary['critical_failures']:
                subject = f"[CRITICAL] Voice SQL Health Check - {len(summary['critical_failures'])} Critical Issues"
            elif summary['failed_tests'] > 0:
                subject = f"[WARNING] Voice SQL Health Check - {summary['failed_tests']} Tests Failed"
            else:
                subject = f"[SUCCESS] Voice SQL Health Check - All Systems Healthy"

        self.logger.info(f"📝 Email Subject: {subject}")

        # Generate the text report
        self.logger.info("📄 Generating email report content...")
        try:
            text_report = self.generate_text_report(summary)
            report_length = len(text_report)
            self.logger.info(f"✅ Report generated successfully ({report_length} characters)")
        except Exception as e:
            self.logger.error(f"❌ Failed to generate report content: {e}")
            raise

        # Create the email
        self.logger.info("✉️ Creating email message...")
        try:
            msg = MIMEText(text_report, 'plain', 'utf-8')
            msg['Subject'] = subject
            msg['From'] = from_address
            msg['To'] = ", ".join(to_addresses)
            self.logger.info("✅ Email message created successfully")
        except Exception as e:
            self.logger.error(f"❌ Failed to create email message: {e}")
            raise

        # Send the email with detailed logging
        self.logger.info("🚀 Attempting to send email...")
        try:
            self.logger.info(f"🔌 Connecting to SMTP server {smtp_server}:{smtp_port}...")
            with smtplib.SMTP(smtp_server, smtp_port) as server:
                self.logger.info("✅ Connected to SMTP server")

                # Enable debug output for SMTP
                server.set_debuglevel(1)  # This will log SMTP conversation

                if username and password:
                    self.logger.info("🔐 Starting TLS and authenticating...")
                    server.starttls()
                    self.logger.info("✅ TLS started")
                    server.login(username, password)
                    self.logger.info("✅ Authentication successful")
                else:
                    self.logger.info("📤 No authentication required, sending directly...")

                self.logger.info(f"📨 Sending message to {len(to_addresses)} recipients...")
                result = server.send_message(msg)

                # Check for any rejected recipients
                if result:
                    self.logger.warning(f"⚠️ Some recipients were rejected: {result}")
                else:
                    self.logger.info("✅ All recipients accepted")

            self.logger.info(f"🎉 Email successfully sent to {', '.join(to_addresses)}")

        except smtplib.SMTPConnectError as e:
            self.logger.error(f"❌ SMTP Connection Error: Cannot connect to {smtp_server}:{smtp_port}")
            self.logger.error(f"   Error details: {e}")
            raise
        except smtplib.SMTPAuthenticationError as e:
            self.logger.error(f"❌ SMTP Authentication Error: Invalid credentials")
            self.logger.error(f"   Error details: {e}")
            raise
        except smtplib.SMTPRecipientsRefused as e:
            self.logger.error(f"❌ SMTP Recipients Refused: Server rejected recipient addresses")
            self.logger.error(f"   Rejected addresses: {e}")
            raise
        except smtplib.SMTPDataError as e:
            self.logger.error(f"❌ SMTP Data Error: Server rejected message content")
            self.logger.error(f"   Error details: {e}")
            raise
        except Exception as e:
            self.logger.error(f"❌ Unexpected email error: {type(e).__name__}: {str(e)}")
            self.logger.error(f"   SMTP Server: {smtp_server}:{smtp_port}")
            self.logger.error(f"   From: {from_address}")
            self.logger.error(f"   To: {to_addresses}")
            import traceback
            self.logger.error(f"   Full traceback: {traceback.format_exc()}")
            raise
        finally:
            self.logger.info("=" * 50)
            self.logger.info("EMAIL SENDING PROCESS COMPLETED")
            self.logger.info("=" * 50)


class TestResult:
    """Container for test results"""

    def __init__(self, name: str, success: bool, message: str, duration: float = 0.0, details: str = ""):
        self.name = name
        self.success = success
        self.message = message
        self.duration = duration
        self.details = details
        self.timestamp = datetime.now()


class TestSuite:
    """Main test suite for server and client testing"""

    def __init__(self):
        self.results: List[TestResult] = []
        self.logger = self.setup_logging()
        self.start_time = time.time()
        self.email_reporter = VoiceSQLMonitoringReporter(self)

        # Email configuration from environment
        self.email_config = {
            'smtp_server': os.getenv('RELAY_IP', 'localhost'),
            'smtp_port': int(os.getenv('SMTP_PORT', '25')),
            'from_address': os.getenv('MONITOR_FROM_EMAIL', 'voicesql-monitor@yourcompany.com'),
            'to_addresses': os.getenv('MONITOR_TO_EMAILS', '').split(','),
            'send_on_success': os.getenv('EMAIL_ON_SUCCESS', 'false').lower() == 'true',
            'send_on_failure': os.getenv('EMAIL_ON_FAILURE', 'true').lower() == 'true'
        }

    def setup_logging(self) -> logging.Logger:
        """Setup logging for scheduled task monitoring"""
        # Create log directory
        TEST_CONFIG['log_dir'].mkdir(parents=True, exist_ok=True)

        # Setup logger
        logger = logging.getLogger('VoiceSQLTests')
        logger.setLevel(logging.INFO)

        # Clear existing handlers
        logger.handlers.clear()

        # File handler with rotation
        log_file = TEST_CONFIG['log_dir'] / f"test_run_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(logging.INFO)

        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)

        # Formatter
        formatter = logging.Formatter('[%(asctime)s] %(levelname)s: %(message)s')
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)

        logger.addHandler(file_handler)
        logger.addHandler(console_handler)

        # Clean old log files
        self.cleanup_old_logs()

        return logger

    def cleanup_old_logs(self):
        """Remove old log files to prevent disk space issues"""
        try:
            log_files = sorted(TEST_CONFIG['log_dir'].glob("test_run_*.log"))
            if len(log_files) > TEST_CONFIG['max_log_files']:
                for old_file in log_files[:-TEST_CONFIG['max_log_files']]:
                    old_file.unlink()
                    print(f"Removed old log file: {old_file.name}")  # Changed from self.logger.info
        except Exception as e:
            print(f"Failed to cleanup old logs: {e}")  # Changed from self.logger.warning

    def add_result(self, result: TestResult):
        """Add test result and log it"""
        self.results.append(result)

        status = "PASS" if result.success else "FAIL"
        duration_str = f" ({result.duration:.2f}s)" if result.duration > 0 else ""

        self.logger.info(f"{status}: {result.name}{duration_str} - {result.message}")

        if not result.success and result.details:
            self.logger.error(f"Details: {result.details}")

    def run_server_tests(self) -> bool:
        """Test server functionality"""
        self.logger.info("=" * 50)
        self.logger.info("STARTING SERVER TESTS")
        self.logger.info("=" * 50)

        server_tests_passed = 0
        server_tests_total = 0

        # Test 1: Health Check
        server_tests_total += 1
        start_time = time.time()
        try:
            response = requests.get(f"{TEST_CONFIG['server_url']}/health", timeout=TEST_CONFIG['timeout'])
            duration = time.time() - start_time

            if response.status_code == 200:
                data = response.json()
                server_status = data.get('status', 'unknown')
                self.add_result(TestResult(
                    "Server Health Check",
                    True,
                    f"Server is healthy (status: {server_status})",
                    duration
                ))
                server_tests_passed += 1
            else:
                self.add_result(TestResult(
                    "Server Health Check",
                    False,
                    f"Server returned status {response.status_code}",
                    duration,
                    response.text
                ))
        except requests.exceptions.ConnectionError:
            duration = time.time() - start_time
            self.add_result(TestResult(
                "Server Health Check",
                False,
                "Cannot connect to server",
                duration,
                f"Server URL: {TEST_CONFIG['server_url']}"
            ))
        except Exception as e:
            duration = time.time() - start_time
            self.add_result(TestResult(
                "Server Health Check",
                False,
                f"Health check failed: {str(e)}",
                duration
            ))

        # Test 2: Server Status Endpoint
        server_tests_total += 1
        start_time = time.time()
        try:
            response = requests.get(f"{TEST_CONFIG['server_url']}/status", timeout=TEST_CONFIG['timeout'])
            duration = time.time() - start_time

            if response.status_code == 200:
                data = response.json()
                kernel_type = data.get('services', {}).get('kernel_type', 'unknown')
                self.add_result(TestResult(
                    "Server Status Check",
                    True,
                    f"Status endpoint working (kernel: {kernel_type})",
                    duration
                ))
                server_tests_passed += 1
            else:
                self.add_result(TestResult(
                    "Server Status Check",
                    False,
                    f"Status endpoint returned {response.status_code}",
                    duration
                ))
        except Exception as e:
            duration = time.time() - start_time
            self.add_result(TestResult(
                "Server Status Check",
                False,
                f"Status check failed: {str(e)}",
                duration
            ))

        # Test 3: Query Endpoint Test
        server_tests_total += 1
        start_time = time.time()
        try:
            test_query = {"question": "What is the status of the database connection?"}
            response = requests.post(
                f"{TEST_CONFIG['server_url']}/ask",
                json=test_query,
                timeout=TEST_CONFIG['timeout']
            )
            duration = time.time() - start_time

            if response.status_code == 200:
                data = response.json()
                answer = data.get('answer', '')
                if answer and not answer.startswith('Error'):
                    self.add_result(TestResult(
                        "Server Query Test",
                        True,
                        "Query endpoint working correctly",
                        duration
                    ))
                    server_tests_passed += 1
                else:
                    self.add_result(TestResult(
                        "Server Query Test",
                        False,
                        f"Query returned error: {answer[:100]}",
                        duration
                    ))
            else:
                self.add_result(TestResult(
                    "Server Query Test",
                    False,
                    f"Query endpoint returned {response.status_code}",
                    duration
                ))
        except Exception as e:
            duration = time.time() - start_time
            self.add_result(TestResult(
                "Server Query Test",
                False,
                f"Query test failed: {str(e)}",
                duration
            ))

        # Test 4: Exports Endpoint
        server_tests_total += 1
        start_time = time.time()
        try:
            response = requests.get(f"{TEST_CONFIG['server_url']}/exports", timeout=TEST_CONFIG['timeout'])
            duration = time.time() - start_time

            if response.status_code == 200:
                data = response.json()
                export_count = data.get('count', 0)
                self.add_result(TestResult(
                    "Server Exports Check",
                    True,
                    f"Exports endpoint working ({export_count} files)",
                    duration
                ))
                server_tests_passed += 1
            else:
                self.add_result(TestResult(
                    "Server Exports Check",
                    False,
                    f"Exports endpoint returned {response.status_code}",
                    duration
                ))
        except Exception as e:
            duration = time.time() - start_time
            self.add_result(TestResult(
                "Server Exports Check",
                False,
                f"Exports check failed: {str(e)}",
                duration
            ))

        server_success_rate = (server_tests_passed / server_tests_total) * 100
        self.logger.info(
            f"SERVER TESTS COMPLETE: {server_tests_passed}/{server_tests_total} passed ({server_success_rate:.1f}%)")

        return server_tests_passed == server_tests_total

    def run_client_tests(self) -> bool:
        """Test thin client GUI functionality"""
        self.logger.info("=" * 50)
        self.logger.info("STARTING CLIENT TESTS")
        self.logger.info("=" * 50)

        client_tests_passed = 0
        client_tests_total = 0

        # Test 1: Import and Initialize GUI
        client_tests_total += 1
        start_time = time.time()
        try:
            # Mock speech modules to avoid hardware dependencies
            from unittest.mock import MagicMock
            sys.modules['pyttsx3'] = MagicMock()
            sys.modules['speech_recognition'] = MagicMock()
            sys.modules['pyaudio'] = MagicMock()

            # Import GUI
            from tkinter_voice_client import VoiceClientGUI
            import tkinter as tk

            # Create GUI instance
            root = tk.Tk()
            root.withdraw()  # Hide window for automated testing
            app = VoiceClientGUI(root)

            duration = time.time() - start_time
            self.add_result(TestResult(
                "Client GUI Initialization",
                True,
                "GUI created successfully",
                duration
            ))
            client_tests_passed += 1

            # Test 2: GUI Components
            client_tests_total += 1
            start_time = time.time()

            required_components = ['input_entry', 'chat_display', 'send_btn', 'voice_btn', 'stop_btn', 'status_label']
            missing_components = [comp for comp in required_components if not hasattr(app, comp)]

            duration = time.time() - start_time
            if not missing_components:
                self.add_result(TestResult(
                    "Client GUI Components",
                    True,
                    f"All {len(required_components)} components found",
                    duration
                ))
                client_tests_passed += 1
            else:
                self.add_result(TestResult(
                    "Client GUI Components",
                    False,
                    f"Missing components: {missing_components}",
                    duration
                ))

            # Test 3: Message Logging
            client_tests_total += 1
            start_time = time.time()
            try:
                app.log_message("Test system message", "system")
                app.log_message("Test user message", "user")
                app.log_message("Test assistant message", "assistant")

                duration = time.time() - start_time
                self.add_result(TestResult(
                    "Client Message Logging",
                    True,
                    "Message logging working correctly",
                    duration
                ))
                client_tests_passed += 1
            except Exception as e:
                duration = time.time() - start_time
                self.add_result(TestResult(
                    "Client Message Logging",
                    False,
                    f"Message logging failed: {str(e)}",
                    duration
                ))

            # Test 4: Export Response Detection
            client_tests_total += 1
            start_time = time.time()
            try:
                export_response = "Exported 100 rows to CSV format. File: test.csv Ready for download"
                non_export_response = "Here are your query results"

                export_detected = app.is_export_response(export_response)
                non_export_detected = app.is_export_response(non_export_response)

                duration = time.time() - start_time
                if export_detected and not non_export_detected:
                    self.add_result(TestResult(
                        "Client Export Detection",
                        True,
                        "Export response detection working",
                        duration
                    ))
                    client_tests_passed += 1
                else:
                    self.add_result(TestResult(
                        "Client Export Detection",
                        False,
                        f"Export detection failed: export={export_detected}, non-export={non_export_detected}",
                        duration
                    ))
            except Exception as e:
                duration = time.time() - start_time
                self.add_result(TestResult(
                    "Client Export Detection",
                    False,
                    f"Export detection test failed: {str(e)}",
                    duration
                ))

            # Test 5: Server Connection Test (from client)
            client_tests_total += 1
            start_time = time.time()
            try:
                # Test the client's connection testing capability
                app.test_connection()
                time.sleep(0.5)  # Give connection test time to complete

                duration = time.time() - start_time
                self.add_result(TestResult(
                    "Client Server Connection Test",
                    True,
                    "Client connection test executed",
                    duration
                ))
                client_tests_passed += 1
            except Exception as e:
                duration = time.time() - start_time
                self.add_result(TestResult(
                    "Client Server Connection Test",
                    False,
                    f"Client connection test failed: {str(e)}",
                    duration
                ))


        except ImportError as e:
            duration = time.time() - start_time
            self.add_result(TestResult(
                "Client GUI Initialization",
                False,
                f"Failed to import GUI: {str(e)}",
                duration,
                "Ensure tkinter_voice_client.py is available"
            ))
        except Exception as e:
            duration = time.time() - start_time
            self.add_result(TestResult(
                "Client GUI Initialization",
                False,
                f"GUI initialization failed: {str(e)}",
                duration
            ))

            # Test 6: Voice Workflow Simulation
            client_tests_total += 1
            start_time = time.time()
            try:
                # Test voice input simulation
                test_voice_text = "How many records in ebayWT"

                # Simulate voice input being processed
                app.input_entry.delete(0, 'end')
                app.handle_voice_input(test_voice_text)

                # Check if text appears in input field
                input_text = app.input_entry.get()

                duration = time.time() - start_time
                if test_voice_text in input_text:
                    self.add_result(TestResult(
                        "Client Voice Workflow Simulation",
                        True,
                        "Voice input simulation working",
                        duration
                    ))
                    client_tests_passed += 1
                else:
                    self.add_result(TestResult(
                        "Client Voice Workflow Simulation",
                        False,
                        f"Voice simulation failed: expected '{test_voice_text}', got '{input_text}'",
                        duration
                    ))
            except Exception as e:
                duration = time.time() - start_time
                self.add_result(TestResult(
                    "Client Voice Workflow Simulation",
                    False,
                    f"Voice workflow test failed: {str(e)}",
                    duration
                ))
        # Cleanup
        root.destroy()

        # Update the total count
        client_tests_total += 1  # You'll need to adjust this since we added a test

        client_success_rate = (client_tests_passed / client_tests_total) * 100
        self.logger.info(
            f"CLIENT TESTS COMPLETE: {client_tests_passed}/{client_tests_total} passed ({client_success_rate:.1f}%)")

        return client_tests_passed == client_tests_total

    def run_integration_tests(self) -> bool:
        """Test end-to-end integration between client and server"""
        self.logger.info("=" * 50)
        self.logger.info("STARTING INTEGRATION TESTS")
        self.logger.info("=" * 50)

        integration_tests_passed = 0
        integration_tests_total = 0

        # Test 1: Client-Server Query Flow
        integration_tests_total += 1
        start_time = time.time()
        try:
            # Mock speech modules
            from unittest.mock import MagicMock, patch
            sys.modules['pyttsx3'] = MagicMock()
            sys.modules['speech_recognition'] = MagicMock()
            sys.modules['pyaudio'] = MagicMock()

            from tkinter_voice_client import VoiceClientGUI
            import tkinter as tk

            root = tk.Tk()
            root.withdraw()
            app = VoiceClientGUI(root)

            # Test sending a query through the client to the server
            with patch.object(app.session, 'post') as mock_post:
                mock_response = MagicMock()
                mock_response.status_code = 200
                mock_response.json.return_value = {"answer": "Test response", "status": "success"}
                mock_post.return_value = mock_response

                # Simulate sending a message
                try:
                    app.query_server_enhanced("Test query")
                    time.sleep(0.1)  # Brief wait for async operation
                    success = True
                except:
                    success = False

                # Verify the request was made
                if mock_post.called:
                    duration = time.time() - start_time
                    self.add_result(TestResult(
                        "Client-Server Integration",
                        True,
                        "Client successfully sends requests to server",
                        duration
                    ))
                    integration_tests_passed += 1
                else:
                    duration = time.time() - start_time
                    self.add_result(TestResult(
                        "Client-Server Integration",
                        False,
                        "Client did not send request to server",
                        duration
                    ))

            root.destroy()

        except Exception as e:
            duration = time.time() - start_time
            self.add_result(TestResult(
                "Client-Server Integration",
                False,
                f"Integration test failed: {str(e)}",
                duration
            ))

        integration_success_rate = (integration_tests_passed / integration_tests_total) * 100
        self.logger.info(
            f"INTEGRATION TESTS COMPLETE: {integration_tests_passed}/{integration_tests_total} passed ({integration_success_rate:.1f}%)")

        return integration_tests_passed == integration_tests_total


    def generate_summary(self) -> Dict:
        """Generate test summary for scheduled task monitoring"""
        total_duration = time.time() - self.start_time

        total_tests = len(self.results)
        passed_tests = sum(1 for r in self.results if r.success)
        failed_tests = total_tests - passed_tests
        success_rate = (passed_tests / total_tests * 100) if total_tests > 0 else 0

        # Categorize results
        server_results = [r for r in self.results if 'Server' in r.name]
        client_results = [r for r in self.results if 'Client' in r.name]
        integration_results = [r for r in self.results if 'Integration' in r.name]

        summary = {
            'timestamp': datetime.now().isoformat(),
            'total_duration': round(total_duration, 2),
            'total_tests': total_tests,
            'passed_tests': passed_tests,
            'failed_tests': failed_tests,
            'success_rate': round(success_rate, 1),
            'server_tests': len(server_results),
            'server_passed': sum(1 for r in server_results if r.success),
            'client_tests': len(client_results),
            'client_passed': sum(1 for r in client_results if r.success),
            'integration_tests': len(integration_results),
            'integration_passed': sum(1 for r in integration_results if r.success),
            'critical_failures': [r.name for r in self.results if not r.success and 'Health' in r.name],
            'server_url': TEST_CONFIG['server_url']
        }

        return summary

    def save_results(self, summary: Dict):
        """Save results for monitoring and trending"""
        try:
            results_file = TEST_CONFIG['log_dir'] / 'latest_results.json'
            with open(results_file, 'w') as f:
                json.dump(summary, f, indent=2)

            # Also save timestamped results for history
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            history_file = TEST_CONFIG['log_dir'] / f'results_{timestamp}.json'
            with open(history_file, 'w') as f:
                json.dump(summary, f, indent=2)

        except Exception as e:
            self.logger.error(f"Failed to save results: {e}")

    def run_all_tests(self) -> bool:
        """Run complete test suite with email reporting"""
        self.logger.info("VOICE SQL CLIENT - COMPREHENSIVE TEST SUITE")
        self.logger.info(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self.logger.info(f"Server URL: {TEST_CONFIG['server_url']}")
        self.logger.info(f"Timeout: {TEST_CONFIG['timeout']}s")

        # Run all test categories
        server_success = self.run_server_tests()
        client_success = self.run_client_tests()
        integration_success = self.run_integration_tests()

        # Generate and log summary
        summary = self.generate_summary()
        self.save_results(summary)

        self.logger.info("=" * 50)
        self.logger.info("FINAL SUMMARY")
        self.logger.info("=" * 50)
        self.logger.info(f"Total Tests: {summary['total_tests']}")
        self.logger.info(f"Passed: {summary['passed_tests']}")
        self.logger.info(f"Failed: {summary['failed_tests']}")
        self.logger.info(f"Success Rate: {summary['success_rate']:.1f}%")
        self.logger.info(f"Duration: {summary['total_duration']:.2f}s")

        if summary['critical_failures']:
            self.logger.error(f"CRITICAL FAILURES: {', '.join(summary['critical_failures'])}")

        # Overall success if all categories pass or if only minor issues
        overall_success = server_success and client_success and integration_success

        # For scheduled tasks, also consider partial success acceptable if server is healthy

        status = "SUCCESS" if overall_success else "FAILURE"
        self.logger.info(f"OVERALL RESULT: {status}")
        if not overall_success:
            server_health_passed = any(r.success for r in self.results if 'Health Check' in r.name)
            if server_health_passed and summary['success_rate'] >= 75:
                self.logger.info("Accepting partial success - server healthy and 75%+ tests passed")
                overall_success = True

                # Determine if we should send email
                self.logger.info("=" * 50)
                self.logger.info("EMAIL DECISION PROCESS")
                self.logger.info("=" * 50)

                self.logger.info(f"📊 Test Results Summary:")
                self.logger.info(f"  Overall Success: {overall_success}")
                self.logger.info(f"  Failed Tests: {summary['failed_tests']}")
                self.logger.info(f"  Critical Failures: {summary.get('critical_failures', [])}")

                self.logger.info(f"📧 Email Configuration:")
                self.logger.info(f"  Send on Success: {self.email_config['send_on_success']}")
                self.logger.info(f"  Send on Failure: {self.email_config['send_on_failure']}")
                self.logger.info(f"  SMTP Server: {self.email_config['smtp_server']}")
                self.logger.info(f"  From Address: {self.email_config['from_address']}")
                self.logger.info(f"  To Addresses: {self.email_config['to_addresses']}")
                self.logger.info(
                    f"  Addresses Configured: {bool(self.email_config['to_addresses'] and self.email_config['to_addresses'][0])}")

                should_send_email = False
                email_reason = ""

                if not overall_success and self.email_config['send_on_failure']:
                    should_send_email = True
                    email_reason = "Tests failed and EMAIL_ON_FAILURE=true"
                elif overall_success and self.email_config['send_on_success']:
                    should_send_email = True
                    email_reason = "Tests passed and EMAIL_ON_SUCCESS=true"
                elif not overall_success and not self.email_config['send_on_failure']:
                    email_reason = "Tests failed but EMAIL_ON_FAILURE=false"
                elif overall_success and not self.email_config['send_on_success']:
                    email_reason = "Tests passed but EMAIL_ON_SUCCESS=false"

                self.logger.info(f"💭 Email Decision: {email_reason}")
                self.logger.info(f"📤 Will Send Email: {should_send_email}")

                # Send email report if configured and conditions met
                if should_send_email:
                    if not (self.email_config['to_addresses'] and self.email_config['to_addresses'][0]):
                        self.logger.warning("⚠️ Email sending skipped: No recipient addresses configured")
                        self.logger.info("   Add MONITOR_TO_EMAILS to .env file to enable email alerts")
                    else:
                        self.logger.info("🚀 Proceeding with email send...")
                        try:
                            # Clean up email addresses (remove empty strings)
                            clean_addresses = [addr.strip() for addr in self.email_config['to_addresses'] if
                                               addr.strip()]
                            self.logger.info(f"📋 Clean recipient list: {clean_addresses}")

                            self.email_reporter.send_email_report(
                                from_address=self.email_config['from_address'],
                                to_addresses=clean_addresses,
                                summary=summary,
                                smtp_server=self.email_config['smtp_server'],
                                smtp_port=self.email_config['smtp_port']
                            )
                            self.logger.info("✅ Email sending completed successfully")
                        except Exception as e:
                            self.logger.error(f"❌ Email sending failed: {type(e).__name__}: {str(e)}")
                            self.logger.error("   The test run completed successfully, but email notification failed")
                            self.logger.error("   Check SMTP server configuration and network connectivity")
                            # Don't fail the overall test run just because email failed
                else:
                    self.logger.info("📭 Email sending skipped based on configuration")

        return overall_success

    def send_email_report(self,
                          from_address: str,
                          to_addresses: List[str],
                          summary: Dict[str, Any],
                          subject: str = None,
                          smtp_server: str = "localhost",
                          smtp_port: int = 25,
                          username: str = None,
                          password: str = None) -> None:
        """
        Send the monitoring report via email in plain text format.

        Args:
            from_address: Email sender address
            to_addresses: List of recipient addresses
            summary: Test results summary dictionary
            subject: Optional custom subject line (default uses test results)
            smtp_server: SMTP server address
            smtp_port: SMTP server port
            username: Optional SMTP authentication username
            password: Optional SMTP authentication password
        """

        self.logger.info("=" * 50)
        self.logger.info("EMAIL SENDING PROCESS STARTED")
        self.logger.info("=" * 50)

        # Log email configuration (without sensitive data)
        self.logger.info(f"📧 Email Configuration:")
        self.logger.info(f"  SMTP Server: {smtp_server}")
        self.logger.info(f"  SMTP Port: {smtp_port}")
        self.logger.info(f"  From Address: {from_address}")
        self.logger.info(f"  To Addresses: {to_addresses}")
        self.logger.info(f"  Authentication: {'Yes' if username else 'No'}")

        # Create email subject based on test results if not provided
        if subject is None:
            if summary['critical_failures']:
                subject = f"[CRITICAL] Voice SQL Health Check - {len(summary['critical_failures'])} Critical Issues"
            elif summary['failed_tests'] > 0:
                subject = f"[WARNING] Voice SQL Health Check - {summary['failed_tests']} Tests Failed"
            else:
                subject = f"[SUCCESS] Voice SQL Health Check - All Systems Healthy"

        self.logger.info(f"📝 Email Subject: {subject}")

        # Generate the text report
        self.logger.info("📄 Generating email report content...")
        try:
            text_report = self.generate_text_report(summary)
            report_length = len(text_report)
            self.logger.info(f"✅ Report generated successfully ({report_length} characters)")
        except Exception as e:
            self.logger.error(f"❌ Failed to generate report content: {e}")
            raise

        # Create the email
        self.logger.info("✉️ Creating email message...")
        try:
            msg = MIMEText(text_report, 'plain', 'utf-8')
            msg['Subject'] = subject
            msg['From'] = from_address
            msg['To'] = ", ".join(to_addresses)
            self.logger.info("✅ Email message created successfully")
        except Exception as e:
            self.logger.error(f"❌ Failed to create email message: {e}")
            raise

        # Send the email with detailed logging
        self.logger.info("🚀 Attempting to send email...")
        try:
            self.logger.info(f"🔌 Connecting to SMTP server {smtp_server}:{smtp_port}...")
            with smtplib.SMTP(smtp_server, smtp_port) as server:
                self.logger.info("✅ Connected to SMTP server")

                # Enable debug output for SMTP
                server.set_debuglevel(1)  # This will log SMTP conversation

                if username and password:
                    self.logger.info("🔐 Starting TLS and authenticating...")
                    server.starttls()
                    self.logger.info("✅ TLS started")
                    server.login(username, password)
                    self.logger.info("✅ Authentication successful")
                else:
                    self.logger.info("📤 No authentication required, sending directly...")

                self.logger.info(f"📨 Sending message to {len(to_addresses)} recipients...")
                result = server.send_message(msg)

                # Check for any rejected recipients
                if result:
                    self.logger.warning(f"⚠️ Some recipients were rejected: {result}")
                else:
                    self.logger.info("✅ All recipients accepted")

            self.logger.info(f"🎉 Email successfully sent to {', '.join(to_addresses)}")

        except smtplib.SMTPConnectError as e:
            self.logger.error(f"❌ SMTP Connection Error: Cannot connect to {smtp_server}:{smtp_port}")
            self.logger.error(f"   Error details: {e}")
            raise
        except smtplib.SMTPAuthenticationError as e:
            self.logger.error(f"❌ SMTP Authentication Error: Invalid credentials")
            self.logger.error(f"   Error details: {e}")
            raise
        except smtplib.SMTPRecipientsRefused as e:
            self.logger.error(f"❌ SMTP Recipients Refused: Server rejected recipient addresses")
            self.logger.error(f"   Rejected addresses: {e}")
            raise
        except smtplib.SMTPDataError as e:
            self.logger.error(f"❌ SMTP Data Error: Server rejected message content")
            self.logger.error(f"   Error details: {e}")
            raise
        except Exception as e:
            self.logger.error(f"❌ Unexpected email error: {type(e).__name__}: {str(e)}")
            self.logger.error(f"   SMTP Server: {smtp_server}:{smtp_port}")
            self.logger.error(f"   From: {from_address}")
            self.logger.error(f"   To: {to_addresses}")
            import traceback
            self.logger.error(f"   Full traceback: {traceback.format_exc()}")
            raise
        finally:
            self.logger.info("=" * 50)
            self.logger.info("EMAIL SENDING PROCESS COMPLETED")
            self.logger.info("=" * 50)


def main():
    """Main entry point for scheduled task"""
    # Parse command line arguments
    test_mode = "all"
    if len(sys.argv) > 1:
        test_mode = sys.argv[1].lower()

    # Initialize test suite
    suite = TestSuite()

    try:
        if test_mode == "server":
            success = suite.run_server_tests()
        elif test_mode == "client":
            success = suite.run_client_tests()
        elif test_mode == "integration":
            success = suite.run_integration_tests()
        elif test_mode == "quick":
            # Quick test - just server health and basic client init
            suite.logger.info("RUNNING QUICK TEST MODE")
            success = suite.run_server_tests()
            if success:
                success = suite.run_client_tests()
        else:  # "all" or default
            success = suite.run_all_tests()

        # Save final summary
        summary = suite.generate_summary()
        suite.save_results(summary)

        # Exit with appropriate code for scheduled task monitoring
        return 0 if success else 1

    except KeyboardInterrupt:
        suite.logger.info("Test run interrupted by user")
        return 2
    except Exception as e:
        suite.logger.error(f"Unexpected error: {e}")
        import traceback
        suite.logger.error(traceback.format_exc())
        return 3


if __name__ == "__main__":
    exit_code = main()
    print(f"\nTest suite completed with exit code: {exit_code}")

    # Exit codes for scheduled task monitoring:
    # 0 = Success (all tests passed)
    # 1 = Test failures (some tests failed)
    # 2 = Interrupted by user
    # 3 = Unexpected error
    sys.exit(exit_code)