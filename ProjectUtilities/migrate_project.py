#!/usr/bin/env python3
"""
migrate_project.py - Reorganize Voice SQL Client project structure

This script will reorganize your project into a proper Python project structure
with separate folders for source, tests, build scripts, and documentation.
"""

import os
import shutil
import sys
from pathlib import Path
from datetime import datetime


def backup_project():
    """Create a backup of the current project"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = f"backup_{timestamp}"

    print(f"📦 Creating backup: {backup_dir}/")

    # Create backup directory
    Path(backup_dir).mkdir(exist_ok=True)

    # Files to backup
    files_to_backup = [
        "tkinter_voice_client.py",
        "test_gui_client.py",
        "run_tests.py",
        "build_executable.py",
        "setup_credentials.py",
        "server_api.py",
        "README.md"
    ]

    # Directories to backup
    dirs_to_backup = ["src"]

    # Backup files
    for file in files_to_backup:
        if os.path.exists(file):
            shutil.copy2(file, backup_dir)
            print(f"  ✅ Backed up {file}")

    # Backup directories
    for dir_name in dirs_to_backup:
        if os.path.exists(dir_name):
            shutil.copytree(dir_name, Path(backup_dir) / dir_name)
            print(f"  ✅ Backed up {dir_name}/")

    print(f"✅ Backup complete: {backup_dir}/")
    return backup_dir


def create_directory_structure():
    """Create the new directory structure"""
    print("\n📁 Creating new directory structure...")

    directories = [
        'src/gui',
        'src/core',
        'src/utils',
        'src/database',
        'tests/fixtures',
        'build/assets',
        'docs',
        'scripts',
        'config',
        'dist/laptop_deployment'
    ]

    for directory in directories:
        Path(directory).mkdir(parents=True, exist_ok=True)
        print(f"  📁 Created {directory}/")

        # Create __init__.py files for Python packages
        if directory.startswith('src/') or directory == 'tests':
            init_file = Path(directory) / '__init__.py'
            if not init_file.exists():
                init_file.touch()
                print(f"    📄 Created {init_file}")


def migrate_existing_files():
    """Move existing files to their new locations"""
    print("\n🚚 Migrating existing files...")

    file_migrations = [
        # Source files
        ('tkinter_voice_client.py', 'src/gui/main_window.py'),

        # Test files
        ('test_gui_client.py', 'tests/test_gui.py'),
        ('run_tests.py', 'tests/run_tests.py'),

        # Build files
        ('build_executable.py', 'build/build_executable.py'),

        # Scripts
        ('setup_credentials.py', 'scripts/setup_credentials.py'),

        # Keep server API in root for now (it's separate from client)
        # ('server_api.py', 'src/server/api.py'),  # Uncomment if you want to include server
    ]

    for old_path, new_path in file_migrations:
        if os.path.exists(old_path):
            # Ensure destination directory exists
            Path(new_path).parent.mkdir(parents=True, exist_ok=True)

            print(f"  📄 Moving {old_path} → {new_path}")
            shutil.move(old_path, new_path)
        else:
            print(f"  ⚠️  {old_path} not found, skipping")

    # Handle existing src directory specially
    if os.path.exists('src') and os.path.isdir('src'):
        print("  📁 Migrating existing src/ to src/database/")

        # Move contents of old src to database subdirectory
        old_src_contents = list(Path('src').iterdir())

        for item in old_src_contents:
            if item.name != 'database':  # Don't move the database dir we just created
                dest = Path('src/database') / item.name
                print(f"    📄 Moving {item} → {dest}")
                shutil.move(str(item), str(dest))


def update_main_window_imports():
    """Update imports in the moved main window file"""
    main_window_file = Path('src/gui/main_window.py')

    if not main_window_file.exists():
        return

    print("\n🔧 Updating imports in main_window.py...")

    with open(main_window_file, 'r') as f:
        content = f.read()

    # Update imports to use relative imports
    import_replacements = [
        ('from src.database', 'from ..database'),
        ('from src.kernel', 'from ..database.kernel'),  # Adjust as needed
        ('from src.speech', 'from ..database.speech'),  # Adjust as needed
        ('from src.plugins', 'from ..database.plugins'),  # Adjust as needed
    ]

    for old_import, new_import in import_replacements:
        if old_import in content:
            content = content.replace(old_import, new_import)
            print(f"  ✅ Updated: {old_import} → {new_import}")

    # Write updated content
    with open(main_window_file, 'w') as f:
        f.write(content)


def update_test_imports():
    """Update imports in test files"""
    test_gui_file = Path('tests/test_gui.py')

    if not test_gui_file.exists():
        return

    print("\n🔧 Updating imports in test_gui.py...")

    with open(test_gui_file, 'r') as f:
        content = f.read()

    # Update imports to use src package
    import_replacements = [
        ('from tkinter_voice_client import VoiceClientGUI', 'from src.gui.main_window import VoiceClientGUI'),
        ('import tkinter_voice_client', 'from src.gui import main_window'),
    ]

    for old_import, new_import in import_replacements:
        if old_import in content:
            content = content.replace(old_import, new_import)
            print(f"  ✅ Updated: {old_import} → {new_import}")

    # Write updated content
    with open(test_gui_file, 'w') as f:
        f.write(content)


def create_new_files():
    """Create new organizational files"""
    print("\n📄 Creating new project files...")

    # New main entry point
    main_py_content = '''#!/usr/bin/env python3
"""
Voice SQL Client - Main Entry Point

Usage:
    python main.py              # Start GUI application
    python main.py --test       # Run quick test
    python main.py --help       # Show help
"""

import sys
import os
import argparse
from pathlib import Path

# Add src to Python path
project_root = Path(__file__).parent
src_path = project_root / 'src'
sys.path.insert(0, str(src_path))

def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description='Voice SQL Client')
    parser.add_argument('--test', action='store_true', help='Run quick functionality test')
    parser.add_argument('--debug', action='store_true', help='Enable debug mode')

    args = parser.parse_args()

    if args.test:
        # Run quick test
        from tests.run_tests import run_quick_test
        print("🧪 Running quick test...")
        success = run_quick_test()
        sys.exit(0 if success else 1)

    # Start GUI application
    try:
        from gui.main_window import main as gui_main
        gui_main()
    except ImportError as e:
        print(f"❌ Import error: {e}")
        print("Make sure all dependencies are installed: pip install -r requirements.txt")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Application error: {e}")
        if args.debug:
            raise
        sys.exit(1)

if __name__ == "__main__":
    main()
'''

    # Requirements file
    requirements_content = '''# Voice SQL Client Dependencies

# Core GUI and networking
requests>=2.25.0

# Optional: Enhanced tooltips (if used)
# tkinter-tooltip>=2.1.0

# Optional: Speech dependencies (comment out if not needed)
# pyttsx3>=2.90
# SpeechRecognition>=3.8.1  
# pyaudio>=0.2.11

# Development and testing
pytest>=6.0.0
pytest-cov>=2.10.0
pytest-mock>=3.3.0

# Building executables
pyinstaller>=4.0

# Database connectivity (if needed)
# pyodbc>=4.0.30

# Encryption for credentials
cryptography>=3.0.0

# Additional utilities
python-dotenv>=0.19.0
pathlib2>=2.3.0; python_version < "3.4"
'''

    # Project README
    readme_content = '''# Voice SQL Client

A desktop GUI application for natural language database queries with optional voice support.

## Features

- 🗣️ Natural language database queries
- 🎤 Voice input support (optional)
- 🔊 Text-to-speech responses (optional)  
- 📊 Export results to CSV/TXT
- 🔒 Secure credential management
- 🧪 Built-in testing capabilities
- 📦 Standalone executable deployment

## Quick Start

### Prerequisites
- Python 3.7 or higher
- Windows 10+ (for full speech features)

### Installation
```bash
# Clone or download the project
cd voice_sql_client

# Install dependencies
pip install -r requirements.txt

# Run the application
python main.py
```

### Configuration
```bash
# Set up database credentials (one time)
python scripts/setup_credentials.py

# Set server URL (optional)
export VOICE_SQL_SERVER="http://your-server:8000"
```

## Development

### Project Structure
```
voice_sql_client/
├── src/             # Source code
│   ├── gui/         # GUI components
│   ├── core/        # Business logic  
│   ├── utils/       # Utilities
│   └── database/    # Database components
├── tests/           # Test suite
├── build/           # Build scripts
├── docs/            # Documentation
└── scripts/         # Utility scripts
```

### Running Tests
```bash
# All tests
python -m pytest tests/

# Quick test
python main.py --test

# GUI tests only
python -m pytest tests/test_gui.py

# With coverage
python -m pytest tests/ --cov=src
```

### Building for Deployment
```bash
# Build standalone executable
python build/build_executable.py

# Windows batch build
build/build_for_laptop.bat
```

## Deployment

### Laptop Deployment (Locked-Down Systems)
1. Build the executable: `python build/build_executable.py`
2. Copy `dist/laptop_deployment/` to target machine
3. Run `VoiceSQL_Client.exe`

### Server Requirements
- Voice SQL API server running on network
- Database connectivity from client machine
- Network access to server port (default: 8000)

## Configuration

### Environment Variables
- `VOICE_SQL_SERVER` - Server URL (default: http://BI-SQL001:8000)
- `DB_USERNAME` - Database username
- `DB_PASSWORD` - Database password  
- `DEBUG` - Enable debug mode

### Configuration Files
- `config/default.yaml` - Default settings
- `config/development.yaml` - Development overrides
- `config/production.yaml` - Production settings

## Troubleshooting

### Common Issues
- **Import errors**: Install requirements `pip install -r requirements.txt`
- **Speech not working**: Install optional speech dependencies
- **Server connection fails**: Check server URL and network connectivity
- **Database errors**: Verify credentials with `python scripts/setup_credentials.py`

### Getting Help
1. Check the logs in `C:/Logs/VoiceSQL/` (Windows)
2. Run with debug: `python main.py --debug`
3. Test connectivity: `python main.py --test`

## License

Internal use only - [Your Organization]
'''

    # Git ignore
    gitignore_content = '''# Byte-compiled / optimized / DLL files
__pycache__/
*.py[cod]
*$py.class

# C extensions
*.so

# Distribution / packaging
.Python
build/
develop-eggs/
dist/
downloads/
eggs/
.eggs/
lib/
lib64/
parts/
sdist/
var/
wheels/
*.egg-info/
.installed.cfg
*.egg
MANIFEST

# PyInstaller
*.manifest
*.spec

# Unit test / coverage reports
htmlcov/
.tox/
.nox/
.coverage
.coverage.*
.cache
nosetests.xml
coverage.xml
*.cover
.hypothesis/
.pytest_cache/

# Virtual environments
.env
.venv
env/
venv/
ENV/
env.bak/
venv.bak/

# IDEs
.vscode/
.idea/
*.swp
*.swo
*~

# OS
.DS_Store
.DS_Store?
._*
.Spotlight-V100
.Trashes
ehthumbs.db
Thumbs.db

# Project specific
db_creds.enc
db.key
*.log
temp/
tmp/

# Build artifacts
dist/
build/
*.exe
*.msi

# Backup files
backup_*/
'''

    # Environment template
    env_example_content = '''# Voice SQL Client Environment Variables
# Copy this file to .env and customize for your environment

# Server Configuration
VOICE_SQL_SERVER=http://BI-SQL001:8000

# Database Configuration (optional - can use credential storage instead)
# DB_USERNAME=your_username
# DB_PASSWORD=your_password
SQL_SERVER_NAME=BI-SQL001
SQL_DATABASE_NAME=CRPAF

# Speech Service Configuration (optional)
# SPEECH_SERVICE_ID=your_speech_service_id
# AZURE_LOCATION=your_azure_region
# AZURE_OPENAI_ENDPOINT=your_openai_endpoint
# AZURE_OPENAI_CHAT_DEPLOYMENT_NAME=your_deployment_name

# Development Settings
DEBUG=false
LOG_LEVEL=INFO

# Server Settings (for running server component)
SERVER_HOST=0.0.0.0
SERVER_PORT=8000
'''

    # Pytest configuration
    pytest_config_content = '''"""
Pytest configuration for Voice SQL Client tests
"""

import pytest
import sys
from pathlib import Path

# Add src to path for imports
project_root = Path(__file__).parent.parent
src_path = project_root / 'src'
sys.path.insert(0, str(src_path))

@pytest.fixture
def mock_server_response():
    """Mock server response for testing"""
    return {
        "answer": "Test response from server",
        "status": "success"
    }

@pytest.fixture  
def sample_export_response():
    """Sample export response for testing"""
    return "Exported 100 rows to CSV format. File: query_export_20241201_120000.csv Ready for download from server."
'''

    # Write all files
    files_to_create = {
        'main.py': main_py_content,
        'requirements.txt': requirements_content,
        'README.md': readme_content,
        '.gitignore': gitignore_content,
        '.env.example': env_example_content,
        'tests/conftest.py': pytest_config_content,
    }

    for filepath, content in files_to_create.items():
        file_path = Path(filepath)
        file_path.parent.mkdir(parents=True, exist_ok=True)

        with open(file_path, 'w') as f:
            f.write(content)
        print(f"  ✅ Created {filepath}")


def create_pycharm_config():
    """Create PyCharm configuration suggestions"""
    pycharm_config = '''
# PyCharm Configuration Instructions

After running this migration, configure PyCharm:

## 1. Mark Directories
Right-click on directories and mark as:
- `src/` → Mark Directory as → Sources Root
- `tests/` → Mark Directory as → Test Sources Root
- `build/` → Mark Directory as → Excluded
- `dist/` → Mark Directory as → Excluded
- `__pycache__/` → Mark Directory as → Excluded

## 2. Run Configurations

### Main Application
- Name: Voice SQL Client
- Script path: main.py
- Working directory: [project root]
- Environment variables: (add any needed)

### Tests
- Name: All Tests  
- Target type: Module name
- Target: tests
- Working directory: [project root]

### Quick Test
- Name: Quick Test
- Script path: main.py
- Parameters: --test
- Working directory: [project root]

### Build Executable
- Name: Build for Laptop
- Script path: build/build_executable.py
- Working directory: [project root]

## 3. Project Settings
- File → Settings → Project → Python Interpreter
- Ensure correct Python interpreter is selected
- Add `src/` to PYTHONPATH if needed

## 4. Code Style
- File → Settings → Editor → Code Style → Python
- Set line length to 88 (Black formatter compatible)
- Enable automatic import organization
'''

    with open('docs/pycharm_setup.md', 'w') as f:
        f.write(pycharm_config)
    print(f"  ✅ Created docs/pycharm_setup.md")


def print_summary(backup_dir):
    """Print migration summary"""
    print("\n" + "=" * 60)
    print("🎉 PROJECT MIGRATION COMPLETE!")
    print("=" * 60)

    print(f"\n📦 Backup created: {backup_dir}/")
    print("\n📁 New project structure:")
    print("├── main.py                 # New entry point")
    print("├── requirements.txt        # Dependencies")
    print("├── README.md              # Project documentation")
    print("├── src/                   # Source code")
    print("│   ├── gui/               # GUI components")
    print("│   ├── database/          # Database code (your existing src/)")
    print("│   ├── core/              # Business logic")
    print("│   └── utils/             # Utilities")
    print("├── tests/                 # Test suite")
    print("├── build/                 # Build scripts")
    print("├── docs/                  # Documentation")
    print("└── scripts/               # Utility scripts")

    print("\n🚀 Next Steps:")
    print("1. Review the new structure")
    print("2. Configure PyCharm (see docs/pycharm_setup.md)")
    print("3. Test the application: python main.py")
    print("4. Run tests: python -m pytest tests/")
    print("5. Install requirements: pip install -r requirements.txt")
    print("6. Build executable: python build/build_executable.py")