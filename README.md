# Web Barcode Inventory Scanner with Google Sheets Backend

This is a simple web application that allows users to scan barcodes to update inventory quantities, add new items, and manage stock levels. All data is stored in a **Google Sheet**.

## Features

*   **Inventory Adjustment:** Easily increase or decrease stock quantities by scanning barcodes.
*   **Add New Items:** Add new products to the inventory with their barcode, name, and initial quantity.
*   **Google Sheets Backend:** All data is stored in a user-specified Google Sheet, accessible via the Google Sheets API.
*   **Simple Web UI:** A user-friendly interface built with Flask and Bootstrap.
*   **Audit Log:** Tracks all inventory changes in a separate 'Log' sheet within the same Google Sheet.
*   **UI-Based Setup:** Configure Google Sheet ID and Service Account credentials through a web interface on first launch.
*   **Item Lookup:** Look up item details by barcode.

## Project Structure

```
.
├── app.py                     # Main Flask application
├── google_sheets_helper.py    # Functions for Google Sheets API interaction
├── settings_manager.py        # Handles loading/saving of app_settings.json
├── app_settings.json          # Stores Google Sheet ID and Service Account JSON (auto-generated, in .gitignore)
├── requirements.txt           # Python dependencies
├── .gitignore                 # Specifies intentionally untracked files
├── static/                    # Static files (CSS, JS)
│   └── .gitkeep
└── templates/                 # HTML templates
    ├── add_item.html          # Page to add new items
    ├── home.html              # Home page
    ├── layout.html            # Base HTML layout
    ├── scan.html              # Page to scan items and update inventory
    ├── lookup.html            # Page to lookup item details
    └── setup.html             # Initial setup page for Google Sheets configuration
```

## Setup and Installation

### 1. Prerequisites (Google Cloud Platform & Google Sheet)

Before running the application for the first time, you need to set up Google Cloud Platform and a Google Sheet:

1.  **Create a Google Cloud Platform (GCP) Project:** Or use an existing one.
2.  **Enable the Google Sheets API:**
    *   In GCP Console: APIs & Services &rarr; Library &rarr; Search "Google Sheets API" &rarr; Enable.
3.  **Create a Service Account:**
    *   In GCP Console: APIs & Services &rarr; Credentials &rarr; + CREATE CREDENTIALS &rarr; Service account.
    *   Give it a name (e.g., "inventory-app-scanner"). Click "CREATE AND CONTINUE", then "DONE".
4.  **Generate a JSON Key for the Service Account:**
    *   Click on your new service account &rarr; KEYS tab &rarr; ADD KEY &rarr; Create new key &rarr; Select JSON &rarr; CREATE.
    *   A JSON file will download. **You will need the entire content of this file for the application setup.**
5.  **Create a Google Sheet:**
    *   Go to [Google Sheets](https://sheets.google.com/) and create a new blank spreadsheet (e.g., name it "WebAppInventory").
    *   Note the **Google Sheet ID** from its URL: `https://docs.google.com/spreadsheets/d/SHEET_ID_IS_HERE/edit`.
6.  **Share the Google Sheet with the Service Account:**
    *   In your Google Sheet, click "Share" (top right).
    *   Find the `client_email` address in the downloaded JSON key file (e.g., `your-service-account-name@your-project-id.iam.gserviceaccount.com`).
    *   Paste this email into the "Add people or groups" field, give it **Editor** permissions, and click "Send" (uncheck "Notify people" if desired).

### 2. Application Installation

1.  **Clone the repository (or download the files):**
    ```bash
    # git clone <repository_url>
    # cd <repository_directory>
    ```

2.  **Ensure Python 3.x is installed.**

3.  **Create a virtual environment (recommended):**
    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows: venv\Scripts\activate
    ```

4.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```
    This will install Flask, Pandas, and Google API client libraries.

## Running the Application

1.  **Start the Flask development server:**
    ```bash
    python app.py
    ```
    The application will run on `http://localhost:5000` by default (or `http://0.0.0.0:5000`).

2.  **Initial Setup via Web UI:**
    *   When you first open the application in your browser, if it's not configured, you will be redirected to a setup page (`/setup`).
    *   Enter the **Google Sheet ID** and the **full content of the Service Account JSON key file** into the form.
    *   Click "Save Configuration & Test Connection".
    *   If successful, the settings will be saved locally in `app_settings.json` (this file is in `.gitignore` and should not be committed if you're using Git). The application will then be ready to use.
    *   The `app_settings.json` file stores your credentials locally on the server running the app. Ensure this server is secure.

3.  **Access the Application:**
    *   Open your web browser and navigate to `http://localhost:5000` (or your server's IP and port).

## Usage

*   **Home Page:** Provides navigation to "Scan Items", "Add New Item", and "Lookup Item".
*   **Scan Items:**
    *   Select mode: "Add Stock" or "Remove Stock".
    *   The barcode input field will be auto-focused. Scan a barcode (or type it manually).
    *   Enter the quantity (defaults to 1).
    *   Click "Update Inventory". The page will show a confirmation and the updated stock.
*   **Add New Item:**
    *   Fill in the barcode, item name, and starting quantity.
    *   Click "Add Item".
*   **Lookup Item:**
    *   Enter a barcode to view its details (Name, Quantity, Last Updated).

The Google Sheet will contain two sheets:
*   `Inventory`: Columns `Barcode`, `Name`, `Quantity`, `Last Updated`.
*   `Log`: Columns `Timestamp`, `Barcode`, `Action`, `Details`, `User`.
These sheets and headers will be automatically created if they don't exist when the application first successfully connects after setup.

## Deployment (Basic)

For a more permanent setup (e.g., on a Raspberry Pi or local server):

*   Ensure `app_settings.json` is configured correctly on the server.
*   You can run the Flask app using a production-ready WSGI server like Gunicorn or Waitress. Example with Gunicorn:
    ```bash
    gunicorn --bind 0.0.0.0:5000 app:app
    ```
*   **Autostart:**
    *   **Linux (systemd):** Create a systemd service file to manage the application and start it on boot.
    *   **Windows (Task Scheduler):** Create a task that runs the python/gunicorn command when the system starts.

## Technology Stack

*   **Backend:** Python, Flask
*   **Data Storage:** Google Sheets API
*   **Google API Interaction:** `google-api-python-client`, `google-auth-oauthlib`, `google-auth-httplib2`
*   **Frontend:** HTML, Bootstrap
*   **Barcode Input:** Standard HTML input field (works with USB scanners that emulate keyboard input).

## Future Enhancements (Ideas)

*   Live Lookup Page: Display all items in a searchable table.
*   User Authentication.
*   Automatic Google Sheet Backups (though Google Sheets has version history).
*   REST API Mode for mobile app integration.
*   CSV Export/Import functionality directly with the Google Sheet.
*   Low stock alerts.
*   Mobile-responsive improvements.
```
