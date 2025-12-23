# hantubot_prod/run.py
import sys
import os
from PySide6.QtWidgets import QApplication

# Ensure the project root is in the python path to allow for absolute imports
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Now that the path is set, we can import from our application
from hantubot.gui.main_window import MainWindow

def main():
    """
    Main entry point for the Hantubot application.
    Initializes and runs the GUI.
    """
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
