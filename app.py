import os
import json
from flask import Flask, render_template, request, redirect, url_for, flash, g, Response, session
from datetime import datetime, timedelta # Added timedelta
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
def before_request_checks():
    """
    Checks for application setup and user identification before handling most requests.
    Also handles session activity timeout.
    """
    # Define endpoints that are always allowed, regardless of setup or user identification
    allowed_endpoints = ['setup', 'identify_user', 'logout', 'static']
    if request.endpoint in allowed_endpoints or request.path.startswith('/static'): # Double check for static
        return

    # 1. Check Application Setup (Google Sheets connection)
    # This part is similar to the previous check_setup
    g.sheets_helper = get_sheets_helper()
    if not g.sheets_helper:
        flash("Application not configured. Please complete the Google Sheets setup.", "warning")
        session['next_url'] = request.url # Store intended URL before redirecting to setup
        return redirect(url_for('setup'))

    # 2. Check User Identification & Activity Timeout
    user_name = session.get('user_name')
    last_activity_str = session.get('last_activity') # Stored as ISO string by some session interfaces, or datetime obj

    if not user_name:
        flash("Please identify yourself to continue.", "info")
        session['next_url'] = request.url # Store intended URL
        return redirect(url_for('identify_user'))

    # User is identified, check for activity timeout
    if last_activity_str:
        # Flask session typically stores datetime objects directly if they are JSON serializable.
        # If it were stored as a string (e.g., session['last_activity'] = datetime.utcnow().isoformat()),
        # you'd need: last_activity = datetime.fromisoformat(last_activity_str)
        # Assuming it's stored as a datetime object directly by Flask's default session interface:
        last_activity = session['last_activity'] # Should be a datetime object

        # Ensure last_activity is indeed a datetime object, defensive coding
        if not isinstance(last_activity, datetime):
            try: # Attempt to parse if it was stored as string somehow
                last_activity = datetime.fromisoformat(str(last_activity_str))
            except (ValueError, TypeError):
                # If parsing fails, treat as invalid session state, force re-identification
                session.pop('user_name', None)
                session.pop('last_activity', None)
                flash("Session error. Please identify yourself again.", "warning")
                return redirect(url_for('identify_user'))

        if datetime.utcnow() - last_activity > timedelta(minutes=20):
            session.pop('user_name', None)
            session.pop('last_activity', None)
            flash("You have been logged out due to inactivity. Please identify yourself again.", "warning")
            session['next_url'] = request.url # Store intended URL
            return redirect(url_for('identify_user'))
    else: # No last_activity timestamp, but user_name exists - inconsistent state, force re-identify
        session.pop('user_name', None)
        flash("Session information incomplete. Please identify yourself again.", "warning")
        return redirect(url_for('identify_user'))

    # If all checks pass and user is active, update last_activity timestamp
    session['last_activity'] = datetime.utcnow()
    g.user_name = user_name # Make user_name available in g for the current request if needed


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

LOW_STOCK_THRESHOLD = 10 # Define globally or in app config

@app.route('/inventory_list')
def inventory_list():
    if not g.get('sheets_helper'): return redirect(url_for('setup'))
    helper = g.sheets_helper

    items = []
    try:
        items = helper.get_all_items()
    except Exception as e:
        flash(f"Error fetching inventory list: {e}", "danger")
        print(f"Error in /inventory_list route: {e}")
        # items will remain empty, template should handle this

    return render_template('inventory_list.html', items=items, low_stock_threshold=LOW_STOCK_THRESHOLD)

@app.route('/export_csv')
def export_csv():
    if not g.get('sheets_helper'):
        flash("Application not configured. Please complete the setup.", "warning")
        return redirect(url_for('setup'))

    helper = g.sheets_helper
    try:
        items = helper.get_all_items()
        if not items:
            flash("No inventory items to export.", "info")
            return redirect(url_for('inventory_list')) # Or wherever is appropriate

        # Use io.StringIO to create an in-memory text buffer
        import io
        import csv
        si = io.StringIO()
        # Define fieldnames based on GoogleSheetsHelper.INVENTORY_COLS or expected output
        # Ensure the order matches the desired CSV column order
        fieldnames = [
            GoogleSheetsHelper.INVENTORY_COLS[0], # Barcode
            GoogleSheetsHelper.INVENTORY_COLS[1], # Name
            GoogleSheetsHelper.INVENTORY_COLS[2], # Quantity
            GoogleSheetsHelper.INVENTORY_COLS[3]  # Last Updated
        ]

        writer = csv.DictWriter(si, fieldnames=fieldnames)
        writer.writeheader()
        for item in items:
            # Ensure all expected keys are present in item, defaulting if necessary
            # The `get_all_items` should already return dicts with these keys
            writer.writerow(item)

        output = si.getvalue()

        return Response(
            output,
            mimetype="text/csv",
            headers={"Content-disposition":
                     "attachment; filename=inventory_export.csv"})

    except Exception as e:
        flash(f"Error exporting CSV: {e}", "danger")
        print(f"Error in /export_csv route: {e}")
        import traceback
        traceback.print_exc()
        return redirect(url_for('inventory_list')) # Or home


@app.route('/add_item_submit', methods=['POST'])
def add_item_submit():
    # g.sheets_helper and g.user_name are expected to be set by before_request_checks
    if not g.get('sheets_helper'): return redirect(url_for('setup')) # Should be caught by before_request_checks
    if not g.get('user_name'): return redirect(url_for('identify_user')) # Should be caught by before_request_checks

    helper = g.sheets_helper
    user_name = g.user_name # Or session.get('user_name', 'Unknown_User')

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
            quantity = 0

        if helper.find_item_row(barcode):
            flash(f"Item with barcode {barcode} already exists.", "warning")
        elif helper.add_item(barcode, name, quantity, user=user_name): # Pass user_name
            flash(f"Item '{name}' (Barcode: {barcode}) added by {user_name} with quantity {quantity}.", "success")
        else:
            flash(f"Failed to add item '{name}'. Check logs or Google Sheet API errors.", "danger")

        return redirect(url_for('add_item_page'))


@app.route('/update_inventory', methods=['POST'])
def update_inventory():
    if not g.get('sheets_helper'): return redirect(url_for('setup'))
    if not g.get('user_name'): return redirect(url_for('identify_user'))

    helper = g.sheets_helper
    user_name = g.user_name

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

        updated_quantity = helper.update_item_quantity(barcode, quantity_change, mode, user=user_name) # Pass user_name

        if updated_quantity is not None:
            item_details = helper.get_item_details(barcode)
            item_name = item_details.get(GoogleSheetsHelper.INVENTORY_COLS[1], barcode) if item_details else barcode
            flash(f"Successfully updated '{item_name}' by {user_name}. New quantity: {updated_quantity}.", "success")
            return redirect(url_for('scan_page', last_barcode=barcode))
        else:
            flash(f"Failed to update quantity for barcode {barcode}. Check logs or Google Sheet API errors.", "danger")
            return redirect(url_for('scan_page', last_barcode=barcode))

    return redirect(url_for('scan_page'))


@app.route('/import_csv', methods=['GET', 'POST'])
def import_csv():
    if not g.get('sheets_helper'): return redirect(url_for('setup'))
    # For CSV import, user identification might still be relevant for who initiated the import.
    if not g.get('user_name') and request.method == 'POST': # Only strictly require user for POST
         flash("Please identify yourself before importing a CSV.", "warning")
         return redirect(url_for('identify_user', next=url_for('import_csv')))

    helper = g.sheets_helper
    # User for logging CSV actions. If no interactive user, could be a system default.
    # For actions within batch_upsert_items, it will pass this user.
    log_user = g.get('user_name', 'CSV_IMPORT_SYSTEM')


    if request.method == 'POST':
        if 'csv_file' not in request.files:
            flash('No file part in the request.', 'danger')
            return redirect(request.url)

        file = request.files['csv_file']
        if file.filename == '':
            flash('No selected file.', 'warning')
            return redirect(request.url)

        if file and file.filename.endswith('.csv'):
            try:
                csv_content = file.stream.read().decode('utf-8-sig')

                import io
                import csv
                si = io.StringIO(csv_content)
                reader = csv.DictReader(si)

                expected_headers = ['Barcode', 'Name', 'Quantity']
                if not reader.fieldnames or not all(header in reader.fieldnames for header in expected_headers):
                    flash(f"CSV file must have headers: {', '.join(expected_headers)}.", 'danger')
                    return redirect(request.url)

                items_to_upsert = []
                row_errors = []
                line_num = 1

                for row in reader:
                    line_num += 1
                    barcode = row.get('Barcode', '').strip()
                    name = row.get('Name', '').strip()
                    quantity_str = row.get('Quantity', '').strip()

                    if not barcode:
                        row_errors.append(f"Row {line_num}: Missing Barcode.")
                        continue
                    if not name:
                        row_errors.append(f"Row {line_num} (Barcode: {barcode}): Missing Name.")
                        continue

                    try:
                        quantity = int(quantity_str)
                        if quantity < 0:
                            row_errors.append(f"Row {line_num} (Barcode: {barcode}): Quantity '{quantity_str}' cannot be negative.")
                            continue
                    except ValueError:
                        row_errors.append(f"Row {line_num} (Barcode: {barcode}): Invalid Quantity '{quantity_str}'. Must be a whole number.")
                        continue

                    items_to_upsert.append({'Barcode': barcode, 'Name': name, 'Quantity': quantity})

                if row_errors:
                    flash(row_errors, 'csv_errors')

                if items_to_upsert:
                    # Pass the identified user (or system default if no interactive user for POST)
                    summary = helper.batch_upsert_items(items_to_upsert, user=log_user)
                    flash_summary_parts = []
                    if summary['added'] > 0:
                        flash_summary_parts.append(f"{summary['added']} item(s) added.")
                    if summary['updated'] > 0:
                        flash_summary_parts.append(f"{summary['updated']} item(s) updated.")
                    if not summary['added'] and not summary['updated'] and not row_errors and not summary['errors']:
                         flash_summary_parts.append("No changes made; items might have matched existing data or no valid items were processed.")

                    if summary['errors']:
                        flash(summary['errors'], 'csv_errors')

                    if flash_summary_parts:
                         flash(f"Import by {log_user}: " + " ".join(flash_summary_parts), 'csv_summary')

                    if not row_errors and not summary['errors'] and (summary['added'] or summary['updated']):
                        return redirect(url_for('inventory_list'))
                elif not row_errors:
                     flash("CSV file processed, but no valid items found to import or update.", "info")

            except Exception as e:
                flash(f"An error occurred processing the CSV file: {e}", 'danger')
                import traceback
                traceback.print_exc()

            return redirect(request.url)

    return render_template('import_inventory_csv.html')

@app.route('/identify_user', methods=['GET', 'POST'])
def identify_user():
    if request.method == 'POST':
        user_name = request.form.get('user_name', '').strip()
        if user_name:
            session['user_name'] = user_name
            session['last_activity'] = datetime.utcnow()
            flash(f"Welcome, {user_name}!", "success")
            # Redirect to intended page if stored, else home
            next_url = session.pop('next_url', url_for('home'))
            return redirect(next_url)
        else:
            flash("Please enter your name to continue.", "danger")
    # For GET request or if POST fails validation
    return render_template('identify_user.html')

@app.route('/logout')
def logout():
    user_name = session.pop('user_name', None)
    session.pop('last_activity', None)
    if user_name:
        flash(f"Successfully logged out, {user_name}.", "info")
    else:
        flash("Successfully logged out.", "info")
    return redirect(url_for('identify_user'))


if __name__ == '__main__':
    # Note: `get_sheets_helper()` will be called by `before_request` when requests come in.
    # No explicit load_workbook or helper init here, as it depends on settings file.
    app.run(debug=True, host='0.0.0.0', port=5000)
