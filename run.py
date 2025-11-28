#!/usr/bin/env python3
"""
HyperTracker Bot - Entry Point
This script ensures proper module paths before importing the main application.
"""
import sys
import os
from pathlib import Path

# Get the absolute path to the project root directory
project_root = Path(__file__).parent.resolve()

# Add to Python path if not already there
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Also add as PYTHONPATH environment variable
os.environ['PYTHONPATH'] = str(project_root) + os.pathsep + os.environ.get('PYTHONPATH', '')

# Print debug info
print(f"Project root: {project_root}")
print(f"Python path includes: {str(project_root)}")
print(f"Current directory: {os.getcwd()}")
print()

# Verify the modules can be found
try:
    import core
    import bot
    import utils
    print("✓ Modules found successfully")
except ImportError as e:
    print(f"✗ Error: Could not import modules: {e}")
    print(f"\nPlease ensure you are running this from the project directory:")
    print(f"  cd {project_root}")
    print(f"  python run.py")
    sys.exit(1)

# Now import and run the main application
print("Starting HyperTracker Bot...\n")

from main import main
import asyncio

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nBot stopped by user")
    except Exception as e:
        print(f"\nFatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
