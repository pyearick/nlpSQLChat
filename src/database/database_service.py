# secure_database_service.py - Enhanced database service with authentication

import logging
import pyodbc
import os
from faker import Faker
from cryptography.fernet import Fernet
import base64
from .utils import table_exists, create_table, insert_record

logger = logging.getLogger(__name__)


class SecureDatabase:
    def __init__(self, server_name: str, database_name: str, username: str = None, password: str = None) -> None:
        self.server_name = server_name
        self.database_name = database_name
        self.username = username
        self.password = password
        self.conn = None
        self.setup_connection()

    def setup_connection(self) -> None:
        """Setup database connection with proper authentication"""
        if self.username and self.password:
            # Use SQL Server authentication with read-only user
            connection_string = (
                "DRIVER={ODBC Driver 17 for SQL Server};"
                f"SERVER={self.server_name};"
                f"DATABASE={self.database_name};"
                f"UID={self.username};"
                f"PWD={self.password};"
                "Encrypt=yes;"
                "TrustServerCertificate=yes;"
                "Connection Timeout=30;"
            )
        else:
            # Fallback to trusted connection (for backwards compatibility)
            connection_string = (
                "DRIVER={ODBC Driver 17 for SQL Server};"
                f"SERVER={self.server_name};"
                f"DATABASE={self.database_name};"
                "Trusted_Connection=yes;"
            )

        try:
            self.conn = pyodbc.connect(connection_string)
            logger.info(f"Connected to database {self.database_name} on {self.server_name}")
            if self.username:
                logger.info(f"Using SQL authentication with user: {self.username}")
            else:
                logger.info("Using Windows integrated authentication")
        except Exception as e:
            logger.error(f"Failed to connect to database: {e}")
            raise

    def setup(self) -> None:
        """Setup database (only for development - read-only user can't create tables)"""
        if not self.username:  # Only allow setup with trusted connection
            logger.debug("Setting up the database.")
            cursor = self.conn.cursor()

            if table_exists(cursor):
                return

            logger.debug("Creating table.")
            create_table(cursor)

            fake = Faker()
            logger.debug("Generating and inserting records.")

            for i in range(1000):
                insert_record(cursor, i, fake)

            self.conn.commit()
            logger.debug("Database setup completed.")
        else:
            logger.info("Skipping database setup - using read-only user")

    def query(self, query: str) -> list:
        """Execute read-only query"""
        cursor = self.conn.cursor()
        try:
            logger.debug(f"Querying database with: {query}")

            # Security check - ensure only SELECT statements
            query_upper = query.strip().upper()
            if not query_upper.startswith('SELECT') and not query_upper.startswith('WITH'):
                if 'INSERT' in query_upper or 'UPDATE' in query_upper or 'DELETE' in query_upper or 'DROP' in query_upper:
                    logger.warning(f"Rejected non-SELECT query: {query}")
                    return "Error: Only SELECT queries are allowed"

            cursor.execute(query)
            result = cursor.fetchall()
            logger.debug(f"Successfully queried database: {len(result) if result else 0} rows returned")
            return result

        except Exception as ex:
            logger.error(f"Error querying database: {ex}")
            return f"Database Error: {str(ex)}"
        finally:
            cursor.close()

    def test_connection(self) -> bool:
        """Test database connection"""
        try:
            cursor = self.conn.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
            cursor.close()
            return True
        except Exception as e:
            logger.error(f"Connection test failed: {e}")
            return False


class PasswordManager:
    """Simple password encryption/decryption for stored credentials"""

    def __init__(self, key_file: str = "db.key"):
        self.key_file = key_file
        self.key = self._get_or_create_key()
        self.cipher = Fernet(self.key)

    def _get_or_create_key(self) -> bytes:
        """Get existing key or create new one"""
        if os.path.exists(self.key_file):
            with open(self.key_file, 'rb') as f:
                return f.read()
        else:
            # Create new key
            key = Fernet.generate_key()
            with open(self.key_file, 'wb') as f:
                f.write(key)
            # Set restrictive permissions on Windows
            try:
                import stat
                os.chmod(self.key_file, stat.S_IRUSR | stat.S_IWUSR)  # Owner read/write only
            except:
                pass
            return key

    def encrypt_password(self, password: str) -> str:
        """Encrypt password and return base64 encoded string"""
        encrypted = self.cipher.encrypt(password.encode())
        return base64.b64encode(encrypted).decode()

    def decrypt_password(self, encrypted_password: str) -> str:
        """Decrypt base64 encoded password"""
        encrypted_bytes = base64.b64decode(encrypted_password.encode())
        decrypted = self.cipher.decrypt(encrypted_bytes)
        return decrypted.decode()


def get_database_credentials():
    """Get database credentials from environment or encrypted storage"""

    # Method 1: Environment variables (recommended for production)
    username = os.getenv('DB_USERNAME')
    password = os.getenv('DB_PASSWORD')

    if username and password:
        logger.info("Using credentials from environment variables")
        return username, password

    # Method 2: Encrypted storage file
    creds_file = "db_creds.enc"
    if os.path.exists(creds_file):
        try:
            pm = PasswordManager()
            with open(creds_file, 'r') as f:
                lines = f.read().strip().split('\n')
                username = lines[0]
                encrypted_password = lines[1]
                password = pm.decrypt_password(encrypted_password)
            logger.info("Using credentials from encrypted storage")
            return username, password
        except Exception as e:
            logger.error(f"Failed to load encrypted credentials: {e}")

    # Method 3: Fallback to None (use trusted connection)
    logger.info("No stored credentials found, using trusted connection")
    return None, None


def store_database_credentials(username: str, password: str):
    """Store database credentials securely"""

    # Store in encrypted file
    pm = PasswordManager()
    encrypted_password = pm.encrypt_password(password)

    creds_file = "db_creds.enc"
    with open(creds_file, 'w') as f:
        f.write(f"{username}\n{encrypted_password}")

    # Set restrictive permissions
    try:
        import stat
        os.chmod(creds_file, stat.S_IRUSR | stat.S_IWUSR)  # Owner read/write only
    except:
        pass

    logger.info(f"Credentials stored securely for user: {username}")


# Updated database factory function
def create_database_service(server_name: str = None, database_name: str = None):
    """Create database service with proper authentication"""

    # Default values
    server_name = server_name or os.getenv("SQL_SERVER_NAME", "BI-SQL001")
    database_name = database_name or os.getenv("SQL_DATABASE_NAME", "CRPAF")

    # Get credentials
    username, password = get_database_credentials()

    # Create and return database service
    return SecureDatabase(
        server_name=server_name,
        database_name=database_name,
        username=username,
        password=password
    )