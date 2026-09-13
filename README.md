# Local Services Hub

A simple zero-cost web application for a small remote city where:

- Admin manages users and approves or rejects services
- Customers can browse approved services
- Providers can register, list services, and manage their own listings

## Features

- Role-based login and registration
- SQLite database stored locally
- Provider service submission with pending approval
- Admin approval, rejection, and status updates
- Simple Bootstrap-based UI

## Default Admin Account

- Username: `admin`
- Password: `admin123`

## Run Locally

1. Open a terminal in this folder
2. Install dependencies:
   ```bash
   python -m pip install -r requirements.txt
   ```
3. Start the app:
   ```bash
   python app.py
   ```
4. Open:
   - http://127.0.0.1:5000

## Notes

- Data is stored in `local_services.db`
- The app is built for local/demo use and uses Flask's built-in development server
- For production use, you would later move to a proper hosting setup and a stronger deployment configuration
