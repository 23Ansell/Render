# Imports
from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
import uuid
from datetime import datetime
import os
from dotenv import load_dotenv
import requests
from datetime import datetime, date, timedelta
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address


# Load environment variables
load_dotenv()


# Flask app setup
app = Flask(__name__)
app.secret_key = uuid.uuid4().hex


# OpenWeatherMap API key
API_KEY = os.getenv('OpenWeatherMap_API_KEY')


limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://"
)


# Function to check if user is logged in
def is_logged_in():
    print("Checking login status:", 'user_id' in session)  # Debug line
    return 'user_id' in session


# Function to get database connection
def get_db_connection():
    db_path = 'database.db'
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


@app.route('/')
@limiter.limit("100 per day")
def index():
    return render_template('index.html', is_logged_in=is_logged_in)


@app.route('/register', methods=['GET', 'POST'])
@limiter.limit("20 per minute")
def register():
    if request.method == 'POST':
        try:
            # Collecting form data
            full_name = request.form['name']
            email = request.form['email']
            password = request.form['password']
            age = request.form.get('age')

            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Checking if email is already registered
            cursor.execute('SELECT * FROM users WHERE email = ?', (email,))
            existing_user = cursor.fetchone()
            
            if existing_user:
                flash('Email already registered. Please use a different email or log in.', 'danger')
                conn.close()
                return redirect(url_for('register'))

            # Hashing password and inserting user data into database
            hashed_password = generate_password_hash(password)
            cursor.execute('INSERT INTO users (full_name, email, password, age) VALUES (?, ?, ?, ?)',
                         (full_name, email, hashed_password, age))
            conn.commit()
            conn.close()
            
            flash('You are now registered and can log in', 'success')
            return redirect(url_for('login'))
        
        except sqlite3.Error as e:
            flash(f'Database error: {str(e)}', 'danger')
            return redirect(url_for('register'))
    
    return render_template('register.html', is_logged_in=is_logged_in)


@app.route('/login', methods=['GET', 'POST'])
@limiter.limit("30 per minute")
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE email = ?', (email,))
        user = cursor.fetchone()
        conn.close()

        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['full_name'] = user['full_name']
            flash('You are now logged in', 'success')
            return redirect(url_for('index'))
        else:
            flash('Login unsuccessful. Please check email and password', 'danger')
            return redirect(url_for('login'))
    return render_template('login.html', is_logged_in=is_logged_in)


@app.route('/logout')
def logout():
    session.clear()
    flash('You are now logged out', 'success')

    return redirect(url_for('index'))


@app.route('/advice')
def advice():
    return render_template('advice.html', is_logged_in=is_logged_in)


@app.route('/account')
def account():
    return render_template('account.html', is_logged_in=is_logged_in)


# Booking page for risk assessments
@app.route('/risk_assessments', methods=['GET', 'POST'])
@limiter.limit("40 per minute")
def risk_assessments():
    if not is_logged_in():
        flash('Please login to access this page', 'danger')
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        if 'cancel_booking_id' in request.form:
            booking_id = request.form['cancel_booking_id']
            user_id = session['user_id']
            
            conn = get_db_connection()
            cursor = conn.cursor()
            
            try:
                cursor.execute('DELETE FROM assessmentBookings WHERE id = ? AND user_id = ?', 
                             (booking_id, user_id))
                conn.commit()
                flash('Booking cancelled successfully!', 'success')
            except sqlite3.Error as e:
                flash(f'Error cancelling booking: {str(e)}', 'danger')
            finally:
                conn.close()
        else:
            booking_date = request.form['booking_date']
            address = request.form['address']
            user_id = session['user_id']
            
            conn = get_db_connection()
            cursor = conn.cursor()
            
            try:
                cursor.execute('''
                    INSERT INTO assessmentBookings (user_id, booking_date, address)
                    VALUES (?, ?, ?)
                ''', (user_id, booking_date, address))
                conn.commit()
                flash('Assessment booked successfully!', 'success')
            except sqlite3.IntegrityError:
                flash('You already have a booking for this date', 'danger')
            except sqlite3.Error as e:
                flash(f'Error creating booking: {str(e)}', 'danger')
            finally:
                conn.close()
        
        return redirect(url_for('risk_assessments'))

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, booking_date, address 
        FROM assessmentBookings 
        WHERE user_id = ? 
        ORDER BY booking_date
    ''', (session['user_id'],))
    bookings = cursor.fetchall()
    conn.close()
    
    return render_template('risk_assessments.html', 
                         is_logged_in=is_logged_in, 
                         today_date=(date.today() + timedelta(days=1)).isoformat(), 
                         bookings=bookings)


@app.route('/health_tracking_tool')
def health_tracking_tool():
    if is_logged_in():
        return render_template('health_tracking_tool.html', is_logged_in=is_logged_in)
    else:
        flash('Please log in to access this page', 'danger')
        return redirect(url_for('login'))


@app.route('/weather_forecast')
@limiter.limit("60 per minute")
def weather_forecast():
    city = request.args.get('city', 'London')
    url = f'https://api.openweathermap.org/data/2.5/forecast?q={city}&appid={API_KEY}&units=metric'
    
    try:
        response = requests.get(url)
        if response.status_code == 200:
            forecast_data = response.json()
            forecasts = {}
            for item in forecast_data['list']:
                date = datetime.fromtimestamp(item['dt']).strftime('%d/%m/%Y')
                if date not in forecasts:
                    forecasts[date] = []
                forecasts[date].append({
                    'time': datetime.fromtimestamp(item['dt']).strftime('%H:%M'),
                    'temp': round(item['main']['temp']),
                    'humidity': item['main']['humidity'],
                    'wind': round(item['wind']['speed'] * 3.6),
                    'description': item['weather'][0]['main'],
                    'icon': item['weather'][0]['main'].lower()
                })
            return render_template('weather_forecast.html', 
                                 is_logged_in=is_logged_in, 
                                 city=city, 
                                 forecasts=forecasts, 
                                 error=None)
        else:
            return render_template('weather_forecast.html', 
                                 is_logged_in=is_logged_in, 
                                 error="City not found")
    except requests.RequestException:
        return render_template('weather_forecast.html', 
                             is_logged_in=is_logged_in, 
                             error="Could not fetch weather data")


# Add error handler for rate limiting
@app.errorhandler(429)
def ratelimit_handler(e):
    flash("Too many requests. Please try again later.", "danger")
    return redirect(url_for('index')), 429


@app.route('/health')
def health_check():
    return 'OK', 200


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')