import os

class DatabaseHandler:
    def __init__(self, directory_path):
        self.directory_path = directory_path

    def save_receipt(self, receipt_text: str) -> bool:
        """
        Saves the given receipt text to a file in the specified directory.

        Args:
            receipt_text (str): The text of the receipt to be saved.

        Returns:
            bool: True if the operation was successful, False otherwise.
        """
        try:
            with open(os.path.join(self.directory_path, "receipt.txt"), "w") as f:
                f.write(receipt_text)
            return True
        except Exception as e:
            print(f"Error saving receipt: {e}")
            return False

    def check_directory(self) -> bool:
        """
        Checks if the specified directory exists.

        Returns:
            bool: True if the directory exists, False otherwise.
        """
        try:
            return os.path.exists(self.directory_path)
        except Exception as e:
            print(f"Error checking directory: {e}")
            return False

# Example usage
if __name__ == "__main__":
    database_handler = DatabaseHandler("./receipts")
    
    receipt_text = "Hello World!"
    save_receipt_result = database_handler.save_receipt(receipt_text)
    check_directory_result = database_handler.check_directory()

    print(f"Save Receipt Result: {save_receipt_result}")
    print(f"Check Directory Result: {check_directory_result}")