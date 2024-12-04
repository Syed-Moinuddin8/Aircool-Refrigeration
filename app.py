from flask import Flask, render_template, request, redirect, url_for, session, flash
import sqlite3
import smtplib
from datetime import datetime

app = Flask(__name__)
app.secret_key = "your_secret_key"

# Database setup
DATABASE = 'database.db'
ADMIN_PASSWORD = "RICH_DAD"  # Change this to your secure password


# Initialize the database
def init_db():
    with sqlite3.connect(DATABASE) as conn:
        cursor = conn.cursor()

        # Create the new table with the updated schema
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS temp_bookings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT NOT NULL,
                phone TEXT NOT NULL,
                service TEXT NOT NULL,
                service_date TEXT NOT NULL,  -- Renamed column
                address TEXT NOT NULL,
                booking_date TEXT DEFAULT CURRENT_TIMESTAMP,
                is_checked INTEGER DEFAULT 0
            )
        ''')

        # Check if the original `bookings` table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='bookings'")
        if cursor.fetchone():
            # Check if `booking_date` exists in the original table
            cursor.execute("PRAGMA table_info(bookings)")
            columns = [col[1] for col in cursor.fetchall()]  # Get column names from the original table

            if "booking_date" not in columns:
                # If `booking_date` doesn't exist, use CURRENT_TIMESTAMP for new column
                cursor.execute('''
                    INSERT INTO temp_bookings (id, name, email, phone, service, service_date, address, booking_date, is_checked)
                    SELECT id, name, email, phone, service, date, address, CURRENT_TIMESTAMP, 0
                    FROM bookings
                ''')
            else:
                # If `booking_date` exists, copy the data directly
                cursor.execute('''
                    INSERT INTO temp_bookings (id, name, email, phone, service, service_date, address, booking_date, is_checked)
                    SELECT id, name, email, phone, service, service_date, address, booking_date, is_checked
                    FROM bookings
                ''')

        # Drop the old `bookings` table
        cursor.execute('DROP TABLE IF EXISTS bookings')

        # Rename the temporary table to `bookings`
        cursor.execute('ALTER TABLE temp_bookings RENAME TO bookings')

    print("Database schema updated successfully.")


# Send email notification
def send_email_notification(name, email, phone, service, service_date, address):
    host_email = "youremail@example.com"
    host_password = "yourpassword"

    message = f"""\
Subject: New AC Service Booking
New service booking received:
- Name: {name}
- Email: {email}
- Phone: {phone}
- Service: {service}
- Date: {service_date}
- Address: {address}
"""

    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(host_email, host_password)
            server.sendmail(host_email, host_email, message)
    except Exception as e:
        print("Error sending email:", e)


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/book', methods=['GET', 'POST'])
def book():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        phone = request.form['phone']
        service = request.form['service']
        service_date = request.form['date']  # Updated to match the new column
        address = request.form['address']

        if not all([name, email, phone, service, service_date, address]):
            flash('All fields are required!', 'danger')
            return redirect(url_for('book'))

        # Save to database
        try:
            with sqlite3.connect(DATABASE) as conn:
                cursor = conn.cursor()
                cursor.execute('''INSERT INTO bookings (name, email, phone, service, service_date, address)
                                  VALUES (?, ?, ?, ?, ?, ?)''', (name, email, phone, service, service_date, address))
                conn.commit()
        except Exception as e:
            flash(f"An error occurred: {e}", 'danger')
            return redirect(url_for('book'))

        # Send email notification
        send_email_notification(name, email, phone, service, service_date, address)

        flash('Your booking has been confirmed!', 'success')
        return redirect(url_for('success'))

    return render_template('booking.html')

@app.route('/bookings', methods=['GET'])
def bookings():
    search_query = request.args.get('search', '').strip()  # Get the search query from the request
    results = []

    try:
        with sqlite3.connect(DATABASE) as conn:
            cursor = conn.cursor()
            
            if search_query:
                # Search in name, email, phone, or service columns
                cursor.execute('''
                    SELECT * FROM bookings
                    WHERE name LIKE ? OR email LIKE ? OR phone LIKE ? OR service LIKE ?
                ''', (f'%{search_query}%', f'%{search_query}%', f'%{search_query}%', f'%{search_query}%'))
            else:
                # If no search query, retrieve all records
                cursor.execute("SELECT * FROM bookings")
            
            results = cursor.fetchall()
    except Exception as e:
        flash(f"Error fetching bookings: {e}", 'danger')

    return render_template('admin.html', bookings=results, search_query=search_query)

@app.route('/success')
def success():
    return render_template('success.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        password = request.form['password']
        if password == ADMIN_PASSWORD:
            session['logged_in'] = True
            flash('Login successful!', 'success')
            return redirect(url_for('admin'))
        else:
            flash('Invalid password. Try again.', 'danger')
    return render_template('login.html')


@app.route('/admin')
def admin():
    if not session.get('logged_in'):
        flash('You must log in to access this page.', 'warning')
        return redirect(url_for('login'))

    with sqlite3.connect(DATABASE) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM bookings")
        bookings = cursor.fetchall()

    return render_template('admin.html', bookings=bookings)


@app.route('/delete_booking', methods=['POST'])
def delete_booking():
    booking_id = request.form.get('booking_id', '').strip()
    if not booking_id.isdigit():
        flash('Invalid booking ID.', 'danger')
        return redirect(url_for('admin'))

    try:
        with sqlite3.connect(DATABASE) as conn:
            cursor = conn.cursor()

            # Delete the booking with the given ID
            cursor.execute("DELETE FROM bookings WHERE id = ?", (int(booking_id),))
            
            # Shift all subsequent IDs down by 1
            cursor.execute("""
                UPDATE bookings
                SET id = id - 1
                WHERE id > ? 
            """, (int(booking_id),))

            # Reset the primary key sequence (only relevant for SQLite's auto-increment)
            cursor.execute("DELETE FROM sqlite_sequence WHERE name = 'bookings'")
            conn.commit()

        flash('Booking deleted and IDs updated successfully.', 'success')
    except Exception as e:
        flash(f"An error occurred: {e}", 'danger')

    return redirect(url_for('admin'))


@app.route('/update_checkboxes', methods=['POST'])
def update_checkboxes():
    try:
        selected_ids = request.form.getlist('select_booking')

        # Ensure selected_ids are valid integers
        selected_ids = [int(id) for id in selected_ids if id.isdigit()]

        with sqlite3.connect(DATABASE) as conn:
            cursor = conn.cursor()

            # Reset only rows that are currently checked
            cursor.execute("UPDATE bookings SET is_checked = 0 WHERE is_checked = 1")

            # Mark selected checkboxes as checked, if any are provided
            if selected_ids:
                placeholders = ','.join(['?'] * len(selected_ids))
                query = f"UPDATE bookings SET is_checked = 1 WHERE id IN ({placeholders})"
                cursor.execute(query, selected_ids)

            conn.commit()

        flash('Checkbox statuses updated successfully.', 'success')
    except Exception as e:
        # Log the exception for debugging
        app.logger.error(f"Error updating checkboxes: {e}")
        flash("An unexpected error occurred while updating checkboxes. Please try again.", 'danger')

    return redirect(url_for('admin'))





@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    flash('You have been logged out.', 'success')
    return redirect(url_for('login'))


if __name__ == '__main__':
    init_db()
    app.run(debug=True)
