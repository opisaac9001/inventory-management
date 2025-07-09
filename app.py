import os
import json
from flask import Flask, render_template, request, redirect, url_for, flash, g
from datetime import datetime
import settings_manager
from google_sheets_helper import GoogleSheetsHelper

app = Flask(__name__)
app.secret_key = 'supersecretkey_for_google_sheets_app' # Changed secret key

# Global variable to hold the sheets helper instance
# Will be initialized after settings are confirmed
sheets_helper_instance = None

def get_sheets_helper():
    """Gets or initializes the GoogleSheetsHelper instance."""
    global sheets_helper_instance
    if sheets_helper_instance is None:
        settings = settings_manager.load_settings()
        if settings:
            sheet_id = settings.get('google_sheet_id')
            sa_json_str = settings.get('service_account_json_str')
            if sheet_id and sa_json_str:
                try:
                    sa_info = json.loads(sa_json_str)
                    sheets_helper_instance = GoogleSheetsHelper(sheet_id=sheet_id, service_account_info=sa_info)
                    # Optionally, ensure sheets and headers on first successful init
                    # if not sheets_helper_instance.ensure_sheets_and_headers():
                    #     flash("Failed to ensure Google Sheets structure (sheets/headers). Check logs.", "danger")
                    #     sheets_helper_instance = None # Prevent use if setup failed
                    print("GoogleSheetsHelper initialized successfully.")
                except json.JSONDecodeError:
                    flash("Error: Service account JSON is not valid.", "danger")
                    print("Service account JSON is not valid.")
                    sheets_helper_instance = None
                except ConnectionError as e: # Custom error from GoogleSheetsHelper._authenticate
                    flash(f"Error connecting to Google Sheets: {e}", "danger")
                    print(f"ConnectionError initializing GoogleSheetsHelper: {e}")
                    sheets_helper_instance = None
                except Exception as e: # Catch any other init errors
                    flash(f"An unexpected error occurred initializing Google Sheets helper: {e}", "danger")
                    print(f"Unexpected error initializing GoogleSheetsHelper: {e}")
                    sheets_helper_instance = None
            else: # Should not happen if load_settings is correct
                print("Sheet ID or SA JSON string missing from settings, though settings file loaded.")
                sheets_helper_instance = None
        else: # Settings file not found or empty
            print("Settings not loaded, sheets_helper_instance remains None.")
            sheets_helper_instance = None

    # Store in g for easy access within request context if needed, though global might be enough
    g.sheets_helper = sheets_helper_instance
    return sheets_helper_instance


@app.before_request
def check_setup():
    """Checks if the application is configured before handling most requests."""
    if request.endpoint == 'setup' or request.path.startswith('/static/'):
        return # Allow access to setup page and static files

    g.sheets_helper = get_sheets_helper() # Ensure it's attempted to load
    if not g.sheets_helper:
        flash("Application not configured. Please complete the setup.", "warning")
        return redirect(url_for('setup'))
    # If helper is available, proceed to the requested endpoint


@app.route('/setup', methods=['GET', 'POST'])
def setup():
    current_settings = settings_manager.load_settings() or {}
    if request.method == 'POST':
        sheet_id = request.form.get('google_sheet_id')
        sa_json_str = request.form.get('service_account_json_str')

        if not sheet_id or not sa_json_str:
            flash("Both Google Sheet ID and Service Account JSON are required.", "danger")
            return render_template('setup.html', current_settings={'google_sheet_id': sheet_id, 'service_account_json_str': sa_json_str})

        try:
            sa_info_test = json.loads(sa_json_str) # Test if JSON is valid
            if not isinstance(sa_info_test, dict):
                 raise json.JSONDecodeError("JSON is not a dictionary.", sa_json_str,0)
        except json.JSONDecodeError as e:
            flash(f"Invalid Service Account JSON: {e}", "danger")
            return render_template('setup.html', current_settings={'google_sheet_id': sheet_id, 'service_account_json_str': sa_json_str})

        # Try to initialize helper to test connection and auth
        try:
            temp_helper = GoogleSheetsHelper(sheet_id=sheet_id, service_account_info=sa_info_test)
            if temp_helper.ensure_sheets_and_headers(): # This also tests connection
                # Save settings if connection and sheet setup are successful
                if settings_manager.save_settings(sheet_id, sa_json_str):
                    global sheets_helper_instance # Update global instance
                    sheets_helper_instance = temp_helper
                    g.sheets_helper = sheets_helper_instance
                    flash("Configuration saved and Google Sheets connection successful!", "success")
                    return redirect(url_for('home'))
                else:
                    flash("Failed to save settings to file. Check server permissions.", "danger")
            else:
                flash("Configuration seems valid, but failed to ensure Google Sheets structure (sheets/headers). Check Sheet ID, permissions, and logs.", "danger")

        except ConnectionError as e: # Raised by GoogleSheetsHelper._authenticate
             flash(f"Connection/Authentication Error with Google Sheets: {e}. Please check your Sheet ID, Service Account JSON, and that the sheet is shared with the service account email.", "danger")
        except Exception as e: # Catch any other unexpected errors during test
            flash(f"An unexpected error occurred during setup test: {e}", "danger")
            import traceback
            traceback.print_exc()

        return render_template('setup.html', current_settings={'google_sheet_id': sheet_id, 'service_account_json_str': sa_json_str})

    return render_template('setup.html', current_settings=current_settings)


@app.context_processor
def inject_now():
    return {'SCRIPT_START_TIME': datetime.utcnow()}

@app.route('/')
def home():
    if not g.get('sheets_helper'): return redirect(url_for('setup')) # Should be caught by before_request
    return render_template('home.html')

@app.route('/scan')
def scan_page():
    if not g.get('sheets_helper'): return redirect(url_for('setup'))
    helper = g.sheets_helper
    last_item_barcode = request.args.get('last_barcode')
    last_item_info = None
    if last_item_barcode:
        item_details = helper.get_item_details(last_item_barcode)
        if item_details:
            last_item_info = {
                'name': item_details.get(GoogleSheetsHelper.INVENTORY_COLS[1]),
                'barcode': item_details.get(GoogleSheetsHelper.INVENTORY_COLS[0]),
                'quantity': item_details.get(GoogleSheetsHelper.INVENTORY_COLS[2])
            }
    return render_template('scan.html', last_item=last_item_info)

@app.route('/lookup', methods=['GET'])
def lookup_item():
    if not g.get('sheets_helper'): return redirect(url_for('setup'))
    helper = g.sheets_helper
    barcode = request.args.get('barcode', None)
    item_details_raw = None
    item_display = None
    if barcode:
        item_details_raw = helper.get_item_details(barcode)
        if item_details_raw:
            item_display = {
                'barcode': item_details_raw.get(GoogleSheetsHelper.INVENTORY_COLS[0]),
                'name': item_details_raw.get(GoogleSheetsHelper.INVENTORY_COLS[1]),
                'quantity': item_details_raw.get(GoogleSheetsHelper.INVENTORY_COLS[2]),
                'last_updated': item_details_raw.get(GoogleSheetsHelper.INVENTORY_COLS[3])
            }
    return render_template('lookup.html', item_details=item_display, searched_barcode=barcode)


@app.route('/add-item')
def add_item_page():
    if not g.get('sheets_helper'): return redirect(url_for('setup'))
    return render_template('add_item.html')


@app.route('/add_item_submit', methods=['POST'])
def add_item_submit():
    if not g.get('sheets_helper'): return redirect(url_for('setup'))
    helper = g.sheets_helper
    if request.method == 'POST':
        barcode = request.form.get('barcode')
        name = request.form.get('name')
        quantity_str = request.form.get('quantity')

        if not barcode or not name:
            flash("Barcode and Name are required.", "danger")
            return redirect(url_for('add_item_page'))

        try:
            quantity = int(quantity_str)
            if quantity < 0:
                flash("Quantity cannot be negative. It will be set to 0.", "warning")
                quantity = 0
        except (ValueError, TypeError):
            flash("Invalid quantity. Please enter a whole number. It will be set to 0.", "warning")
            quantity = 0 # Default to 0

        if helper.find_item_row(barcode):
            flash(f"Item with barcode {barcode} already exists.", "warning")
        elif helper.add_item(barcode, name, quantity):
            flash(f"Item '{name}' (Barcode: {barcode}) added successfully with quantity {quantity}.", "success")
        else:
            flash(f"Failed to add item '{name}'. Check logs or Google Sheet API errors.", "danger")

        return redirect(url_for('add_item_page'))


@app.route('/update_inventory', methods=['POST'])
def update_inventory():
    if not g.get('sheets_helper'): return redirect(url_for('setup'))
    helper = g.sheets_helper
    if request.method == 'POST':
        barcode = request.form.get('barcode')
        quantity_str = request.form.get('quantity', '1')
        mode = request.form.get('mode')

        if not barcode:
            flash("Barcode is required.", "danger")
            return redirect(url_for('scan_page'))

        try:
            quantity_change = int(quantity_str)
            if quantity_change <= 0:
                flash("Quantity to change must be a positive number.", "warning")
                return redirect(url_for('scan_page', last_barcode=barcode))
        except ValueError:
            flash("Invalid quantity. Please enter a number.", "danger")
            return redirect(url_for('scan_page', last_barcode=barcode))

        if not helper.find_item_row(barcode):
            flash(f"Item with barcode {barcode} not found. Please add it first.", "warning")
            return redirect(url_for('add_item_page', barcode=barcode))

        updated_quantity = helper.update_item_quantity(barcode, quantity_change, mode)

        if updated_quantity is not None:
            item_details = helper.get_item_details(barcode)
            item_name = item_details.get(GoogleSheetsHelper.INVENTORY_COLS[1], barcode) if item_details else barcode
            flash(f"Successfully updated '{item_name}'. New quantity: {updated_quantity}.", "success")
            return redirect(url_for('scan_page', last_barcode=barcode))
        else:
            flash(f"Failed to update quantity for barcode {barcode}. Check logs or Google Sheet API errors.", "danger")
            return redirect(url_for('scan_page', last_barcode=barcode))

    return redirect(url_for('scan_page'))


if __name__ == '__main__':
    # Note: `get_sheets_helper()` will be called by `before_request` when requests come in.
    # No explicit load_workbook or helper init here, as it depends on settings file.
    app.run(debug=True, host='0.0.0.0', port=5000)
