import pandas as pd
import time
import os
import urllib.parse
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import TimeoutException, NoSuchElementException

# Load contacts from Excel file
def load_contacts(file_path):
    if not os.path.exists(file_path):
        print(f"Error: The file '{file_path}' does not exist.")
        print(f"Current working directory: {os.getcwd()}")
        exit(1)
    df = pd.read_excel(file_path)
    return df

# Initialize WhatsApp Web
def initialize_whatsapp():
    # Setup Chrome options
    chrome_options = webdriver.ChromeOptions()
    chrome_options.add_argument("--start-maximized")
    # Uncomment this if you want to avoid Chrome closing automatically when script ends
    # chrome_options.add_experimental_option("detach", True)
    
    # Initialize the driver
    print("Initializing WhatsApp Web...")
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
    driver.get("https://web.whatsapp.com/")
    
    # Wait for user to scan QR code and load WhatsApp Web
    print("Please scan the QR code with your phone...")
    try:
        WebDriverWait(driver, 60).until(EC.presence_of_element_located((By.ID, "side")))
        print("WhatsApp Web loaded successfully!")
    except TimeoutException:
        print("Timeout waiting for WhatsApp Web to load. Please try again.")
        driver.quit()
        exit(1)
    
    # Give extra time for full loading
    time.sleep(5)
    return driver

# Send message to a single contact
def send_message_to_contact(driver, phone, message):
    try:
        # URL encode the message
        encoded_message = urllib.parse.quote(message)
        
        # Navigate to the specific chat
        whatsapp_url = f"https://web.whatsapp.com/send?phone={phone}&text={encoded_message}"
        driver.get(whatsapp_url)
        
        print(f"Waiting for chat to load for {phone}...")
        
        # Wait for chat to load - look for the send button instead
        send_button = WebDriverWait(driver, 30).until(
            EC.element_to_be_clickable((By.XPATH, "//span[@data-icon='send']"))
        )
        
        # Click the send button
        send_button.click()
        print(f"Message sent to {phone}")
        
        # Wait to ensure message is sent
        time.sleep(5)
        return True
        
    except TimeoutException:
        print(f"Timeout loading chat for {phone}. Number may be invalid.")
        return False
    except NoSuchElementException:
        print(f"Could not find send button for {phone}.")
        return False
    except Exception as e:
        print(f"Error sending message to {phone}: {str(e)}")
        return False

# Send messages to all contacts using a single browser instance
def send_bulk_messages(driver, contacts_df, message, phone_column):
    country_code = input("Enter your country code (e.g., 91 for India, without + symbol): ")
    total_contacts = len(contacts_df)
    successful = 0
    
    for index, row in contacts_df.iterrows():
        # Get phone number and ensure it's formatted correctly
        phone = str(row[phone_column]).strip()
        # Remove any non-digit characters
        phone = ''.join(filter(str.isdigit, phone))
        
        # If the number already starts with the country code, don't add it again
        if not phone.startswith(country_code):
            phone = country_code + phone
        
        print(f"\nProcessing {index+1}/{total_contacts}: {phone}")
        
        if send_message_to_contact(driver, phone, message):
            successful += 1
        
        # Pause between messages to avoid being blocked
        delay = 10  # seconds
        print(f"Waiting {delay} seconds before next message...")
        time.sleep(delay)
    
    print(f"\nCompleted: {successful} of {total_contacts} messages sent successfully.")
    return successful

# Example usage
if __name__ == "__main__":
    # Set file path
    excel_file = "path_to_xlsx_file"
    
    if not os.path.exists(excel_file):
        excel_file = input("Enter the full path to your Excel file: ")
    
    # Load contacts
    contacts = load_contacts(excel_file)
    
    # Show available columns
    print("\nAvailable columns in your Excel file:")
    for i, col in enumerate(contacts.columns):
        print(f"{i}: {col}")
    
    # Let user select column with phone numbers
    col_index = int(input("\nEnter the number of the column that contains phone numbers: "))
    phone_column = contacts.columns[col_index]
    print(f"Using column: {phone_column}")
    
    # Get message content
    message_content = input("Enter your message: ")
    
    # Initialize WhatsApp
    driver = initialize_whatsapp()
    
    try:
        # Send messages
        send_bulk_messages(driver, contacts, message_content, phone_column)
    except KeyboardInterrupt:
        print("\nProcess interrupted by user.")
    except Exception as e:
        print(f"\nAn error occurred: {str(e)}")
    finally:
        # Ask before closing
        input("\nPress Enter to close the browser...")
        driver.quit()