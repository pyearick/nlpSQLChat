# build_for_laptop.py - Simple build script for laptop deployment

import os
import sys
import subprocess
import shutil
from pathlib import Path
from datetime import datetime


def check_pyinstaller():
    """Check if PyInstaller is available"""
    try:
        import PyInstaller
        print(f"✅ PyInstaller {PyInstaller.__version__} found")
        return True
    except ImportError:
        print("❌ PyInstaller not found. Installing...")
        try:
            subprocess.run([sys.executable, "-m", "pip", "install", "pyinstaller"], check=True)
            print("✅ PyInstaller installed successfully")
            return True
        except subprocess.CalledProcessError:
            print("❌ Failed to install PyInstaller")
            return False


def clean_previous_builds():
    """Clean previous build artifacts"""
    print("🧹 Cleaning previous builds...")

    dirs_to_clean = ['build', 'dist', '__pycache__']
    files_to_clean = ['*.spec']

    for dir_name in dirs_to_clean:
        if os.path.exists(dir_name):
            shutil.rmtree(dir_name)
            print(f"  🗑️ Removed {dir_name}/")

    # Remove spec files
    for spec_file in Path('.').glob('*.spec'):
        spec_file.unlink()
        print(f"  🗑️ Removed {spec_file}")


def build_executable():
    """Build the executable"""
    print("\n🔨 Building executable...")

    # PyInstaller command
    cmd = [
        'pyinstaller',
        '--onefile',  # Single file
        '--windowed',  # No console window
        '--name=VoiceSQL_Client',  # Executable name
        '--clean',  # Clean build
        '--noconfirm',  # Overwrite without asking

        # Include test files for laptop testing
        '--add-data=test_gui_client.py;.',
        '--add-data=run_tests.py;.',

        # Hidden imports
        '--hidden-import=tkinter',
        '--hidden-import=tkinter.ttk',
        '--hidden-import=tkinter.scrolledtext',
        '--hidden-import=tkinter.messagebox',
        '--hidden-import=tkinter.filedialog',
        '--hidden-import=requests',
        '--hidden-import=urllib3',
        '--hidden-import=certifi',
        '--hidden-import=json',
        '--hidden-import=threading',
        '--hidden-import=pathlib',
        '--hidden-import=datetime',
        '--hidden-import=webbrowser',
        '--hidden-import=subprocess',

        # Exclude large unnecessary modules
        '--exclude-module=matplotlib',
        '--exclude-module=numpy',
        '--exclude-module=pandas',
        '--exclude-module=scipy',
        '--exclude-module=PIL',
        '--exclude-module=opencv',

        # Main script
        'tkinter_voice_client.py'
    ]

    print("Running PyInstaller command:")
    print(" ".join(cmd))
    print()

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

        if result.returncode == 0:
            print("✅ Build successful!")
            return True
        else:
            print("❌ Build failed!")
            print("STDOUT:", result.stdout)
            print("STDERR:", result.stderr)
            return False

    except subprocess.TimeoutExpired:
        print("❌ Build timed out (5 minutes)")
        return False
    except Exception as e:
        print(f"❌ Build error: {e}")
        return False


def create_laptop_package():
    """Create deployment package for laptop"""
    print("\n📦 Creating laptop deployment package...")

    # Check if executable was created
    exe_path = Path('dist/VoiceSQL_Client.exe')
    if not exe_path.exists():
        print("❌ Executable not found!")
        return False

    # Create deployment directory
    deploy_dir = Path('laptop_deployment')
    if deploy_dir.exists():
        shutil.rmtree(deploy_dir)
    deploy_dir.mkdir()

    # Copy executable
    shutil.copy2(exe_path, deploy_dir / 'VoiceSQL_Client.exe')
    print(f"  ✅ Copied executable")

    # Get file size
    size_mb = exe_path.stat().st_size / (1024 * 1024)
    print(f"  📊 Executable size: {size_mb:.1f} MB")

    # Create quick start guide
    quick_start = f"""Voice SQL Client - Laptop Testing Guide
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

QUICK START:
1. Double-click VoiceSQL_Client.exe to start
2. The GUI will open - test all features
3. Default server: http://BI-SQL001:8000

TESTING:
- Type queries in the text box
- Test export functionality (CSV/TXT)
- Check server connection status
- Try voice features if hardware available

TROUBLESHOOTING:
- Run as administrator if needed
- Check Windows Defender isn't blocking
- Verify network access to BI-SQL001:8000
- Check event viewer for detailed errors

FEATURES INCLUDED:
✅ Complete GUI with all controls
✅ Natural language to SQL processing
✅ Export to CSV/TXT files  
✅ Download management
✅ Built-in error handling
✅ Optional voice input/output

If the application doesn't start, try running from command prompt:
VoiceSQL_Client.exe

For support, contact the development team.
"""

    with open(deploy_dir / 'README.txt', 'w', encoding='utf-8') as f:
        f.write(quick_start)
    print(f"  ✅ Created README.txt")

    # Create launcher batch file
    launcher_bat = """@echo off
echo Starting Voice SQL Client...
echo.
VoiceSQL_Client.exe
if errorlevel 1 (
    echo.
    echo Application exited with error code %errorlevel%
    echo Check the README.txt for troubleshooting steps.
    echo.
    pause
)
"""

    with open(deploy_dir / 'start_voice_sql.bat', 'w') as f:
        f.write(launcher_bat)
    print(f"  ✅ Created start_voice_sql.bat")

    print(f"\n✅ Laptop deployment package ready: {deploy_dir.absolute()}")
    return True


def main():
    """Main build process"""
    print("🚀 Voice SQL Client - Laptop Builder")
    print("=" * 50)

    # Check requirements
    required_files = ['tkinter_voice_client.py']
    missing_files = [f for f in required_files if not os.path.exists(f)]

    if missing_files:
        print(f"❌ Missing required files: {missing_files}")
        return 1

    print("✅ Required files found")

    # Check PyInstaller
    if not check_pyinstaller():
        return 1

    # Clean previous builds
    clean_previous_builds()

    # Build executable
    if not build_executable():
        print("\n❌ Build failed! Check the errors above.")
        return 1

    # Create deployment package
    if not create_laptop_package():
        print("\n❌ Failed to create deployment package!")
        return 1

    # Success!
    print("\n" + "=" * 60)
    print("🎉 BUILD COMPLETED SUCCESSFULLY!")
    print("=" * 60)
    print("\n📁 Files ready for laptop:")
    deploy_dir = Path('laptop_deployment')
    for file in deploy_dir.iterdir():
        if file.is_file():
            size = file.stat().st_size / (1024 * 1024)
            print(f"  📄 {file.name} ({size:.1f} MB)")

    print(f"\n🚚 Next Steps:")
    print(f"1. Copy the 'laptop_deployment' folder to USB/network")
    print(f"2. Transfer to laptop via approved method")
    print(f"3. On laptop: Double-click VoiceSQL_Client.exe")
    print(f"4. Or use: start_voice_sql.bat for easier launching")
    print(f"\n💡 Tip: Test locally first - run dist/VoiceSQL_Client.exe")

    return 0


if __name__ == "__main__":
    try:
        result = main()
        print(f"\nBuild script completed with exit code: {result}")
        input("\nPress Enter to close...")
        sys.exit(result)
    except KeyboardInterrupt:
        print("\n🛑 Build interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n💥 Unexpected error: {e}")
        import traceback

        traceback.print_exc()
        input("\nPress Enter to close...")
        sys.exit(1)