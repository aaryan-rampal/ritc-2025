import sys
import signal

class FileLogger:
    def __init__(self, filename="log.txt"):
        self.filename = filename
        self.file = open(self.filename, "a", encoding="utf-8", buffering=1)  # Line-buffered writing
        self.log("\nStarting logging")

        # Handle cleanup on Ctrl+C
        signal.signal(signal.SIGINT, self.cleanup)
        signal.signal(signal.SIGTERM, self.cleanup)

    def log(self, message):
        """Write a message to the log file."""
        self.file.write(str(message) + "\n")
        self.file.flush()  # Ensure immediate writing

    def cleanup(self, signum=None, frame=None):
        """Ensure the file is closed properly on exit."""
        print("\nClosing log file...")
        self.file.close()
        sys.exit(0)

# Example usage:
if __name__ == "__main__":
    logger = FileLogger()
    logger.log("Logging system initialized.")
