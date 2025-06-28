# setup_credentials.py - Script to securely store database credentials

import os
import getpass
import sys
from pathlib import Path

# Add the src directory to path so we can import our modules
sys.path.append(str(Path(__file__).parent / "src"))

try:
    from database.secure_service import store_database_credentials, get_database_credentials, create_database_service
except ImportError as e:
    print(f"Error importing secure_service: {e}")
    print("Make sure you have the src/database/secure_service.py file")
    sys.exit(1)


def setup_credentials():
    """Interactive script to set up database credentials"""

    print("=== Voice SQL Database Credential Setup ===")
    print()

    # Check if credentials already exist
    existing_username, existing_password = get_database_credentials()
    if existing_username:
        print(f"Existing credentials found for user: {existing_username}")
        response = input("Do you want to update them? (y/N): ").lower()
        if response != 'y':
            print("Keeping existing credentials.")
            return

    print("Setting up database credentials for read-only access...")
    print()

    # Get server details
    server_name = input(f"SQL Server name (default: BI-SQL001): ").strip()
    if not server_name:
        server_name = "BI-SQL001"

    database_name = input(f"Database name (default: CRPAF): ").strip()
    if not database_name:
        database_name = "CRPAF"

    # Get credentials
    print()
    print("Enter your read-only database credentials:")
    username = input("Username (e.g., CRPreadonly_user): ").strip()
    if not username:
        print("Username is required!")
        return

    password = getpass.getpass("Password (hidden): ")
    if not password:
        print("Password is required!")
        return

    # Confirm password
    password_confirm = getpass.getpass("Confirm password (hidden): ")
    if password != password_confirm:
        print("Passwords don't match!")
        return

    try:
        # Test the connection first
        print("\nTesting database connection...")
        from database.secure_service import SecureDatabase

        test_db = SecureDatabase(
            server_name=server_name,
            database_name=database_name,
            username=username,
            password=password
        )

        if test_db.test_connection():
            print("✅ Connection successful!")

            # Store credentials
            store_database_credentials(username, password)
            print("✅ Credentials stored securely!")

            # Set environment variables for this session
            os.environ['DB_USERNAME'] = username
            os.environ['DB_PASSWORD'] = password
            os.environ['SQL_SERVER_NAME'] = server_name
            os.environ['SQL_DATABASE_NAME'] = database_name

            print("\n✅ Setup complete!")
            print("\nNext steps:")
            print("1. Restart your server: Stop and start the scheduled task")
            print("   Stop-ScheduledTask -TaskName 'VoiceSQL API Server'")
            print("   Start-ScheduledTask -TaskName 'VoiceSQL API Server'")
            print("2. Test connection: curl http://localhost:8000/health")
            print("3. Launch the client: python enhanced_tkinter_voice_client.py")

        else:
            print("❌ Connection failed! Please check your credentials and try again.")
            print("Make sure:")
            print("- Username and password are correct")
            print("- CRPreadonly_user has proper permissions")
            print("- Network connectivity to BI-SQL001")

    except Exception as e:
        print(f"❌ Error testing connection: {e}")
        print("Please verify your credentials and network connectivity.")


def show_credential_status():
    """Show current credential status"""

    print("=== Current Database Credential Status ===")
    print()

    username, password = get_database_credentials()

    if username:
        print(f"✅ Credentials configured for user: {username}")

        # Test connection
        try:
            db = create_database_service()
            if db.test_connection():
                print("✅ Database connection: Working")
            else:
                print("❌ Database connection: Failed")
        except Exception as e:
            print(f"❌ Database connection: Error - {e}")
    else:
        print("❌ No credentials configured")
        print("Run: python setup_credentials.py")

    print()
    print("Environment variables:")
    print(f"  SQL_SERVER_NAME: {os.getenv('SQL_SERVER_NAME', 'Not set')}")
    print(f"  SQL_DATABASE_NAME: {os.getenv('SQL_DATABASE_NAME', 'Not set')}")
    print(f"  DB_USERNAME: {os.getenv('DB_USERNAME', 'Not set')}")
    print(f"  DB_PASSWORD: {'Set' if os.getenv('DB_PASSWORD') else 'Not set'}")


def create_env_file():
    """Create a .env file with database settings"""

    print("=== Creating .env file ===")

    username, password = get_database_credentials()
    if not username:
        print("❌ No credentials found. Run setup_credentials.py first.")
        return

    server_name = os.getenv('SQL_SERVER_NAME', 'BI-SQL001')
    database_name = os.getenv('SQL_DATABASE_NAME', 'CRPAF')

    env_content = f"""# Voice SQL Database Configuration
SQL_SERVER_NAME={server_name}
SQL_DATABASE_NAME={database_name}
DB_USERNAME={username}
DB_PASSWORD={password}

# Speech Service Configuration (optional)
SPEECH_SERVICE_ID=your_speech_service_id
AZURE_LOCATION=your_azure_region
AZURE_OPENAI_ENDPOINT=your_openai_endpoint
AZURE_OPENAI_CHAT_DEPLOYMENT_NAME=your_deployment_name
"""

    with open('.env', 'w') as f:
        f.write(env_content)

    print("✅ .env file created successfully!")
    print("⚠️  Remember to add .env to your .gitignore file!")


def test_current_setup():
    """Test the current credential setup"""
    print("=== Testing Current Setup ===")
    print()

    try:
        # Test credentials
        username, password = get_database_credentials()
        if not username:
            print("❌ No credentials found")
            return

        print(f"Testing connection with user: {username}")

        # Test database connection
        db = create_database_service()
        if db.test_connection():
            print("✅ Database connection successful")

            # Test a simple query
            result = db.query(
                "SELECT COUNT(*) as table_count FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_TYPE = 'BASE TABLE'")
            if result and not isinstance(result, str):
                count = result[0][0]
                print(f"✅ Query test successful: {count} tables found")
            else:
                print(f"⚠️  Query test issue: {result}")
        else:
            print("❌ Database connection failed")

    except Exception as e:
        print(f"❌ Test failed: {e}")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        if sys.argv[1] == "status":
            show_credential_status()
        elif sys.argv[1] == "env":
            create_env_file()
        elif sys.argv[1] == "test":
            test_current_setup()
        else:
            print("Usage:")
            print("  python setup_credentials.py        # Setup credentials")
            print("  python setup_credentials.py status # Show current status")
            print("  python setup_credentials.py test   # Test current setup")
            print("  python setup_credentials.py env    # Create .env file")
    else:
        setup_credentials()