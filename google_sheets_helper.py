import time
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import json
from datetime import datetime

# Scopes required for Google Sheets API
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']

# Constants for sheet names and columns, similar to excel_helper
INVENTORY_SHEET_NAME = "Inventory"
LOG_SHEET_NAME = "Log"
INVENTORY_COLS = ["Barcode", "Name", "Quantity", "Last Updated"]
LOG_COLS = ["Timestamp", "Barcode", "Action", "Details", "User"]

class GoogleSheetsHelper:
    def __init__(self, sheet_id: str, service_account_info: dict):
        self.sheet_id = sheet_id
        self.service_account_info = service_account_info
        self.creds = None
        self.service = None
        self._authenticate()

    def _authenticate(self):
        """Authenticates with Google Sheets API using service account info."""
        try:
            self.creds = service_account.Credentials.from_service_account_info(
                self.service_account_info, scopes=SCOPES
            )
            self.service = build('sheets', 'v4', credentials=self.creds, cache_discovery=False)
        except Exception as e:
            print(f"Failed to authenticate with Google Sheets: {e}")
            # Potentially raise a custom exception here to be caught by app.py
            raise ConnectionError(f"Google Sheets authentication failed: {e}")

    def _execute_batch_update(self, requests_body):
        """Helper to execute batchUpdate requests."""
        if not self.service:
            raise ConnectionError("Google Sheets service not initialized.")
        try:
            self.service.spreadsheets().batchUpdate(
                spreadsheetId=self.sheet_id, body={'requests': requests_body}
            ).execute()
            return True
        except HttpError as e:
            print(f"Google Sheets API batchUpdate error: {e}")
            return False
        except Exception as e:
            print(f"An unexpected error occurred during batchUpdate: {e}")
            return False

    def _get_sheet_id_by_name(self, sheet_name):
        """Retrieves the integer ID of a sheet by its name."""
        if not self.service:
            raise ConnectionError("Google Sheets service not initialized.")
        try:
            spreadsheet_metadata = self.service.spreadsheets().get(spreadsheetId=self.sheet_id).execute()
            sheets = spreadsheet_metadata.get('sheets', [])
            for sheet in sheets:
                if sheet.get('properties', {}).get('title') == sheet_name:
                    return sheet.get('properties', {}).get('sheetId')
            return None
        except HttpError as e:
            print(f"Error getting sheet ID for '{sheet_name}': {e}")
            return None


    def ensure_sheets_and_headers(self) -> bool:
        """
        Ensures 'Inventory' and 'Log' sheets exist with correct headers.
        Returns True if successful or sheets already compliant, False on error.
        """
        if not self.service:
            raise ConnectionError("Google Sheets service not initialized.")

        requests = []
        try:
            spreadsheet_metadata = self.service.spreadsheets().get(spreadsheetId=self.sheet_id).execute()
            existing_sheets = {sheet['properties']['title']: sheet['properties']['sheetId'] for sheet in spreadsheet_metadata.get('sheets', [])}

            # Check/Create Inventory Sheet
            if INVENTORY_SHEET_NAME not in existing_sheets:
                requests.append({'addSheet': {'properties': {'title': INVENTORY_SHEET_NAME}}})
                print(f"'{INVENTORY_SHEET_NAME}' sheet creation requested.")
                # If we add a sheet, we'll need to re-fetch metadata or handle headers separately after creation

            # Check/Create Log Sheet
            if LOG_SHEET_NAME not in existing_sheets:
                requests.append({'addSheet': {'properties': {'title': LOG_SHEET_NAME}}})
                print(f"'{LOG_SHEET_NAME}' sheet creation requested.")

            if requests: # If sheets were added
                response = self.service.spreadsheets().batchUpdate(spreadsheetId=self.sheet_id, body={'requests': requests}).execute()
                print("Sheet creation requests executed.")
                # Update existing_sheets map after creation for header checks
                spreadsheet_metadata = self.service.spreadsheets().get(spreadsheetId=self.sheet_id).execute()
                existing_sheets = {sheet['properties']['title']: sheet['properties']['sheetId'] for sheet in spreadsheet_metadata.get('sheets', [])}
                time.sleep(1) # Brief pause for sheets to be fully available

            # Check/Write Headers for Inventory
            inventory_sheet_id = existing_sheets.get(INVENTORY_SHEET_NAME)
            if inventory_sheet_id is not None:
                header_check_inv = self.service.spreadsheets().values().get(
                    spreadsheetId=self.sheet_id, range=f"'{INVENTORY_SHEET_NAME}'!A1:D1"
                ).execute()
                if not header_check_inv.get('values'):
                    self.service.spreadsheets().values().update(
                        spreadsheetId=self.sheet_id, range=f"'{INVENTORY_SHEET_NAME}'!A1",
                        valueInputOption='USER_ENTERED', body={'values': [INVENTORY_COLS]}
                    ).execute()
                    print(f"Headers written to '{INVENTORY_SHEET_NAME}'.")
            else:
                print(f"Error: '{INVENTORY_SHEET_NAME}' sheet ID not found after potential creation.")
                return False


            # Check/Write Headers for Log
            log_sheet_id = existing_sheets.get(LOG_SHEET_NAME)
            if log_sheet_id is not None:
                header_check_log = self.service.spreadsheets().values().get(
                    spreadsheetId=self.sheet_id, range=f"'{LOG_SHEET_NAME}'!A1:E1"
                ).execute()
                if not header_check_log.get('values'):
                    self.service.spreadsheets().values().update(
                        spreadsheetId=self.sheet_id, range=f"'{LOG_SHEET_NAME}'!A1",
                        valueInputOption='USER_ENTERED', body={'values': [LOG_COLS]}
                    ).execute()
                    print(f"Headers written to '{LOG_SHEET_NAME}'.")
            else:
                print(f"Error: '{LOG_SHEET_NAME}' sheet ID not found after potential creation.")
                return False

            return True

        except HttpError as e:
            print(f"Google Sheets API error during ensure_sheets_and_headers: {e}")
            return False
        except Exception as e:
            print(f"Unexpected error in ensure_sheets_and_headers: {e}")
            return False

    def find_item_row(self, barcode: str) -> int | None:
        """Finds an item by barcode. Returns 1-indexed row number or None."""
        if not self.service: return None
        try:
            # Get all values from the Barcode column (A) in Inventory sheet
            # Assuming Barcode is always in column A
            result = self.service.spreadsheets().values().get(
                spreadsheetId=self.sheet_id, range=f"'{INVENTORY_SHEET_NAME}'!A:A"
            ).execute()
            values = result.get('values', [])
            for i, row in enumerate(values):
                if row and str(row[0]) == str(barcode):
                    return i + 1  # 1-indexed row number
            return None
        except HttpError as e:
            print(f"Google Sheets API error in find_item_row: {e}")
            return None

    def get_item_details(self, barcode: str) -> dict | None:
        """Retrieves item details by barcode."""
        row_num = self.find_item_row(barcode)
        if not row_num or not self.service:
            return None
        try:
            # Range for the specific row, up to column D (Barcode, Name, Quantity, Last Updated)
            result = self.service.spreadsheets().values().get(
                spreadsheetId=self.sheet_id, range=f"'{INVENTORY_SHEET_NAME}'!A{row_num}:D{row_num}"
            ).execute()
            row_values = result.get('values', [[]])[0]
            if not row_values: return None
            raw_qty_val = row_values[2] if len(row_values) > 2 else '0'
            parsed_qty = 0
            try:
                # Ensure it's treated as a string first for float conversion if it's a number like "123.0"
                # Then convert to int. Handles actual numbers from sheets too.
                parsed_qty = int(float(str(raw_qty_val)))
            except (ValueError, TypeError):
                print(f"Warning: Could not parse quantity '{raw_qty_val}' as int for barcode {barcode}. Defaulting to 0.")
                # parsed_qty remains 0

            return {
                INVENTORY_COLS[0]: row_values[0] if len(row_values) > 0 else None, # Barcode
                INVENTORY_COLS[1]: row_values[1] if len(row_values) > 1 else None, # Name
                INVENTORY_COLS[2]: parsed_qty, # Quantity
                INVENTORY_COLS[3]: row_values[3] if len(row_values) > 3 else None  # Last Updated
            }
        except HttpError as e:
            print(f"Google Sheets API error in get_item_details: {e}")
            return None
        except (IndexError, ValueError) as e:
            print(f"Error processing item details for barcode {barcode}: {e}")
            return None


    def add_item(self, barcode: str, name: str, quantity: int) -> bool:
        """Adds a new item to the Inventory sheet."""
        if self.find_item_row(barcode):
            print(f"Item with barcode {barcode} already exists.")
            return False # Item already exists
        if not self.service: return False

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            item_data = [barcode, name, int(quantity), timestamp]
            self.service.spreadsheets().values().append(
                spreadsheetId=self.sheet_id,
                range=f"'{INVENTORY_SHEET_NAME}'!A:D", # Append to the first 4 columns
                valueInputOption='USER_ENTERED',
                insertDataOption='INSERT_ROWS',
                body={'values': [item_data]}
            ).execute()
            self.add_log_entry(barcode, "ADD_ITEM", f"Name: {name}, Initial Qty: {quantity}")
            return True
        except HttpError as e:
            print(f"Google Sheets API error in add_item: {e}")
            return False
        except ValueError:
            print(f"Invalid quantity provided for item {barcode}: {quantity}")
            return False

    def update_item_quantity(self, barcode: str, quantity_change: int, mode: str) -> int | None:
        """Updates quantity of an existing item. Returns new quantity or None."""
        row_num = self.find_item_row(barcode)
        if not row_num or not self.service:
            return None

        try:
            # Get current quantity (Column C) and name (Column B)
            current_data_range = f"'{INVENTORY_SHEET_NAME}'!B{row_num}:C{row_num}"
            current_data_result = self.service.spreadsheets().values().get(
                spreadsheetId=self.sheet_id, range=current_data_range
            ).execute()

            current_values = current_data_result.get('values', [[]])[0]
            if not current_values or len(current_values) < 2: # Expect Name and Quantity
                 print(f"Could not retrieve current name/quantity for barcode {barcode} at row {row_num}.")
                 return None

            item_name = current_values[0]
            current_quantity = 0
            try:
                current_quantity = int(current_values[1])
            except (ValueError, TypeError):
                print(f"Warning: Could not parse current quantity for {barcode} as int. Assuming 0.")


            new_quantity = current_quantity
            if mode == "add":
                new_quantity = current_quantity + int(quantity_change)
            elif mode == "remove":
                new_quantity = current_quantity - int(quantity_change)
                if new_quantity < 0:
                    new_quantity = 0  # Prevent negative inventory

            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            # Update Quantity (Column C) and Last Updated (Column D)
            update_range = f"'{INVENTORY_SHEET_NAME}'!C{row_num}:D{row_num}"
            self.service.spreadsheets().values().update(
                spreadsheetId=self.sheet_id,
                range=update_range,
                valueInputOption='USER_ENTERED',
                body={'values': [[new_quantity, timestamp]]}
            ).execute()

            action_details = f"Mode: {mode.upper()}, Change: {quantity_change}, New Qty: {new_quantity}"
            action_log = f"UPDATE_QTY ({item_name or 'N/A'})"
            self.add_log_entry(barcode, action_log, action_details)
            return new_quantity
        except HttpError as e:
            print(f"Google Sheets API error in update_item_quantity: {e}")
            return None
        except ValueError:
            print(f"Invalid quantity_change value: {quantity_change}")
            return None
        except Exception as e:
            print(f"Unexpected error in update_item_quantity: {e}")
            return None

    def add_log_entry(self, barcode: str, action: str, details: str, user: str = "System") -> bool:
        """Adds an entry to the Log sheet."""
        if not self.service: return False
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_data = [timestamp, barcode, action, details, user]
        try:
            self.service.spreadsheets().values().append(
                spreadsheetId=self.sheet_id,
                range=f"'{LOG_SHEET_NAME}'!A:E", # Append to first 5 columns
                valueInputOption='USER_ENTERED',
                insertDataOption='INSERT_ROWS',
                body={'values': [log_data]}
            ).execute()
            return True
        except HttpError as e:
            print(f"Google Sheets API error in add_log_entry: {e}")
            return False

# Example usage (for direct testing, requires valid service_account_info.json and sheet_id)
if __name__ == '__main__':
    print("Attempting to test GoogleSheetsHelper...")
    # You would need to create a 'test_service_account.json' and provide a 'TEST_SHEET_ID'
    # For automated testing, this would require a more complex setup or mocking.

    SERVICE_ACCOUNT_FILE_FOR_TEST = 'path_to_your_service_account.json' # REPLACE
    TEST_SHEET_ID = 'your_test_google_sheet_id' # REPLACE

    try:
        with open(SERVICE_ACCOUNT_FILE_FOR_TEST, 'r') as f:
            sa_info = json.load(f)

        print(f"Initializing helper with Sheet ID: {TEST_SHEET_ID}")
        helper = GoogleSheetsHelper(sheet_id=TEST_SHEET_ID, service_account_info=sa_info)

        print("Ensuring sheets and headers...")
        if helper.ensure_sheets_and_headers():
            print("Sheets and headers setup complete/verified.")

            # Test Add Item
            print("\nTesting Add Item 'GSH001'...")
            if helper.add_item("GSH001", "Google Test Item 1", 10):
                print("Item 'GSH001' added.")
            else:
                print("Failed to add 'GSH001' or it already exists.")

            print("\nTesting Add Item 'GSH002'...")
            if helper.add_item("GSH002", "Google Test Item 2", 50):
                print("Item 'GSH002' added.")
            else:
                print("Failed to add 'GSH002' or it already exists.")

            # Test Get Item Details
            print("\nTesting Get Item Details for 'GSH001'...")
            details = helper.get_item_details("GSH001")
            if details:
                print(f"Details for 'GSH001': {details}")
                assert details['Name'] == "Google Test Item 1"
                assert details['Quantity'] == 10
            else:
                print("Could not get details for 'GSH001'.")

            # Test Update Item Quantity - Add
            print("\nTesting Update Item Quantity (add 5) for 'GSH001'...")
            new_qty_add = helper.update_item_quantity("GSH001", 5, "add")
            if new_qty_add is not None:
                print(f"'GSH001' new quantity after add: {new_qty_add}")
                assert new_qty_add == 15
            else:
                print("Failed to update 'GSH001' quantity (add).")

            # Test Update Item Quantity - Remove
            print("\nTesting Update Item Quantity (remove 3) for 'GSH002'...")
            new_qty_remove = helper.update_item_quantity("GSH002", 3, "remove")
            if new_qty_remove is not None:
                print(f"'GSH002' new quantity after remove: {new_qty_remove}")
                assert new_qty_remove == 47
            else:
                print("Failed to update 'GSH002' quantity (remove).")

            # Test Over-Remove
            print("\nTesting Update Item Quantity (remove 20) for 'GSH001' (current should be 15)...")
            new_qty_over_remove = helper.update_item_quantity("GSH001", 20, "remove")
            if new_qty_over_remove is not None:
                print(f"'GSH001' new quantity after over-remove: {new_qty_over_remove}")
                assert new_qty_over_remove == 0
            else:
                print("Failed to update 'GSH001' quantity (over-remove).")

            print("\nTesting find_item_row for 'GSH002'...")
            row = helper.find_item_row("GSH002")
            if row:
                print(f"'GSH002' found at row: {row}")
            else:
                print("'GSH002' not found.")

            print("\nTesting find_item_row for non-existent 'GSH999'...")
            row_non_existent = helper.find_item_row("GSH999")
            assert row_non_existent is None
            print("'GSH999' not found, as expected.")

        else:
            print("Failed to ensure sheets and headers. Aborting further tests.")

    except FileNotFoundError:
        print(f"TESTING SKIPPED: Service account file '{SERVICE_ACCOUNT_FILE_FOR_TEST}' not found.")
    except ConnectionError as ce:
        print(f"TESTING FAILED: Connection error - {ce}")
    except Exception as e:
        print(f"An error occurred during testing: {e}")
        import traceback
        traceback.print_exc()

    print("\nGoogleSheetsHelper testing attempt finished.")

    def get_all_items(self) -> list[dict]:
        """Retrieves all items from the Inventory sheet."""
        if not self.service:
            print("Google Sheets service not initialized.")
            return []
        try:
            # Range to get all data from Inventory sheet, starting from A2 to skip header
            range_name = f"'{INVENTORY_SHEET_NAME}'!A2:D" # A:D means all rows in these columns
            result = self.service.spreadsheets().values().get(
                spreadsheetId=self.sheet_id, range=range_name
            ).execute()

            values = result.get('values', [])
            if not values:
                print("No items found in inventory.")
                return []

            items = []
            for row in values:
                # Pad row with None if not all columns are present, up to expected INVENTORY_COLS length
                padded_row = row + [None] * (len(INVENTORY_COLS) - len(row))

                raw_qty_val = padded_row[2] # Quantity is at index 2
                parsed_qty = 0
                try:
                    if raw_qty_val is not None and str(raw_qty_val).strip() != "":
                        parsed_qty = int(float(str(raw_qty_val)))
                except (ValueError, TypeError):
                    print(f"Warning: Could not parse quantity '{raw_qty_val}' for item {padded_row[0]}. Defaulting to 0.")

                item_dict = {
                    INVENTORY_COLS[0]: padded_row[0],  # Barcode
                    INVENTORY_COLS[1]: padded_row[1],  # Name
                    INVENTORY_COLS[2]: parsed_qty,     # Quantity
                    INVENTORY_COLS[3]: padded_row[3]   # Last Updated
                }
                items.append(item_dict)

            return items
        except HttpError as e:
            print(f"Google Sheets API error in get_all_items: {e}")
            return []
        except Exception as e:
            print(f"An unexpected error occurred in get_all_items: {e}")
            import traceback
            traceback.print_exc()
            return []

    def batch_upsert_items(self, items_data: list[dict]) -> dict:
        """
        Batch upserts items into the Inventory sheet.
        Updates existing items (based on Barcode) or adds new ones.
        items_data: list of dicts, each like {'Barcode': '...', 'Name': '...', 'Quantity': ...}
        Returns a summary dict: {'added': count, 'updated': count, 'errors': list_of_error_details}
        """
        if not self.service:
            return {'added': 0, 'updated': 0, 'errors': ["Google Sheets service not initialized."]}
        if not items_data:
            return {'added': 0, 'updated': 0, 'errors': ["No items data provided for upsert."]}

        summary = {'added': 0, 'updated': 0, 'errors': []}

        try:
            # 1. Get all current barcodes and their row numbers
            # Range A:A gets all barcodes, B:D for corresponding data to avoid multiple reads for names
            range_name_all_inventory = f"'{INVENTORY_SHEET_NAME}'!A2:D"
            result = self.service.spreadsheets().values().get(
                spreadsheetId=self.sheet_id, range=range_name_all_inventory
            ).execute()

            existing_rows_values = result.get('values', [])

            # Create a map of barcode -> {row_index (0-based for list), name, quantity, last_updated}
            # The row_index here is 0-based relative to the start of the data range (A2)
            existing_items_map = {}
            for i, row_val in enumerate(existing_rows_values):
                if row_val and len(row_val) > 0 and row_val[0]: # Check if barcode exists
                    barcode = str(row_val[0])
                    existing_items_map[barcode] = {
                        'row_index_in_data': i, # 0-based index within the A2:D data
                        'sheet_row_num': i + 2,   # 1-based sheet row number (A2 is row 2)
                        'name': str(row_val[1]) if len(row_val) > 1 else '',
                        'quantity': int(float(str(row_val[2]))) if len(row_val) > 2 and str(row_val[2]).strip() else 0,
                        'last_updated': str(row_val[3]) if len(row_val) > 3 else ''
                    }

            update_requests_data = [] # For batchUpdate: {'range': ..., 'values': ...}
            new_rows_to_append = []   # For append operation: list of lists

            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            for item_csv in items_data:
                barcode_csv = str(item_csv['Barcode'])
                name_csv = str(item_csv['Name'])
                try:
                    quantity_csv = int(item_csv['Quantity'])
                    if quantity_csv < 0:
                        summary['errors'].append(f"Barcode {barcode_csv}: Quantity {quantity_csv} is negative, skipping.")
                        continue
                except (ValueError, TypeError):
                    summary['errors'].append(f"Barcode {barcode_csv}: Invalid quantity '{item_csv['Quantity']}', skipping.")
                    continue

                existing_item = existing_items_map.get(barcode_csv)

                if existing_item: # Item exists, prepare for update
                    # Only update if name or quantity is different to minimize writes & log entries
                    if existing_item['name'] != name_csv or existing_item['quantity'] != quantity_csv:
                        sheet_row_num = existing_item['sheet_row_num']
                        # Update Name (Col B), Quantity (Col C), Last Updated (Col D)
                        update_range = f"'{INVENTORY_SHEET_NAME}'!B{sheet_row_num}:D{sheet_row_num}"
                        update_requests_data.append({
                            'range': update_range,
                            'values': [[name_csv, quantity_csv, timestamp]]
                        })
                        self.add_log_entry(barcode_csv, "UPDATE_ITEM_CSV", f"Name: {name_csv}, Qty: {quantity_csv} (was {existing_item['name']}, {existing_item['quantity']})")
                        summary['updated'] += 1
                    # else: item is identical, no action needed for this one

                else: # Item is new, prepare for append
                    new_rows_to_append.append([barcode_csv, name_csv, quantity_csv, timestamp])
                    self.add_log_entry(barcode_csv, "ADD_ITEM_CSV", f"Name: {name_csv}, Qty: {quantity_csv}")
                    summary['added'] += 1

            # Execute batch updates if any
            if update_requests_data:
                body = {'valueInputOption': 'USER_ENTERED', 'data': update_requests_data}
                self.service.spreadsheets().values().batchUpdate(
                    spreadsheetId=self.sheet_id, body=body
                ).execute()

            # Execute append if any new rows
            if new_rows_to_append:
                self.service.spreadsheets().values().append(
                    spreadsheetId=self.sheet_id,
                    range=f"'{INVENTORY_SHEET_NAME}'!A:D",
                    valueInputOption='USER_ENTERED',
                    insertDataOption='INSERT_ROWS',
                    body={'values': new_rows_to_append}
                ).execute()

        except HttpError as e:
            err_msg = f"Google Sheets API error during batch upsert: {e}"
            print(err_msg)
            summary['errors'].append(err_msg)
        except Exception as e:
            err_msg = f"Unexpected error during batch upsert: {e}"
            print(err_msg)
            import traceback
            traceback.print_exc()
            summary['errors'].append(err_msg)

        return summary
