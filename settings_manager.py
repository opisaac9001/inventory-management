import json
import os

SETTINGS_FILE = 'app_settings.json'

def save_settings(sheet_id: str, service_account_json_str: str, service_account_file_path: str = None):
    """
    Saves the Google Sheet ID and Service Account JSON string to the settings file.
    The service_account_file_path is effectively ignored now, as we store the content.
    """
    settings = {
        'google_sheet_id': sheet_id,
        'service_account_json_str': service_account_json_str
    }
    try:
        with open(SETTINGS_FILE, 'w') as f:
            json.dump(settings, f, indent=4)
        return True
    except IOError as e:
        print(f"Error saving settings: {e}")
        return False

def load_settings() -> dict | None:
    """
    Loads the settings from the settings file.
    Returns a dictionary with settings if successful, None otherwise.
    """
    if not os.path.exists(SETTINGS_FILE):
        return None
    try:
        with open(SETTINGS_FILE, 'r') as f:
            settings = json.load(f)
            # Basic validation
            if 'google_sheet_id' in settings and 'service_account_json_str' in settings:
                return settings
            else:
                print("Settings file is missing required keys.")
                return None
    except (IOError, json.JSONDecodeError) as e:
        print(f"Error loading or parsing settings: {e}")
        return None

def get_google_sheet_id() -> str | None:
    """Helper to get just the sheet ID."""
    settings = load_settings()
    return settings.get('google_sheet_id') if settings else None

def get_service_account_info() -> dict | None:
    """
    Helper to get the service account info as a dictionary from the JSON string.
    """
    settings = load_settings()
    if settings and settings.get('service_account_json_str'):
        try:
            return json.loads(settings['service_account_json_str'])
        except json.JSONDecodeError as e:
            print(f"Error parsing service_account_json_str: {e}")
            return None
    return None

if __name__ == '__main__':
    # Example Usage and Testing
    print("Testing settings_manager.py...")

    # Test saving
    test_sheet_id = "test_sheet_id_123"
    test_sa_json_str = '{"type": "service_account", "project_id": "test-project"}'
    print(f"Attempting to save settings: ID='{test_sheet_id}', JSON='{test_sa_json_str}'")
    if save_settings(test_sheet_id, test_sa_json_str):
        print("Settings saved successfully.")
    else:
        print("Failed to save settings.")

    # Test loading
    print("Attempting to load settings...")
    loaded = load_settings()
    if loaded:
        print(f"Settings loaded: {loaded}")
        retrieved_id = get_google_sheet_id()
        retrieved_sa_info = get_service_account_info()
        print(f"Retrieved Sheet ID: {retrieved_id}")
        print(f"Retrieved Service Account Info: {retrieved_sa_info}")
        assert retrieved_id == test_sheet_id
        assert retrieved_sa_info['project_id'] == "test-project"
        print("Load and helper functions test successful.")
    else:
        print("Failed to load settings or settings were invalid.")

    # Test loading non-existent file (by temporarily renaming)
    if os.path.exists(SETTINGS_FILE):
        try:
            os.rename(SETTINGS_FILE, SETTINGS_FILE + ".bak")
            print("Testing load_settings() when file does not exist...")
            assert load_settings() is None
            print("Load non-existent test successful.")
        finally:
            os.rename(SETTINGS_FILE + ".bak", SETTINGS_FILE)

    print("settings_manager.py tests complete.")
