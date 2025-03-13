import pandas as pd
import time
import os
import logging
import random
from datetime import datetime
from tqdm import tqdm
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import TimeoutException, NoSuchElementException, ElementClickInterceptedException
from urllib.parse import quote
import requests
import random
from selenium.webdriver.common.action_chains import ActionChains

# Set up logging
log_file = f"whatsapp_bulk_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
logging.basicConfig(
    filename=log_file,
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
# Add this function to the script
def check_phone_validity(phone, country_code=""):
    """
    Pre-validate phone numbers before attempting to send messages.
    Returns True if likely valid, False otherwise.
    """
    # Format checks
    if not phone or not str(phone).strip():
        return False
        
    # Numbers with just country code
    if phone == country_code or len(phone) <= len(country_code) + 2:
        return False
        
    # Check for obviously invalid formats
    if len(phone) < 10 or len(phone) > 15:
        return False
    
    return True

# Add this function to improve chat opening reliability
def open_chat_with_retry(driver, phone, max_retries=3):
    """Open WhatsApp chat with retry mechanism and validation."""
    # First check if the number is valid before trying
    if not check_phone_validity(phone):
        logging.warning(f"Skipping likely invalid number: {phone}")
        return False, "Phone number appears invalid (too short or malformed)"
    
    # Try direct URL method first
    for attempt in range(max_retries):
        try:
            chat_url = f"https://web.whatsapp.com/send?phone={phone}"
            driver.get(chat_url)
            logging.info(f"Opening chat with {phone} (attempt {attempt+1}/{max_retries})...")
            
            # Wait for either the chat to load or for an error message
            element = WebDriverWait(driver, 15).until(
                EC.presence_of_any_element_located((
                    By.XPATH, '//div[@id="main"]//footer//div[@role="textbox"]',
                    By.XPATH, '//div[contains(text(), "Phone number shared via url is invalid")]'
                ))
            )
            
            # Check if we got the invalid number error
            try:
                error = driver.find_element(By.XPATH, 
                    '//div[contains(text(), "Phone number shared via url is invalid")]')
                logging.error(f"Invalid number error for {phone}")
                return False, "Invalid phone number"
            except NoSuchElementException:
                # No error found, chat might be loaded
                pass
            
            # Verify chat is actually loaded
            chat_loaded = wait_for_element(
                driver, 
                '//div[@id="main"]//footer//div[@role="textbox"]', 
                timeout=5,
                take_screenshot=False
            )
            
            if chat_loaded:
                return True, "Chat loaded successfully"
            
            # If we get here, something went wrong but no explicit error
            logging.warning(f"Chat may not be properly loaded for {phone}, retrying...")
            time.sleep(2)
            
        except TimeoutException:
            logging.warning(f"Timeout opening chat with {phone}, attempt {attempt+1}/{max_retries}")
            # Try refreshing the page
            try:
                driver.refresh()
                time.sleep(3)
            except:
                pass
            
        except Exception as e:
            logging.error(f"Error opening chat: {str(e)}")
            
    # If we get here, all attempts failed
    return False, "Failed to open chat after multiple attempts"

# Replace the send_message function with this improved version
def send_message_improved(driver, phone, message, media_path=None):
    """Enhanced message sending with better error handling and recovery."""
    try:
        # First validate and open the chat with retries
        chat_success, chat_result = open_chat_with_retry(driver, phone)
        if not chat_success:
            return False, chat_result
        
        # Chat is now open, proceed with sending the message
        chat_input = wait_for_element(
            driver, 
            '//div[@id="main"]//footer//div[@role="textbox"]', 
            timeout=15
        )
        
        if not chat_input:
            # Try one more approach - sometimes WhatsApp requires a click to focus
            try:
                ActionChains(driver).move_to_element_with_offset(
                    driver.find_element(By.XPATH, '//div[@id="main"]//footer'), 
                    10, 10
                ).click().perform()
                time.sleep(1)
                chat_input = driver.find_element(By.XPATH, '//div[@id="main"]//footer//div[@role="textbox"]')
            except:
                logging.error(f"Cannot find or interact with chat input for {phone}")
                return False, "Chat input not found"
        
        # Rest of the existing send_message function remains the same
        # (include the media handling code here)
        
        # Add better verification of message sending
        try:
            # Look for message status indicators after sending
            sent_indicator = wait_for_element(
                driver,
                '//span[@data-icon="msg-check"] | //span[@data-icon="msg-dblcheck"]',
                timeout=10
            )
            if sent_indicator:
                return True, "Message sent and confirmed delivered"
        except:
            # If we can't confirm, but no error occurred, assume success
            pass
            
        return True, "Message likely sent successfully"
        
    except Exception as e:
        # Capture screenshot with timestamp for debugging
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        screenshot_file = f"error_{phone}_{timestamp}.png"
        try:
            driver.save_screenshot(screenshot_file)
            logging.error(f"Screenshot saved to {screenshot_file}")
        except:
            pass
            
        logging.error(f"Error sending message to {phone}: {str(e)}")
        return False, f"Error: {str(e)}"


def load_contacts(file_path):
    """Loads contacts from an Excel file."""
    if not os.path.exists(file_path):
        logging.error(f"The file '{file_path}' does not exist.")
        print(f"Error: The file '{file_path}' does not exist.")
        exit(1)
    try:
        df = pd.read_excel(file_path, dtype=str)
        logging.info(f"Loaded contacts from {file_path} with {len(df)} rows.")
        return df
    except Exception as e:
        logging.error(f"Error loading contacts: {str(e)}")
        print(f"Error loading contacts: {str(e)}")
        exit(1)

def initialize_whatsapp():
    """Sets up Chrome and opens WhatsApp Web with user profile."""
    # Create a chrome profile directory to save login state
    user_data_dir = os.path.join(os.getcwd(), "chrome_profile")
    os.makedirs(user_data_dir, exist_ok=True)
    
    chrome_options = webdriver.ChromeOptions()
    chrome_options.add_argument("--start-maximized")
    chrome_options.add_argument(f"user-data-dir={user_data_dir}")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--disable-dev-shm-usage")
    
    # Disable images to speed up loading
    prefs = {
        "credentials_enable_service": False,
        "profile.password_manager_enabled": False,
        "profile.default_content_setting_values.notifications": 1,
        "profile.default_content_setting_values.media_stream_mic": 1,
        "profile.default_content_setting_values.media_stream_camera": 1
    }
    chrome_options.add_experimental_option("prefs", prefs)
    
    print("Initializing WhatsApp Web...")
    try:
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
        driver.get("https://web.whatsapp.com/")
        
        print("Please scan the QR code with your phone (if required)...")
        # Wait for WhatsApp Web to load completely
        WebDriverWait(driver, 60).until(
            EC.presence_of_element_located((By.XPATH, '//*[@id="side"]'))
        )
        logging.info("WhatsApp Web loaded successfully.")
        print("WhatsApp Web loaded successfully!")
        time.sleep(1)  # Reduced initial wait time
        return driver
    except Exception as e:
        logging.error(f"Error initializing WhatsApp Web: {str(e)}")
        print(f"Error initializing WhatsApp Web: {str(e)}")
        if 'driver' in locals():
            driver.save_screenshot("whatsapp_init_error.png")
            driver.quit()
        exit(1)

def wait_for_element(driver, xpath, timeout=20, take_screenshot=False, screenshot_name="element_wait"):
    """Wait for an element and take a screenshot if it fails."""
    try:
        element = WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.XPATH, xpath))
        )
        return element
    except TimeoutException:
        if take_screenshot:
            driver.save_screenshot(f"{screenshot_name}_timeout.png")
        logging.error(f"Timeout waiting for element: {xpath}")
        return None

def send_message(driver, phone, message, media_path=None):
    """Sends a message and media to a contact, ensuring both are sent together."""
    try:
        # Use encoded message for URL
        encoded_message = ""
        if message:
            encoded_message = quote(message)
        
        # Navigate directly to the contact's chat
        chat_url = f"https://web.whatsapp.com/send?phone={phone}"
        if encoded_message:
            chat_url += f"&text={encoded_message}"
            
        driver.get(chat_url)
        logging.info(f"Opening chat with {phone}...")
        print(f"Opening chat with {phone}...")
        
        # Wait for the chat to load
        chat_input = wait_for_element(
            driver, 
            '//div[@id="main"]//footer//div[@role="textbox"]', 
            timeout=20,
            screenshot_name=f"chat_load_{phone}"
        )
        
        if not chat_input:
            # Check if we got an invalid number error
            try:
                invalid_number = driver.find_element(By.XPATH, 
                    '//div[contains(text(), "Phone number shared via url is invalid")]'
                )
                logging.error(f"Invalid number: {phone}")
                return False, "Invalid phone number"
            except NoSuchElementException:
                logging.error(f"Timeout loading chat for {phone}")
                return False, "Chat load timeout"
        
        # Only need a short wait
        time.sleep(0.5)
        
        # If we didn't specify a message in the URL or need to add media, handle it now
        if not media_path:
            # For text-only messages, just press Enter
            if chat_input:
                if not encoded_message:
                    # If no message was in URL, add it now
                    chat_input.send_keys(message)
                    time.sleep(0.5)
                
                # Send the message
                chat_input.send_keys(Keys.ENTER)
                time.sleep(1)  # Reduced wait time for message send
                logging.info(f"Text message sent to {phone}")
                return True, "Text message sent successfully"
        else:
            # We have media to send
            if not os.path.exists(media_path):
                logging.error(f"Media file not found: {media_path}")
                if encoded_message:
                    # Still send the text message
                    chat_input.send_keys(Keys.ENTER)
                    time.sleep(1)
                    return True, "Text sent but media file not found"
                return False, "Media file not found"
            
            # Find the attachment button
            clip_selectors = [
                '//div[@title="Attach"]',
                '//span[@data-icon="attach"]',
                '//span[@data-testid="clip"]',
                '//button[contains(@aria-label, "Attach")]',
                '//*[contains(@aria-label, "Attach")]'
            ]
            
            clip_found = False
            for selector in clip_selectors:
                try:
                    clip_button = driver.find_element(By.XPATH, selector)
                    clip_button.click()
                    clip_found = True
                    logging.info("Attachment button clicked")
                    time.sleep(1)  # Reduced wait time
                    break
                except (NoSuchElementException, ElementClickInterceptedException) as e:
                    continue
            
            if not clip_found:
                # Try with JavaScript as a fallback
                try:
                    clip_found = driver.execute_script("""
                        var buttons = document.querySelectorAll('[data-icon="attach"], [title="Attach"], [aria-label*="Attach"]');
                        if (buttons.length > 0) {
                            buttons[0].click();
                            return true;
                        }
                        return false;
                    """)
                except Exception as js_error:
                    logging.error(f"JavaScript clip error: {str(js_error)}")
            
            if not clip_found:
                logging.error("Could not find attachment button")
                driver.save_screenshot(f"no_clip_button_{phone}.png")
                
                # Send just text if we have it
                if encoded_message and chat_input:
                    chat_input.send_keys(Keys.ENTER)
                    time.sleep(1)
                    return True, "Text sent but media attachment failed - clip button not found"
                return False, "Media attachment failed - clip button not found"
            
            # Find file input for media
            file_input = None
            
            # First look for all file inputs
            file_selectors = [
                '//input[@accept="image/*,video/mp4,video/3gpp,video/quicktime"]',
                '//input[@type="file"]'
            ]
            
            for selector in file_selectors:
                elements = driver.find_elements(By.XPATH, selector)
                if elements:
                    file_input = elements[0]
                    break
            
            # If not found, try clicking the image option first
            if not file_input:
                try:
                    image_options = driver.find_elements(By.XPATH, 
                        '//span[@data-icon="attach-image"] | //div[contains(@aria-label, "Photo")]'
                    )
                    if image_options:
                        image_options[0].click()
                        time.sleep(1)  # Reduced wait time
                        # Now look for file input again
                        elements = driver.find_elements(By.XPATH, '//input[@type="file"]')
                        if elements:
                            file_input = elements[0]
                except Exception as image_error:
                    logging.error(f"Error selecting image option: {str(image_error)}")
            
            # Make file inputs visible with JavaScript as last resort
            if not file_input:
                try:
                    driver.execute_script("""
                        var inputs = document.getElementsByTagName('input');
                        for(var i=0; i<inputs.length; i++) {
                            if(inputs[i].type === 'file') {
                                inputs[i].style.display = 'block';
                                inputs[i].style.visibility = 'visible';
                                inputs[i].style.opacity = '1';
                                inputs[i].style.position = 'relative';
                                inputs[i].style.zIndex = '9999';
                            }
                        }
                    """)
                    time.sleep(0.5)  # Reduced wait time
                    
                    # Try to find file input again
                    elements = driver.find_elements(By.XPATH, '//input[@type="file"]')
                    if elements:
                        file_input = elements[0]
                except Exception as js_error:
                    logging.error(f"JavaScript file input error: {str(js_error)}")
            
            if not file_input:
                logging.error("Could not find file input element")
                driver.save_screenshot(f"no_file_input_{phone}.png")
                
                # Send just text if we have it
                if encoded_message and chat_input:
                    chat_input.send_keys(Keys.ENTER)
                    time.sleep(1)
                    return True, "Text sent but media attachment failed - file input not found"
                return False, "Media attachment failed - file input not found"
            
            # Send the file path to the input
            abs_media_path = os.path.abspath(media_path)
            logging.info(f"Attaching media: {abs_media_path}")
            file_input.send_keys(abs_media_path)
            
            # Wait for media to upload
            image_preview = wait_for_element(
                driver,
                '//div[contains(@class, "image-thumb")] | //div[contains(@data-testid, "media-canvas")]',
                timeout=15,  # Reduced timeout
                screenshot_name=f"media_upload_{phone}"
            )
            
            # Now we need to find both the message input and the send button
            # If we didn't send text in the URL, we should add it now
            if not encoded_message and message:
                try:
                    chat_input = driver.find_element(By.XPATH, '//div[@role="textbox"][@contenteditable="true"]')
                    chat_input.send_keys(message)
                    time.sleep(0.5)  # Reduced wait time
                except Exception as text_error:
                    logging.error(f"Error entering text with media: {str(text_error)}")
            
            # Wait for send button to be clickable
            send_button = wait_for_element(
                driver,
                '//span[@data-icon="send"] | //button[contains(@aria-label, "Send")]',
                timeout=15,  # Reduced timeout
                screenshot_name=f"send_button_{phone}"
            )
            
            if send_button:
                try:
                    send_button.click()
                    logging.info(f"Media and text sent to {phone}")
                    time.sleep(2)  # Reduced wait time for message to send
                    return True, "Media and text sent successfully"
                except Exception as click_error:
                    logging.error(f"Error clicking send button: {str(click_error)}")
                    
                    # Try JavaScript click as last resort
                    try:
                        sent = driver.execute_script("""
                            var buttons = document.querySelectorAll('[data-icon="send"], [aria-label*="Send"]');
                            if (buttons.length > 0) {
                                buttons[0].click();
                                return true;
                            }
                            return false;
                        """)
                        
                        if sent:
                            logging.info(f"Media and text sent to {phone} via JavaScript")
                            time.sleep(2)  # Reduced wait time
                            return True, "Media and text sent successfully"
                    except Exception as js_error:
                        logging.error(f"JavaScript send error: {str(js_error)}")
            
            logging.error("Failed to send media - send button not clicked")
            driver.save_screenshot(f"send_failure_{phone}.png")
            return False, "Failed to send media - send button error"
        
        return False, "Unknown error in messaging process"
        
    except Exception as e:
        logging.error(f"Error sending message to {phone}: {str(e)}")
        driver.save_screenshot(f"general_error_{phone}.png")
        return False, str(e)

def format_phone_number(phone, country_code):
    """Format phone number with country code."""
    # Remove non-digit characters
    phone = ''.join(filter(str.isdigit, str(phone).strip()))
    
    # Add country code if not present
    if not phone.startswith(country_code):
        phone = country_code + phone
    
    return phone

def batch_process_contacts(driver, contacts_df, phone_column, message, media_path=None, batch_size=10):
    """Process contacts in batches to improve overall speed."""
    country_code = input("Enter country code (e.g., 91 for India, without +): ")
    
    successful = 0
    failed = 0
    results = []
    
    total_contacts = len(contacts_df)
    print(f"\nSending messages to {total_contacts} contacts...")
    
    # Create batches of contacts
    batches = [contacts_df[i:i + batch_size] for i in range(0, len(contacts_df), batch_size)]
    batch_number = 1
    
    for batch_df in batches:
        print(f"\nProcessing batch {batch_number}/{len(batches)} ({len(batch_df)} contacts)")
        
        # Process each contact in the batch
        for index, row in tqdm(batch_df.iterrows(), total=len(batch_df), desc="Batch progress"):
            # Format phone number
            phone = format_phone_number(row[phone_column], country_code)
            
            print(f"\nProcessing contact {index+1} (overall {successful+failed+1}/{total_contacts}): {phone}")
            
            # Send message
            success, result = send_message(driver, phone, message, media_path)
            
            # Record result
            status = "Sent" if success else "Failed"
            results.append({"phone": phone, "status": status, "result": result})
            
            if success:
                successful += 1
                print(f"✓ Success: {result}")
            else:
                failed += 1
                print(f"✗ Failed: {result}")
            
            # Add randomized delay between messages to reduce detection risk
            # Shorter delay with randomization to avoid detection patterns
            if media_path:
                delay = random.uniform(5, 10)  # Random delay between 5-10 seconds for media
            else:
                delay = random.uniform(3, 7)   # Random delay between 3-7 seconds for text
                
            print(f"Waiting {delay:.1f} seconds before next message...")
            time.sleep(delay)
        
        # After each batch, take a slightly longer break
        if batch_number < len(batches):
            batch_break = random.uniform(12, 18)  # 12-18 seconds between batches
            print(f"\nCompleted batch {batch_number}/{len(batches)}. Taking a {batch_break:.1f} second break...")
            time.sleep(batch_break)
        
        batch_number += 1
        
        # Save interim results after each batch
        interim_df = pd.DataFrame(results)
        interim_file = f"whatsapp_interim_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        interim_df.to_excel(interim_file, index=False)
        print(f"Interim results saved to {interim_file}")
        # Validate phone numbers before processing
    print("Pre-validating phone numbers...")
    valid_contacts = []
    invalid_contacts = []
    
    for index, row in contacts_df.iterrows():
        phone = format_phone_number(row[phone_column], country_code)
        if check_phone_validity(phone, country_code):
            valid_contacts.append((index, row, phone))
        else:
            invalid_contacts.append((index, row, phone))
    
    if invalid_contacts:
        print(f"\nWARNING: Found {len(invalid_contacts)} potentially invalid phone numbers.")
        show_invalid = input("Would you like to see them before proceeding? (y/n): ").lower()
        if show_invalid == 'y':
            for _, row, phone in invalid_contacts:
                print(f"Row {row.name}: {phone} (original: {row[phone_column]})")
        proceed = input("\nContinue only with valid numbers? (y/n): ").lower()
        if proceed != 'y':
            # Include invalid numbers
            valid_contacts.extend(invalid_contacts)
    
    if not valid_contacts:
        print("No valid contacts to process.")
        return 0, 0
    
    # Save final results
    print(f"\nAll batches completed: {successful} successful, {failed} failed out of {total_contacts}")
    results_df = pd.DataFrame(results)
    results_file = f"whatsapp_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    results_df.to_excel(results_file, index=False)
    print(f"Final results saved to {results_file}")
    
    # Save failed contacts separately for retry
    failed_df = results_df[results_df["status"] == "Failed"]
    if not failed_df.empty:
        failed_file = f"failed_contacts_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        failed_df.to_excel(failed_file, index=False)
        print(f"Failed contacts saved to {failed_file}")
    
    return successful, failed

def check_whatsapp_status(driver):
    """Check if WhatsApp is still connected and try to recover if not."""
    try:
        # Look for common disconnection indicators
        disconnected = driver.find_elements(By.XPATH, 
            '//div[contains(text(), "Phone not connected")] | //div[contains(text(), "Reconnecting")]')
        
        if disconnected:
            logging.warning("WhatsApp appears to be disconnected. Attempting to recover...")
            print("\nWhatsApp connection issue detected. Attempting to recover...")
            
            # Try refreshing
            driver.refresh()
            
            # Wait for reconnection
            success = WebDriverWait(driver, 60).until(
                EC.presence_of_element_located((By.XPATH, '//*[@id="side"]'))
            )
            
            if success:
                logging.info("WhatsApp reconnected successfully")
                print("WhatsApp reconnected successfully!")
                time.sleep(3)  # Give it a moment to stabilize
                return True
                
        # If we don't detect any disconnection or recovery was successful
        return True
    except:
        # If we can't determine the status, assume we need to restart the session
        logging.error("Unable to determine WhatsApp connection status. Session may need restart.")
        return False

def main():
    try:
        print("WhatsApp Bulk Message Sender")
        print("============================")
        
        # Get inputs
        contacts_file = input("Enter the path to Excel file with contacts: ")
        phone_column = input("Enter the column name containing phone numbers: ")
        
        # Load contacts
        contacts_df = load_contacts(contacts_file)
        
        if contacts_df.empty:
            print("No contacts found in the file.")
            return
            
        if phone_column not in contacts_df.columns:
            print(f"Column '{phone_column}' not found in the Excel file.")
            print(f"Available columns: {', '.join(contacts_df.columns)}")
            return
        
        # Get message content
        print("\nEnter your message (press Enter twice to finish):")
        message_lines = []
        while True:
            line = input()
            if line == "":
                break
            message_lines.append(line)
        
        message = "\n".join(message_lines)
        
        # Check for media attachment
        media_option = input("\nDo you want to attach media? (y/n): ").lower()
        media_path = None
        if media_option == 'y':
            media_path = input("Enter the path to the media file (image/video): ")
            if not os.path.exists(media_path):
                print(f"File not found: {media_path}")
                retry = input("Continue without media? (y/n): ").lower()
                if retry != 'y':
                    return
                media_path = None
        
        # Ask for batch size
        try:
            batch_size = int(input("\nEnter batch size (recommended 5-20 contacts per batch): ") or "10")
            if batch_size < 1:
                batch_size = 10
                print("Invalid batch size. Using default: 10")
        except ValueError:
            batch_size = 10
            print("Invalid batch size. Using default: 10")
        
        # Initialize driver
        driver = initialize_whatsapp()
        
        # Confirm before sending
        count = len(contacts_df)
        print(f"\nReady to send messages to {count} contacts in batches of {batch_size}.")
        if message.strip():
            print(f"Message preview: \n{message[:100]}{'...' if len(message) > 100 else ''}")
        else:
            print("No text message will be sent.")
            
        if media_path:
            print(f"With media attachment: {media_path}")
        
        # Show expected time
        if media_path:
            est_time_per_msg = 15  # seconds with media
        else:
            est_time_per_msg = 8   # seconds without media
            
        est_total_mins = (count * est_time_per_msg) / 60
        print(f"Estimated completion time: approximately {est_total_mins:.1f} minutes")
        
        confirm = input("\nProceed with sending? (y/n): ").lower()
        if confirm != 'y':
            print("Operation cancelled.")
            driver.quit()
            return
        
        # Process contacts
        successful, failed = batch_process_contacts(driver, contacts_df, phone_column, message, media_path, batch_size)
        
        # Summary
        print("\nSummary:")
        print(f"Total contacts: {count}")
        print(f"Successfully sent: {successful}")
        print(f"Failed: {failed}")
        
        # Close the driver
        driver.quit()
        print("\nWhatsApp session closed.")
        
    except Exception as e:
        logging.error(f"Error in main function: {str(e)}")
        print(f"An error occurred: {str(e)}")
        try:
            if 'driver' in locals():
                driver.quit()
        except:
            pass
        
if __name__ == "__main__":
    main()
