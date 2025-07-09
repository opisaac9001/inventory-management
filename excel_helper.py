import openpyxl
from openpyxl.utils.exceptions import InvalidFileException
from datetime import datetime
import os

# This will be set by app.py to ensure consistency
EXCEL_FILE_PATH = 'inventory.xlsx'

# Constants for sheet names and columns
INVENTORY_SHEET_NAME = "Inventory"
LOG_SHEET_NAME = "Log"

INVENTORY_COLS = ["Barcode", "Name", "Quantity", "Last Updated"]
LOG_COLS = ["Timestamp", "Barcode", "Action", "Details", "User"]

def load_workbook(path=None):
    """Loads the Excel workbook. Creates it if it doesn't exist."""
    file_path = path or EXCEL_FILE_PATH
    try:
        # Try to load existing workbook
        workbook = openpyxl.load_workbook(file_path)
        # Ensure sheets exist
        if INVENTORY_SHEET_NAME not in workbook.sheetnames:
            inventory_sheet = workbook.create_sheet(INVENTORY_SHEET_NAME)
            inventory_sheet.append(INVENTORY_COLS)
        if LOG_SHEET_NAME not in workbook.sheetnames:
            log_sheet = workbook.create_sheet(LOG_SHEET_NAME)
            log_sheet.append(LOG_COLS)

    except (FileNotFoundError, InvalidFileException): # InvalidFileException for empty/corrupt files
        workbook = openpyxl.Workbook()
        # Create Inventory sheet
        if INVENTORY_SHEET_NAME in workbook.sheetnames: # Default sheet might be 'Sheet'
            inventory_sheet = workbook[INVENTORY_SHEET_NAME]
            inventory_sheet.title = INVENTORY_SHEET_NAME # Ensure correct name
        else:
            inventory_sheet = workbook.active
            inventory_sheet.title = INVENTORY_SHEET_NAME
        inventory_sheet.append(INVENTORY_COLS)

        # Create Log sheet
        if LOG_SHEET_NAME in workbook.sheetnames:
             log_sheet = workbook[LOG_SHEET_NAME]
        else:
            log_sheet = workbook.create_sheet(LOG_SHEET_NAME)
        log_sheet.append(LOG_COLS)

        # Remove default "Sheet" if it exists and is not one of our main sheets
        if "Sheet" in workbook.sheetnames and "Sheet" not in [INVENTORY_SHEET_NAME, LOG_SHEET_NAME]:
             if len(workbook.sheetnames) > 1 : # only if other sheets exist
                del workbook["Sheet"]

    try:
        workbook.save(file_path)
    except Exception as e:
        print(f"Error saving workbook during initial load/creation: {e}")
        # Decide how to handle this, maybe raise the exception
        # For now, we'll proceed, but operations might fail if saving failed
    return workbook

def find_item_row(barcode):
    """Finds an item by barcode in the Inventory sheet. Returns row_idx or None."""
    workbook = load_workbook()
    inventory_sheet = workbook[INVENTORY_SHEET_NAME]
    for row_idx, row in enumerate(inventory_sheet.iter_rows(min_row=2, values_only=True), start=2):
        if row and str(row[0]) == str(barcode): # Barcode is in the first column
            return row_idx
    return None

def add_item(barcode, name, quantity):
    """Adds a new item to the Inventory sheet. Returns True if successful, False otherwise."""
    if find_item_row(barcode):
        return False # Item already exists

    workbook = load_workbook()
    inventory_sheet = workbook[INVENTORY_SHEET_NAME]
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    try:
        quantity = int(quantity)
        if quantity < 0: quantity = 0 # Ensure quantity is not negative
    except ValueError:
        quantity = 0 # Default to 0 if quantity is not a valid number

    new_row = [barcode, name, quantity, timestamp]
    inventory_sheet.append(new_row)

    add_log_entry(barcode, "ADD_ITEM", f"Name: {name}, Initial Qty: {quantity}")

    try:
        workbook.save(EXCEL_FILE_PATH)
        return True
    except Exception as e:
        print(f"Error saving workbook after adding item: {e}")
        return False


def update_item_quantity(barcode, quantity_change, mode="add"):
    """Updates the quantity of an existing item. Returns new quantity or None if item not found."""
    row_idx = find_item_row(barcode)
    if not row_idx:
        return None

    workbook = load_workbook()
    inventory_sheet = workbook[INVENTORY_SHEET_NAME]

    current_quantity_cell = inventory_sheet.cell(row=row_idx, column=3) # Quantity is in the 3rd column
    try:
        current_quantity = int(current_quantity_cell.value)
    except (ValueError, TypeError):
        current_quantity = 0 # If quantity is missing or not a number, treat as 0

    try:
        quantity_change = int(quantity_change)
    except ValueError:
        return current_quantity # Invalid change, return current quantity

    if mode == "add":
        new_quantity = current_quantity + quantity_change
    elif mode == "remove":
        new_quantity = current_quantity - quantity_change
        if new_quantity < 0:
            new_quantity = 0 # Prevent negative inventory
    else:
        return current_quantity # Invalid mode

    inventory_sheet.cell(row=row_idx, column=3, value=new_quantity)
    inventory_sheet.cell(row=row_idx, column=4, value=datetime.now().strftime("%Y-%m-%d %H:%M:%S")) # Update Last Updated

    action_details = f"Mode: {mode.upper()}, Change: {quantity_change}, New Qty: {new_quantity}"
    item_name = inventory_sheet.cell(row=row_idx, column=2).value or "N/A"
    action_log = f"UPDATE_QTY ({item_name})"
    add_log_entry(barcode, action_log, action_details)

    try:
        workbook.save(EXCEL_FILE_PATH)
        return new_quantity
    except Exception as e:
        print(f"Error saving workbook after updating quantity: {e}")
        return None # Indicate error

def get_item_details(barcode):
    """Retrieves details for a specific item."""
    row_idx = find_item_row(barcode)
    if not row_idx:
        return None

    workbook = load_workbook()
    inventory_sheet = workbook[INVENTORY_SHEET_NAME]
    row_values = inventory_sheet.cell(row=row_idx, column=1).parent # Get the whole row

    return {
        "barcode": row_values[0].value,
        "name": row_values[1].value,
        "quantity": row_values[2].value,
        "last_updated": row_values[3].value
    }

def add_log_entry(barcode, action, details, user="System"):
    """Adds an entry to the Log sheet."""
    workbook = load_workbook()
    log_sheet = workbook[LOG_SHEET_NAME]
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_row = [timestamp, barcode, action, details, user]
    log_sheet.append(log_row)
    # Note: Saving is typically done by the calling function (add_item, update_item_quantity)
    # to bundle save operations. If this is called standalone, it might need its own save.
    # For now, we assume the main operations will handle the save.
    # However, if an operation only logs without modifying inventory, it would need a save here.
    # Let's add a save here for safety, though it might be redundant in some flows.
    try:
        workbook.save(EXCEL_FILE_PATH)
    except Exception as e:
        print(f"Error saving workbook after adding log entry: {e}")


if __name__ == '__main__':
    # Initialize or ensure the Excel file is correctly set up
    print(f"Attempting to load/initialize workbook at: {EXCEL_FILE_PATH}")
    if not os.path.exists(EXCEL_FILE_PATH):
        print(f"Excel file '{EXCEL_FILE_PATH}' not found, will be created.")
    else:
        print(f"Excel file '{EXCEL_FILE_PATH}' found.")

    wb = load_workbook()
    print(f"Excel file '{EXCEL_FILE_PATH}' is ready. Sheets: {wb.sheetnames}")

    # Example Usage (for testing directly)
    # print("\nTesting add_item...")
    # if add_item("123456", "Test Widget 1", 10):
    #     print("Test Widget 1 added.")
    # else:
    #     print("Test Widget 1 already exists or error.")

    # if add_item("789012", "Test Gadget 2", 5):
    #     print("Test Gadget 2 added.")
    # else:
    #     print("Test Gadget 2 already exists or error.")

    # print("\nTesting update_item_quantity...")
    # new_qty = update_item_quantity("123456", 5, mode="add")
    # if new_qty is not None:
    #     print(f"Test Widget 1 quantity updated to: {new_qty}")
    # else:
    #     print("Failed to update Test Widget 1.")

    # new_qty_remove = update_item_quantity("789012", 2, mode="remove")
    # if new_qty_remove is not None:
    #     print(f"Test Gadget 2 quantity updated to: {new_qty_remove}")
    # else:
    #     print("Failed to update Test Gadget 2.")

    # print("\nTesting get_item_details...")
    # item = get_item_details("123456")
    # if item:
    #     print(f"Details for 123456: {item}")
    # else:
    #     print("Item 123456 not found.")

    # print("\nChecking Log sheet content...")
    # log_wb = load_workbook()
    # log_s = log_wb[LOG_SHEET_NAME]
    # for row in log_s.iter_rows(min_row=1, values_only=True):
    #     print(row)
