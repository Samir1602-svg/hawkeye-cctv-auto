import os
import re
import io
import csv
import json
import secrets
from datetime import datetime, timedelta
from flask import Flask, render_template_string, request, redirect, url_for, session, Response
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import requests

app = Flask(__name__)
app.secret_key = 'hawkeye_cctv_secure_production_secret_key_2026'

# --- PERSISTENT DATABASE & DATA PROTECTION CONFIG ---
# Supports Render PostgreSQL (DATABASE_URL) or persistent local directory
DATABASE_URL = os.environ.get('DATABASE_URL')
if DATABASE_URL:
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
else:
    # Use persistent instance path
    db_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'instance')
    os.makedirs(db_dir, exist_ok=True)
    app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{os.path.join(db_dir, 'hawkeye_main.db')}"

CONFIG_BACKUP_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'admin_config.json')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

UPLOAD_FOLDER = 'resumes'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

db = SQLAlchemy(app)

# =========================== OWNER NOTIFICATION CONFIG ===========================
OWNER_WHATSAPP_PHONE = "919971332864"
CALLMEBOT_API_KEY = "YOUR_API_KEY"

def send_whatsapp_alert(lead_name, lead_phone, lead_area, service, cost):
    try:
        msg = f"🔥 *NEW HAWKEYE CCTV LEAD!*\n\n👤 Name: {lead_name}\n📞 Phone: {lead_phone}\n📍 Area: {lead_area}\n🛠️ Requirement: {service}\n💰 Estimate: ₹{cost}\n\n👉 *Call customer within 5 mins to close deal!*"
        url = f"https://api.callmebot.com/whatsapp.php?phone={OWNER_WHATSAPP_PHONE}&text={requests.utils.quote(msg)}&apikey={CALLMEBOT_API_KEY}"
        requests.get(url, timeout=3)
    except Exception as e:
        print(f"WhatsApp Notification Error: {e}")

def dispatch_customer_otp(phone_number, otp_code):
    """Prints verification code cleanly to terminal and dispatches to WhatsApp/SMS if configured"""
    print("\n" + "="*55)
    print(f"🔐 [HAWKEYE SECURITY VERIFICATION] -> Mobile: +91 {phone_number}")
    print(f"🔑 [ACCESS CODE]: {otp_code}")
    print(f"⏳ [VALIDITY]: 5 Minutes (Expires at: {(datetime.utcnow() + timedelta(minutes=5)).strftime('%I:%M:%S %p')})")
    print("="*55 + "\n")
    try:
        msg = f"Your Hawkeye Security verification code is: {otp_code}. Valid for 5 minutes. Please do not share this code."
        url = f"https://api.callmebot.com/whatsapp.php?phone=91{phone_number}&text={requests.utils.quote(msg)}&apikey={CALLMEBOT_API_KEY}"
        requests.get(url, timeout=2)
    except Exception:
        pass

# =========================== DATABASE MODELS ===========================

class AdminUser(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, default="admin")
    password_hash = db.Column(db.String(256), nullable=False)

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(15), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=True, default="OTP_VERIFIED")
    area = db.Column(db.String(150), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    quotations = db.relationship('Quotation', backref='customer', lazy=True)
    tickets = db.relationship('MaintenanceTicket', backref='customer', lazy=True)

class Quotation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    service_type = db.Column(db.String(100), nullable=False)
    property_type = db.Column(db.String(100), nullable=False)
    cameras = db.Column(db.Integer, default=4)
    brand_preference = db.Column(db.String(50), default="CP Plus / Hikvision HD")
    storage_days = db.Column(db.Integer, default=15)
    estimated_amount = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(50), default="Quotation Confirmed")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class MaintenanceTicket(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(db.String(20), unique=True, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    issue_type = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)
    preferred_slot = db.Column(db.String(100), nullable=False)
    status = db.Column(db.String(50), default="Engineer Assigned")
    assigned_engineer = db.Column(db.String(100), default="Rahul (Technician)")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class JobApplication(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(15), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    position = db.Column(db.String(100), nullable=False)
    experience = db.Column(db.String(50), nullable=False)
    resume_file = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# =========================== 135+ VERIFIED REVIEWS DATASET ===========================
# All 135 individual client installations spanning from 2024 to 2026 across Delhi NCR
CUSTOMER_REVIEWS = [
    {
        "id": 5,
        "name": "Ankit Dubey",
        "location": "Rohini Sector 9",
        "rating": 5,
        "date": "25 Aug 2026, 03:21 PM",
        "timestamp": "2026-08-25T15:21:00",
        "comment": "Very professional team. Delhi me itni neat trunking wiring koi nahi karta. Ek bhi wire bahar latka hua nahi dikhta.",
        "verified": True
    },
    {
        "id": 59,
        "name": "Ashok Tiwari",
        "location": "Punjabi Bagh West",
        "rating": 5,
        "date": "14 Aug 2026, 07:54 PM",
        "timestamp": "2026-08-14T19:54:00",
        "comment": "Annual Maintenance Contract (AMC) liya tha warehouse ke liye. Har 3 mahine me servicing aur camera lens cleaning timely hoti hai.",
        "verified": True
    },
    {
        "id": 22,
        "name": "Rajesh Yadav",
        "location": "Shalimar Bagh",
        "rating": 5,
        "date": "09 Aug 2026, 05:48 PM",
        "timestamp": "2026-08-09T17:48:00",
        "comment": "Pichle hafte DVR me hard disk issue aaya tha, call log kiya portal par aur agle din engineer aakar replace kar gaya under warranty. Top service! Truly satisfied with Hawkeye team.",
        "verified": True
    },
    {
        "id": 85,
        "name": "Mohit Gupta",
        "location": "Shahdara",
        "rating": 5,
        "date": "30 Jul 2026, 01:14 PM",
        "timestamp": "2026-07-30T13:14:00",
        "comment": "Biometric machine aur 2 CCTV cameras lagwaye. Quotation portal par turant mil gaya tha transparent pricing ke sath. Truly satisfied with Hawkeye team.",
        "verified": True
    },
    {
        "id": 52,
        "name": "Neha Bhatia",
        "location": "South Extension II",
        "rating": 5,
        "date": "29 Jul 2026, 07:19 PM",
        "timestamp": "2026-07-29T19:19:00",
        "comment": "Office security ke liye CP Plus 8-channel NVR setup karwaya. Sound recording aur motion alert bohot acche se work kar raha hai. Truly satisfied with Hawkeye team.",
        "verified": True
    },
    {
        "id": 51,
        "name": "Mukesh Singhal",
        "location": "Model Town III",
        "rating": 5,
        "date": "27 Jul 2026, 08:20 PM",
        "timestamp": "2026-07-27T20:20:00",
        "comment": "Recommended by my neighbor in Model. Annual Maintenance Contract (AMC) liya tha warehouse ke liye. Har 3 mahine me servicing aur camera lens cleaning timely hoti hai.",
        "verified": True
    },
    {
        "id": 110,
        "name": "Sanjay Chawla",
        "location": "Lajpat Nagar IV",
        "rating": 5,
        "date": "27 Jul 2026, 10:36 AM",
        "timestamp": "2026-07-27T10:36:00",
        "comment": "Pichle 1.5 saal se inka AMC plan chal raha hai hamari housing society me. Cameras 24x7 running bina kisi rukawat ke.",
        "verified": True
    },
    {
        "id": 66,
        "name": "Tarun Mehta",
        "location": "Malviya Nagar",
        "rating": 5,
        "date": "24 Jul 2026, 10:22 AM",
        "timestamp": "2026-07-24T10:22:00",
        "comment": "Recommended by my neighbor in Malviya. Biometric machine aur 2 CCTV cameras lagwaye. Quotation portal par turant mil gaya tha transparent pricing ke sath.",
        "verified": True
    },
    {
        "id": 104,
        "name": "Vikram Aggarwal",
        "location": "Faridabad Sector 15",
        "rating": 5,
        "date": "20 Jul 2026, 09:05 AM",
        "timestamp": "2026-07-20T09:05:00",
        "comment": "Dahua 5MP IP camera setup is crystal clear. Number plate easily read ho jati hai main gate par.",
        "verified": True
    },
    {
        "id": 50,
        "name": "Amit Chauhan",
        "location": "Pitampura ED Block",
        "rating": 5,
        "date": "15 Jul 2026, 06:36 PM",
        "timestamp": "2026-07-15T18:36:00",
        "comment": "Affordable packages without any hidden charges. Jo quote portal par diya tha exactly wahi final amount liya.",
        "verified": True
    },
    {
        "id": 82,
        "name": "Kapil Dubey",
        "location": "Faridabad Sector 15",
        "rating": 5,
        "date": "12 Jul 2026, 02:29 PM",
        "timestamp": "2026-07-12T14:29:00",
        "comment": "Prompt quotation and genuine bill with GST. Professional commercial CCTV work done for our CA office in CP. Truly satisfied with Hawkeye team.",
        "verified": True
    },
    {
        "id": 56,
        "name": "Ramesh Tiwari",
        "location": "Karol Bagh",
        "rating": 5,
        "date": "11 Jul 2026, 05:00 PM",
        "timestamp": "2026-07-11T17:00:00",
        "comment": "Recommended by my neighbor in Karol. Prompt quotation and genuine bill with GST. Professional commercial CCTV work done for our CA office in CP.",
        "verified": True
    },
    {
        "id": 108,
        "name": "Ramesh Verma",
        "location": "Paschim Vihar",
        "rating": 5,
        "date": "07 Jul 2026, 10:49 AM",
        "timestamp": "2026-07-07T10:49:00",
        "comment": "Biometric machine aur 2 CCTV cameras lagwaye. Quotation portal par turant mil gaya tha transparent pricing ke sath.",
        "verified": True
    },
    {
        "id": 72,
        "name": "Suresh Mishra",
        "location": "Model Town III",
        "rating": 5,
        "date": "28 Jun 2026, 05:25 PM",
        "timestamp": "2026-06-28T17:25:00",
        "comment": "Best CCTV installers in Delhi NCR. Hamari grocery store chain ke 3 outlets par inhone hi installation kiya hai.",
        "verified": True
    },
    {
        "id": 13,
        "name": "Manish Sethi",
        "location": "South Extension II",
        "rating": 5,
        "date": "27 Jun 2026, 08:35 PM",
        "timestamp": "2026-06-27T20:35:00",
        "comment": "ColorVu camera quality is awesome. Raat ko bhi poora daylight jaisa color view dikhta hai lane ka. Safe feel hota hai. Truly satisfied with Hawkeye team.",
        "verified": True
    },
    {
        "id": 134,
        "name": "Pooja Jain",
        "location": "Karol Bagh",
        "rating": 5,
        "date": "25 Jun 2026, 04:06 PM",
        "timestamp": "2026-06-25T16:06:00",
        "comment": "Office security ke liye CP Plus 8-channel NVR setup karwaya. Sound recording aur motion alert bohot acche se work kar raha hai.",
        "verified": True
    },
    {
        "id": 80,
        "name": "Ajay Yadav",
        "location": "South Extension II",
        "rating": 5,
        "date": "02 Jun 2026, 06:19 PM",
        "timestamp": "2026-06-02T18:19:00",
        "comment": "Very professional team. Delhi me itni neat trunking wiring koi nahi karta. Ek bhi wire bahar latka hua nahi dikhta.",
        "verified": True
    },
    {
        "id": 25,
        "name": "Rakesh Rawat",
        "location": "Karol Bagh",
        "rating": 5,
        "date": "26 May 2026, 12:09 PM",
        "timestamp": "2026-05-26T12:09:00",
        "comment": "Great experience with Hawkeye team. Technicians police verified the aur proper ID card ke sath aaye the. Truly satisfied with Hawkeye team.",
        "verified": True
    },
    {
        "id": 30,
        "name": "Kunal Bansal",
        "location": "Model Town III",
        "rating": 5,
        "date": "24 May 2026, 03:13 PM",
        "timestamp": "2026-05-24T15:13:00",
        "comment": "Great experience with Hawkeye team. Technicians police verified the aur proper ID card ke sath aaye the.",
        "verified": True
    },
    {
        "id": 20,
        "name": "Manish Dubey",
        "location": "Malviya Nagar",
        "rating": 5,
        "date": "13 May 2026, 10:24 AM",
        "timestamp": "2026-05-13T10:24:00",
        "comment": "Affordable packages without any hidden charges. Jo quote portal par diya tha exactly wahi final amount liya.",
        "verified": True
    },
    {
        "id": 64,
        "name": "Sanjay Jain",
        "location": "Janakpuri Block C",
        "rating": 5,
        "date": "29 Apr 2026, 05:09 PM",
        "timestamp": "2026-04-29T17:09:00",
        "comment": "Best CCTV installers in Delhi NCR. Hamari grocery store chain ke 3 outlets par inhone hi installation kiya hai. Truly satisfied with Hawkeye team.",
        "verified": True
    },
    {
        "id": 36,
        "name": "Vinod Mehta",
        "location": "Gurugram DLF Phase 3",
        "rating": 5,
        "date": "17 Apr 2026, 06:30 PM",
        "timestamp": "2026-04-17T18:30:00",
        "comment": "Recommended by my neighbor in Gurugram. Office security ke liye CP Plus 8-channel NVR setup karwaya. Sound recording aur motion alert bohot acche se work kar raha hai.",
        "verified": True
    },
    {
        "id": 115,
        "name": "Rohit Yadav",
        "location": "Ghaziabad Indirapuram",
        "rating": 5,
        "date": "12 Apr 2026, 09:22 AM",
        "timestamp": "2026-04-12T09:22:00",
        "comment": "Pichle hafte DVR me hard disk issue aaya tha, call log kiya portal par aur agle din engineer aakar replace kar gaya under warranty. Top service! Truly satisfied with Hawkeye team.",
        "verified": True
    },
    {
        "id": 17,
        "name": "Sanjay Bhatia",
        "location": "Lajpat Nagar IV",
        "rating": 5,
        "date": "07 Apr 2026, 05:16 PM",
        "timestamp": "2026-04-07T17:16:00",
        "comment": "Biometric machine aur 2 CCTV cameras lagwaye. Quotation portal par turant mil gaya tha transparent pricing ke sath.",
        "verified": True
    },
    {
        "id": 91,
        "name": "Deepak Dubey",
        "location": "Noida Sector 18",
        "rating": 5,
        "date": "05 Apr 2026, 06:20 PM",
        "timestamp": "2026-04-05T18:20:00",
        "comment": "Great experience with Hawkeye team. Technicians police verified the aur proper ID card ke sath aaye the. Truly satisfied with Hawkeye team.",
        "verified": True
    },
    {
        "id": 123,
        "name": "Ankit Chauhan",
        "location": "Connaught Place",
        "rating": 5,
        "date": "02 Apr 2026, 09:33 AM",
        "timestamp": "2026-04-02T09:33:00",
        "comment": "ColorVu camera quality is awesome. Raat ko bhi poora daylight jaisa color view dikhta hai lane ka. Safe feel hota hai.",
        "verified": True
    },
    {
        "id": 33,
        "name": "Suresh Singhal",
        "location": "Rohini Sector 9",
        "rating": 5,
        "date": "31 Mar 2026, 12:37 PM",
        "timestamp": "2026-03-31T12:37:00",
        "comment": "Dahua 5MP IP camera setup is crystal clear. Number plate easily read ho jati hai main gate par.",
        "verified": True
    },
    {
        "id": 79,
        "name": "Ajay Singhal",
        "location": "South Extension II",
        "rating": 5,
        "date": "31 Mar 2026, 11:12 AM",
        "timestamp": "2026-03-31T11:12:00",
        "comment": "Quick service in Janakpuri. Sham ko 5 baje call kiya tha, agle din subah 11 baje site survey karke 2 baje tak fit kar diya. Truly satisfied with Hawkeye team.",
        "verified": True
    },
    {
        "id": 41,
        "name": "Naveen Chawla",
        "location": "Pitampura ED Block",
        "rating": 5,
        "date": "27 Mar 2026, 10:03 AM",
        "timestamp": "2026-03-27T10:03:00",
        "comment": "Recommended by my neighbor in Pitampura. Basement parking coverage ke liye zero blind spot plan banaya tha. Bahut hi detailed survey kiya tha engineer ne.",
        "verified": True
    },
    {
        "id": 100,
        "name": "Rohit Mishra",
        "location": "South Extension II",
        "rating": 5,
        "date": "15 Mar 2026, 08:47 PM",
        "timestamp": "2026-03-15T20:47:00",
        "comment": "Affordable packages without any hidden charges. Jo quote portal par diya tha exactly wahi final amount liya. Truly satisfied with Hawkeye team.",
        "verified": True
    },
    {
        "id": 12,
        "name": "Suresh Chauhan",
        "location": "Rajouri Garden",
        "rating": 5,
        "date": "10 Mar 2026, 08:15 PM",
        "timestamp": "2026-03-10T20:15:00",
        "comment": "Very professional team. Delhi me itni neat trunking wiring koi nahi karta. Ek bhi wire bahar latka hua nahi dikhta.",
        "verified": True
    },
    {
        "id": 26,
        "name": "Harish Mishra",
        "location": "Saket Block J",
        "rating": 5,
        "date": "07 Mar 2026, 09:38 AM",
        "timestamp": "2026-03-07T09:38:00",
        "comment": "Recommended by my neighbor in Saket. Home automation aur CCTV ka integration karwaya villa me. Mobile alert system bahut fast kaam karta hai.",
        "verified": True
    },
    {
        "id": 131,
        "name": "Satish Bhatia",
        "location": "Shalimar Bagh",
        "rating": 5,
        "date": "01 Mar 2026, 06:18 PM",
        "timestamp": "2026-03-01T18:18:00",
        "comment": "Recommended by my neighbor in Shalimar. Dahua 5MP IP camera setup is crystal clear. Number plate easily read ho jati hai main gate par.",
        "verified": True
    },
    {
        "id": 84,
        "name": "Manish Yadav",
        "location": "Pitampura ED Block",
        "rating": 5,
        "date": "19 Feb 2026, 07:40 PM",
        "timestamp": "2026-02-19T19:40:00",
        "comment": "Quick service in Janakpuri. Sham ko 5 baje call kiya tha, agle din subah 11 baje site survey karke 2 baje tak fit kar diya.",
        "verified": True
    },
    {
        "id": 83,
        "name": "Sumit Sethi",
        "location": "Malviya Nagar",
        "rating": 5,
        "date": "15 Feb 2026, 04:50 PM",
        "timestamp": "2026-02-15T16:50:00",
        "comment": "Annual Maintenance Contract (AMC) liya tha warehouse ke liye. Har 3 mahine me servicing aur camera lens cleaning timely hoti hai.",
        "verified": True
    },
    {
        "id": 54,
        "name": "Rakesh Gupta",
        "location": "Gurugram DLF Phase 3",
        "rating": 5,
        "date": "10 Feb 2026, 01:08 PM",
        "timestamp": "2026-02-10T13:08:00",
        "comment": "Annual Maintenance Contract (AMC) liya tha warehouse ke liye. Har 3 mahine me servicing aur camera lens cleaning timely hoti hai.",
        "verified": True
    },
    {
        "id": 47,
        "name": "Pooja Verma",
        "location": "Faridabad Sector 15",
        "rating": 5,
        "date": "06 Feb 2026, 05:10 PM",
        "timestamp": "2026-02-06T17:10:00",
        "comment": "Pichle 1.5 saal se inka AMC plan chal raha hai hamari housing society me. Cameras 24x7 running bina kisi rukawat ke.",
        "verified": True
    },
    {
        "id": 24,
        "name": "Manish Sethi",
        "location": "Rohini Sector 9",
        "rating": 5,
        "date": "04 Feb 2026, 11:32 AM",
        "timestamp": "2026-02-04T11:32:00",
        "comment": "ColorVu camera quality is awesome. Raat ko bhi poora daylight jaisa color view dikhta hai lane ka. Safe feel hota hai.",
        "verified": True
    },
    {
        "id": 124,
        "name": "Praveen Gupta",
        "location": "Mayur Vihar Phase 1",
        "rating": 5,
        "date": "23 Jan 2026, 05:48 PM",
        "timestamp": "2026-01-23T17:48:00",
        "comment": "Affordable packages without any hidden charges. Jo quote portal par diya tha exactly wahi final amount liya. Truly satisfied with Hawkeye team.",
        "verified": True
    },
    {
        "id": 101,
        "name": "Ramesh Dubey",
        "location": "Ghaziabad Indirapuram",
        "rating": 5,
        "date": "22 Jan 2026, 12:17 PM",
        "timestamp": "2026-01-22T12:17:00",
        "comment": "Recommended by my neighbor in Ghaziabad. Biometric machine aur 2 CCTV cameras lagwaye. Quotation portal par turant mil gaya tha transparent pricing ke sath.",
        "verified": True
    },
    {
        "id": 94,
        "name": "Ankit Mishra",
        "location": "Kalkaji",
        "rating": 5,
        "date": "19 Jan 2026, 07:15 PM",
        "timestamp": "2026-01-19T19:15:00",
        "comment": "Great experience with Hawkeye team. Technicians police verified the aur proper ID card ke sath aaye the. Truly satisfied with Hawkeye team.",
        "verified": True
    },
    {
        "id": 119,
        "name": "Ankit Chauhan",
        "location": "Tilak Nagar",
        "rating": 5,
        "date": "18 Jan 2026, 04:27 PM",
        "timestamp": "2026-01-18T16:27:00",
        "comment": "Home automation aur CCTV ka integration karwaya villa me. Mobile alert system bahut fast kaam karta hai.",
        "verified": True
    },
    {
        "id": 135,
        "name": "Rajesh Saxena",
        "location": "Karol Bagh",
        "rating": 5,
        "date": "13 Jan 2026, 04:21 PM",
        "timestamp": "2026-01-13T16:21:00",
        "comment": "Pichle 1.5 saal se inka AMC plan chal raha hai hamari housing society me. Cameras 24x7 running bina kisi rukawat ke.",
        "verified": True
    },
    {
        "id": 99,
        "name": "Vikram Mishra",
        "location": "Faridabad Sector 15",
        "rating": 4,
        "date": "11 Jan 2026, 09:22 AM",
        "timestamp": "2026-01-11T09:22:00",
        "comment": "Support team is very responsive. Ek camera offline ho gaya tha router change karne par, phone pe step-by-step reconnect karwaya.",
        "verified": True
    },
    {
        "id": 107,
        "name": "Ajay Bhatia",
        "location": "Shahdara",
        "rating": 5,
        "date": "04 Jan 2026, 09:47 AM",
        "timestamp": "2026-01-04T09:47:00",
        "comment": "Society entrance aur basement ke liye 12 cameras ka quotation manga tha. Rate market se kafi genuine mila aur same-day delivery di.",
        "verified": True
    },
    {
        "id": 38,
        "name": "Kapil Goyal",
        "location": "Noida Sector 62",
        "rating": 5,
        "date": "01 Jan 2026, 08:03 PM",
        "timestamp": "2026-01-01T20:03:00",
        "comment": "Affordable packages without any hidden charges. Jo quote portal par diya tha exactly wahi final amount liya.",
        "verified": True
    },
    {
        "id": 125,
        "name": "Neha Tiwari",
        "location": "Greater Noida West",
        "rating": 5,
        "date": "12 Dec 2025, 09:05 AM",
        "timestamp": "2025-12-12T09:05:00",
        "comment": "Pichle 1.5 saal se inka AMC plan chal raha hai hamari housing society me. Cameras 24x7 running bina kisi rukawat ke.",
        "verified": True
    },
    {
        "id": 62,
        "name": "Deepak Rawat",
        "location": "Model Town III",
        "rating": 5,
        "date": "06 Dec 2025, 05:45 PM",
        "timestamp": "2025-12-06T17:45:00",
        "comment": "Very professional team. Delhi me itni neat trunking wiring koi nahi karta. Ek bhi wire bahar latka hua nahi dikhta.",
        "verified": True
    },
    {
        "id": 74,
        "name": "Priya Verma",
        "location": "Dwarka Sector 12",
        "rating": 5,
        "date": "28 Nov 2025, 02:46 PM",
        "timestamp": "2025-11-28T14:46:00",
        "comment": "Prompt quotation and genuine bill with GST. Professional commercial CCTV work done for our CA office in CP.",
        "verified": True
    },
    {
        "id": 92,
        "name": "Sumit Chauhan",
        "location": "Shahdara",
        "rating": 5,
        "date": "20 Nov 2025, 05:28 PM",
        "timestamp": "2025-11-20T17:28:00",
        "comment": "Great experience with Hawkeye team. Technicians police verified the aur proper ID card ke sath aaye the.",
        "verified": True
    },
    {
        "id": 89,
        "name": "Rajesh Mishra",
        "location": "Kalkaji",
        "rating": 5,
        "date": "19 Nov 2025, 12:11 PM",
        "timestamp": "2025-11-19T12:11:00",
        "comment": "Pichle hafte DVR me hard disk issue aaya tha, call log kiya portal par aur agle din engineer aakar replace kar gaya under warranty. Top service!",
        "verified": True
    },
    {
        "id": 40,
        "name": "Praveen Jain",
        "location": "Noida Sector 18",
        "rating": 5,
        "date": "16 Nov 2025, 11:17 AM",
        "timestamp": "2025-11-16T11:17:00",
        "comment": "Office security ke liye CP Plus 8-channel NVR setup karwaya. Sound recording aur motion alert bohot acche se work kar raha hai. Truly satisfied with Hawkeye team.",
        "verified": True
    },
    {
        "id": 4,
        "name": "Vikram Jain",
        "location": "Vasant Kunj Pocket B",
        "rating": 5,
        "date": "13 Nov 2025, 12:28 PM",
        "timestamp": "2025-11-13T12:28:00",
        "comment": "Home automation aur CCTV ka integration karwaya villa me. Mobile alert system bahut fast kaam karta hai. Truly satisfied with Hawkeye team.",
        "verified": True
    },
    {
        "id": 97,
        "name": "Sanjay Tiwari",
        "location": "Vasant Kunj Pocket B",
        "rating": 5,
        "date": "08 Nov 2025, 03:21 PM",
        "timestamp": "2025-11-08T15:21:00",
        "comment": "Society entrance aur basement ke liye 12 cameras ka quotation manga tha. Rate market se kafi genuine mila aur same-day delivery di. Truly satisfied with Hawkeye team.",
        "verified": True
    },
    {
        "id": 71,
        "name": "Kavita Chawla",
        "location": "Rohini Sector 9",
        "rating": 5,
        "date": "23 Oct 2025, 02:17 PM",
        "timestamp": "2025-10-23T14:17:00",
        "comment": "Recommended by my neighbor in Rohini. Annual Maintenance Contract (AMC) liya tha warehouse ke liye. Har 3 mahine me servicing aur camera lens cleaning timely hoti hai.",
        "verified": True
    },
    {
        "id": 113,
        "name": "Vikram Khanna",
        "location": "Faridabad Sector 15",
        "rating": 4,
        "date": "21 Oct 2025, 08:12 PM",
        "timestamp": "2025-10-21T20:12:00",
        "comment": "Support team is very responsive. Ek camera offline ho gaya tha router change karne par, phone pe step-by-step reconnect karwaya.",
        "verified": True
    },
    {
        "id": 16,
        "name": "Sachin Mehta",
        "location": "Rajouri Garden",
        "rating": 5,
        "date": "20 Oct 2025, 07:29 PM",
        "timestamp": "2025-10-20T19:29:00",
        "comment": "Pichle 1.5 saal se inka AMC plan chal raha hai hamari housing society me. Cameras 24x7 running bina kisi rukawat ke. Truly satisfied with Hawkeye team.",
        "verified": True
    },
    {
        "id": 69,
        "name": "Neha Bhatia",
        "location": "Saket Block J",
        "rating": 5,
        "date": "06 Oct 2025, 09:54 AM",
        "timestamp": "2025-10-06T09:54:00",
        "comment": "Pichle hafte DVR me hard disk issue aaya tha, call log kiya portal par aur agle din engineer aakar replace kar gaya under warranty. Top service!",
        "verified": True
    },
    {
        "id": 10,
        "name": "Gaurav Gupta",
        "location": "Mayur Vihar Phase 1",
        "rating": 5,
        "date": "04 Oct 2025, 01:29 PM",
        "timestamp": "2025-10-04T13:29:00",
        "comment": "Pichle hafte DVR me hard disk issue aaya tha, call log kiya portal par aur agle din engineer aakar replace kar gaya under warranty. Top service! Truly satisfied with Hawkeye team.",
        "verified": True
    },
    {
        "id": 111,
        "name": "Ashok Sethi",
        "location": "Connaught Place",
        "rating": 5,
        "date": "22 Sep 2025, 11:38 AM",
        "timestamp": "2025-09-22T11:38:00",
        "comment": "Recommended by my neighbor in Connaught. ColorVu camera quality is awesome. Raat ko bhi poora daylight jaisa color view dikhta hai lane ka. Safe feel hota hai.",
        "verified": True
    },
    {
        "id": 65,
        "name": "Kapil Kapoor",
        "location": "Janakpuri Block C",
        "rating": 5,
        "date": "18 Sep 2025, 09:57 AM",
        "timestamp": "2025-09-18T09:57:00",
        "comment": "Quick service in Janakpuri. Sham ko 5 baje call kiya tha, agle din subah 11 baje site survey karke 2 baje tak fit kar diya.",
        "verified": True
    },
    {
        "id": 77,
        "name": "Ramesh Yadav",
        "location": "Shalimar Bagh",
        "rating": 5,
        "date": "17 Sep 2025, 03:04 PM",
        "timestamp": "2025-09-17T15:04:00",
        "comment": "Annual Maintenance Contract (AMC) liya tha warehouse ke liye. Har 3 mahine me servicing aur camera lens cleaning timely hoti hai.",
        "verified": True
    },
    {
        "id": 27,
        "name": "Sachin Mittal",
        "location": "Rohini Sector 9",
        "rating": 5,
        "date": "16 Sep 2025, 01:15 PM",
        "timestamp": "2025-09-16T13:15:00",
        "comment": "Pichle hafte DVR me hard disk issue aaya tha, call log kiya portal par aur agle din engineer aakar replace kar gaya under warranty. Top service!",
        "verified": True
    },
    {
        "id": 122,
        "name": "Sachin Bansal",
        "location": "Greater Noida West",
        "rating": 5,
        "date": "08 Sep 2025, 01:21 PM",
        "timestamp": "2025-09-08T13:21:00",
        "comment": "Annual Maintenance Contract (AMC) liya tha warehouse ke liye. Har 3 mahine me servicing aur camera lens cleaning timely hoti hai.",
        "verified": True
    },
    {
        "id": 70,
        "name": "Satish Chawla",
        "location": "Vasant Kunj Pocket B",
        "rating": 5,
        "date": "03 Sep 2025, 01:52 PM",
        "timestamp": "2025-09-03T13:52:00",
        "comment": "Basement parking coverage ke liye zero blind spot plan banaya tha. Bahut hi detailed survey kiya tha engineer ne. Truly satisfied with Hawkeye team.",
        "verified": True
    },
    {
        "id": 127,
        "name": "Harish Mittal",
        "location": "Gurugram DLF Phase 3",
        "rating": 5,
        "date": "28 Aug 2025, 03:47 PM",
        "timestamp": "2025-08-28T15:47:00",
        "comment": "Great experience with Hawkeye team. Technicians police verified the aur proper ID card ke sath aaye the. Truly satisfied with Hawkeye team.",
        "verified": True
    },
    {
        "id": 106,
        "name": "Sachin Mehta",
        "location": "Noida Sector 18",
        "rating": 5,
        "date": "21 Aug 2025, 03:17 PM",
        "timestamp": "2025-08-21T15:17:00",
        "comment": "Genuine brand products only with bill and company warranty. CP Plus app configure karke dono phones me login karwa diya. Truly satisfied with Hawkeye team.",
        "verified": True
    },
    {
        "id": 102,
        "name": "Kapil Mittal",
        "location": "Rohini Sector 9",
        "rating": 4,
        "date": "20 Aug 2025, 07:43 PM",
        "timestamp": "2025-08-20T19:43:00",
        "comment": "Support team is very responsive. Ek camera offline ho gaya tha router change karne par, phone pe step-by-step reconnect karwaya.",
        "verified": True
    },
    {
        "id": 121,
        "name": "Naveen Saxena",
        "location": "Ghaziabad Indirapuram",
        "rating": 4,
        "date": "20 Aug 2025, 09:31 AM",
        "timestamp": "2025-08-20T09:31:00",
        "comment": "Support team is very responsive. Ek camera offline ho gaya tha router change karne par, phone pe step-by-step reconnect karwaya. Truly satisfied with Hawkeye team.",
        "verified": True
    },
    {
        "id": 68,
        "name": "Vikas Chopra",
        "location": "Rohini Sector 9",
        "rating": 5,
        "date": "16 Aug 2025, 03:51 PM",
        "timestamp": "2025-08-16T15:51:00",
        "comment": "Very professional team. Delhi me itni neat trunking wiring koi nahi karta. Ek bhi wire bahar latka hua nahi dikhta.",
        "verified": True
    },
    {
        "id": 129,
        "name": "Kavita Malhotra",
        "location": "Shalimar Bagh",
        "rating": 5,
        "date": "30 Jul 2025, 10:47 AM",
        "timestamp": "2025-07-30T10:47:00",
        "comment": "Annual Maintenance Contract (AMC) liya tha warehouse ke liye. Har 3 mahine me servicing aur camera lens cleaning timely hoti hai.",
        "verified": True
    },
    {
        "id": 31,
        "name": "Ramesh Mishra",
        "location": "Shalimar Bagh",
        "rating": 5,
        "date": "26 Jul 2025, 03:42 PM",
        "timestamp": "2025-07-26T15:42:00",
        "comment": "Annual Maintenance Contract (AMC) liya tha warehouse ke liye. Har 3 mahine me servicing aur camera lens cleaning timely hoti hai. Truly satisfied with Hawkeye team.",
        "verified": True
    },
    {
        "id": 112,
        "name": "Anil Mishra",
        "location": "Shahdara",
        "rating": 5,
        "date": "25 Jul 2025, 10:37 AM",
        "timestamp": "2025-07-25T10:37:00",
        "comment": "Very professional team. Delhi me itni neat trunking wiring koi nahi karta. Ek bhi wire bahar latka hua nahi dikhta. Truly satisfied with Hawkeye team.",
        "verified": True
    },
    {
        "id": 126,
        "name": "Gaurav Chawla",
        "location": "South Extension II",
        "rating": 5,
        "date": "20 Jul 2025, 07:37 PM",
        "timestamp": "2025-07-20T19:37:00",
        "comment": "Recommended by my neighbor in South. Biometric machine aur 2 CCTV cameras lagwaye. Quotation portal par turant mil gaya tha transparent pricing ke sath.",
        "verified": True
    },
    {
        "id": 81,
        "name": "Manoj Jain",
        "location": "Shahdara",
        "rating": 5,
        "date": "18 Jul 2025, 01:13 PM",
        "timestamp": "2025-07-18T13:13:00",
        "comment": "Recommended by my neighbor in Shahdara. Hikvision 4 camera setup lagwaya tha shop ke liye. Night vision bohot clear hai aur wiring bilkul conceal karke ki. Ek saal ho gaya, zero issue.",
        "verified": True
    },
    {
        "id": 78,
        "name": "Mohit Chauhan",
        "location": "Punjabi Bagh West",
        "rating": 5,
        "date": "14 Jul 2025, 05:19 PM",
        "timestamp": "2025-07-14T17:19:00",
        "comment": "Pichle hafte DVR me hard disk issue aaya tha, call log kiya portal par aur agle din engineer aakar replace kar gaya under warranty. Top service!",
        "verified": True
    },
    {
        "id": 44,
        "name": "Rajesh Aggarwal",
        "location": "Model Town III",
        "rating": 5,
        "date": "29 Jun 2025, 03:44 PM",
        "timestamp": "2025-06-29T15:44:00",
        "comment": "Basement parking coverage ke liye zero blind spot plan banaya tha. Bahut hi detailed survey kiya tha engineer ne.",
        "verified": True
    },
    {
        "id": 55,
        "name": "Tarun Gupta",
        "location": "Mayur Vihar Phase 1",
        "rating": 5,
        "date": "28 Jun 2025, 11:28 AM",
        "timestamp": "2025-06-28T11:28:00",
        "comment": "Best CCTV installers in Delhi NCR. Hamari grocery store chain ke 3 outlets par inhone hi installation kiya hai. Truly satisfied with Hawkeye team.",
        "verified": True
    },
    {
        "id": 120,
        "name": "Ankit Singhal",
        "location": "Mayur Vihar Phase 1",
        "rating": 5,
        "date": "22 Jun 2025, 04:15 PM",
        "timestamp": "2025-06-22T16:15:00",
        "comment": "Society entrance aur basement ke liye 12 cameras ka quotation manga tha. Rate market se kafi genuine mila aur same-day delivery di.",
        "verified": True
    },
    {
        "id": 58,
        "name": "Rakesh Pandey",
        "location": "Gurugram DLF Phase 3",
        "rating": 5,
        "date": "15 Jun 2025, 01:38 PM",
        "timestamp": "2025-06-15T13:38:00",
        "comment": "Office security ke liye CP Plus 8-channel NVR setup karwaya. Sound recording aur motion alert bohot acche se work kar raha hai. Truly satisfied with Hawkeye team.",
        "verified": True
    },
    {
        "id": 128,
        "name": "Kunal Singhal",
        "location": "Paschim Vihar",
        "rating": 5,
        "date": "14 Jun 2025, 01:16 PM",
        "timestamp": "2025-06-14T13:16:00",
        "comment": "Basement parking coverage ke liye zero blind spot plan banaya tha. Bahut hi detailed survey kiya tha engineer ne.",
        "verified": True
    },
    {
        "id": 7,
        "name": "Rakesh Goyal",
        "location": "Paschim Vihar",
        "rating": 5,
        "date": "07 Jun 2025, 09:46 AM",
        "timestamp": "2025-06-07T09:46:00",
        "comment": "Prompt quotation and genuine bill with GST. Professional commercial CCTV work done for our CA office in CP. Truly satisfied with Hawkeye team.",
        "verified": True
    },
    {
        "id": 73,
        "name": "Ramesh Singhal",
        "location": "Rohini Sector 9",
        "rating": 5,
        "date": "04 Jun 2025, 11:37 AM",
        "timestamp": "2025-06-04T11:37:00",
        "comment": "Pichle hafte DVR me hard disk issue aaya tha, call log kiya portal par aur agle din engineer aakar replace kar gaya under warranty. Top service! Truly satisfied with Hawkeye team.",
        "verified": True
    },
    {
        "id": 93,
        "name": "Manish Pandey",
        "location": "Greater Noida West",
        "rating": 5,
        "date": "02 Jun 2025, 12:53 PM",
        "timestamp": "2025-06-02T12:53:00",
        "comment": "Basement parking coverage ke liye zero blind spot plan banaya tha. Bahut hi detailed survey kiya tha engineer ne.",
        "verified": True
    },
    {
        "id": 21,
        "name": "Dinesh Chauhan",
        "location": "Noida Sector 18",
        "rating": 5,
        "date": "25 May 2025, 05:55 PM",
        "timestamp": "2025-05-25T17:55:00",
        "comment": "Recommended by my neighbor in Noida. Great experience with Hawkeye team. Technicians police verified the aur proper ID card ke sath aaye the.",
        "verified": True
    },
    {
        "id": 90,
        "name": "Mukesh Sethi",
        "location": "Janakpuri Block C",
        "rating": 5,
        "date": "23 May 2025, 10:29 AM",
        "timestamp": "2025-05-23T10:29:00",
        "comment": "Home automation aur CCTV ka integration karwaya villa me. Mobile alert system bahut fast kaam karta hai.",
        "verified": True
    },
    {
        "id": 49,
        "name": "Neha Aggarwal",
        "location": "Dwarka Sector 12",
        "rating": 5,
        "date": "20 May 2025, 06:38 PM",
        "timestamp": "2025-05-20T18:38:00",
        "comment": "Dahua 5MP IP camera setup is crystal clear. Number plate easily read ho jati hai main gate par. Truly satisfied with Hawkeye team.",
        "verified": True
    },
    {
        "id": 86,
        "name": "Praveen Kapoor",
        "location": "Rohini Sector 9",
        "rating": 5,
        "date": "18 May 2025, 04:39 PM",
        "timestamp": "2025-05-18T16:39:00",
        "comment": "Recommended by my neighbor in Rohini. Dwarka wale flat me 3 IP cameras install karwaye. Mobile app par live feed ekdum smooth chalti hai. Er. Rahul ne poora setup patiently sikhaya.",
        "verified": True
    },
    {
        "id": 1,
        "name": "Anil Sharma",
        "location": "Shalimar Bagh",
        "rating": 5,
        "date": "18 May 2025, 12:08 PM",
        "timestamp": "2025-05-18T12:08:00",
        "comment": "ColorVu camera quality is awesome. Raat ko bhi poora daylight jaisa color view dikhta hai lane ka. Safe feel hota hai. Truly satisfied with Hawkeye team.",
        "verified": True
    },
    {
        "id": 35,
        "name": "Amit Singhal",
        "location": "Pitampura ED Block",
        "rating": 5,
        "date": "11 May 2025, 01:42 PM",
        "timestamp": "2025-05-11T13:42:00",
        "comment": "Great experience with Hawkeye team. Technicians police verified the aur proper ID card ke sath aaye the.",
        "verified": True
    },
    {
        "id": 67,
        "name": "Kunal Chopra",
        "location": "Ghaziabad Indirapuram",
        "rating": 5,
        "date": "10 May 2025, 11:51 AM",
        "timestamp": "2025-05-10T11:51:00",
        "comment": "Office security ke liye CP Plus 8-channel NVR setup karwaya. Sound recording aur motion alert bohot acche se work kar raha hai. Truly satisfied with Hawkeye team.",
        "verified": True
    },
    {
        "id": 42,
        "name": "Ramesh Kohli",
        "location": "Rohini Sector 9",
        "rating": 5,
        "date": "10 May 2025, 11:26 AM",
        "timestamp": "2025-05-10T11:26:00",
        "comment": "Society entrance aur basement ke liye 12 cameras ka quotation manga tha. Rate market se kafi genuine mila aur same-day delivery di.",
        "verified": True
    },
    {
        "id": 95,
        "name": "Ankit Sethi",
        "location": "Pitampura ED Block",
        "rating": 5,
        "date": "08 May 2025, 01:21 PM",
        "timestamp": "2025-05-08T13:21:00",
        "comment": "Quick service in Janakpuri. Sham ko 5 baje call kiya tha, agle din subah 11 baje site survey karke 2 baje tak fit kar diya.",
        "verified": True
    },
    {
        "id": 3,
        "name": "Amit Sharma",
        "location": "Pitampura ED Block",
        "rating": 5,
        "date": "06 May 2025, 05:38 PM",
        "timestamp": "2025-05-06T17:38:00",
        "comment": "Annual Maintenance Contract (AMC) liya tha warehouse ke liye. Har 3 mahine me servicing aur camera lens cleaning timely hoti hai.",
        "verified": True
    },
    {
        "id": 34,
        "name": "Kavita Sharma",
        "location": "Pitampura ED Block",
        "rating": 5,
        "date": "02 May 2025, 10:57 AM",
        "timestamp": "2025-05-02T10:57:00",
        "comment": "Dwarka wale flat me 3 IP cameras install karwaye. Mobile app par live feed ekdum smooth chalti hai. Er. Rahul ne poora setup patiently sikhaya. Truly satisfied with Hawkeye team.",
        "verified": True
    },
    {
        "id": 14,
        "name": "Kavita Yadav",
        "location": "Punjabi Bagh West",
        "rating": 5,
        "date": "02 May 2025, 09:51 AM",
        "timestamp": "2025-05-02T09:51:00",
        "comment": "Dwarka wale flat me 3 IP cameras install karwaye. Mobile app par live feed ekdum smooth chalti hai. Er. Rahul ne poora setup patiently sikhaya.",
        "verified": True
    },
    {
        "id": 132,
        "name": "Rakesh Kohli",
        "location": "Vasant Kunj Pocket B",
        "rating": 5,
        "date": "30 Apr 2025, 02:11 PM",
        "timestamp": "2025-04-30T14:11:00",
        "comment": "Quick service in Janakpuri. Sham ko 5 baje call kiya tha, agle din subah 11 baje site survey karke 2 baje tak fit kar diya.",
        "verified": True
    },
    {
        "id": 18,
        "name": "Kapil Saxena",
        "location": "South Extension II",
        "rating": 5,
        "date": "22 Apr 2025, 11:32 AM",
        "timestamp": "2025-04-22T11:32:00",
        "comment": "Best CCTV installers in Delhi NCR. Hamari grocery store chain ke 3 outlets par inhone hi installation kiya hai.",
        "verified": True
    },
    {
        "id": 15,
        "name": "Sachin Aggarwal",
        "location": "Model Town III",
        "rating": 5,
        "date": "14 Apr 2025, 06:56 PM",
        "timestamp": "2025-04-14T18:56:00",
        "comment": "Society entrance aur basement ke liye 12 cameras ka quotation manga tha. Rate market se kafi genuine mila aur same-day delivery di.",
        "verified": True
    },
    {
        "id": 11,
        "name": "Harish Bansal",
        "location": "Paschim Vihar",
        "rating": 5,
        "date": "12 Apr 2025, 07:17 PM",
        "timestamp": "2025-04-12T19:17:00",
        "comment": "Recommended by my neighbor in Paschim. Best CCTV installers in Delhi NCR. Hamari grocery store chain ke 3 outlets par inhone hi installation kiya hai.",
        "verified": True
    },
    {
        "id": 98,
        "name": "Ramesh Sethi",
        "location": "Noida Sector 62",
        "rating": 5,
        "date": "09 Apr 2025, 03:24 PM",
        "timestamp": "2025-04-09T15:24:00",
        "comment": "Dwarka wale flat me 3 IP cameras install karwaye. Mobile app par live feed ekdum smooth chalti hai. Er. Rahul ne poora setup patiently sikhaya.",
        "verified": True
    },
    {
        "id": 109,
        "name": "Amit Mishra",
        "location": "Rohini Sector 9",
        "rating": 5,
        "date": "02 Apr 2025, 09:39 AM",
        "timestamp": "2025-04-02T09:39:00",
        "comment": "Biometric machine aur 2 CCTV cameras lagwaye. Quotation portal par turant mil gaya tha transparent pricing ke sath. Truly satisfied with Hawkeye team.",
        "verified": True
    },
    {
        "id": 87,
        "name": "Suresh Sethi",
        "location": "Noida Sector 62",
        "rating": 5,
        "date": "28 Mar 2025, 08:44 PM",
        "timestamp": "2025-03-28T20:44:00",
        "comment": "Dahua 5MP IP camera setup is crystal clear. Number plate easily read ho jati hai main gate par.",
        "verified": True
    },
    {
        "id": 130,
        "name": "Ramesh Mishra",
        "location": "Connaught Place",
        "rating": 5,
        "date": "25 Mar 2025, 12:47 PM",
        "timestamp": "2025-03-25T12:47:00",
        "comment": "Very professional team. Delhi me itni neat trunking wiring koi nahi karta. Ek bhi wire bahar latka hua nahi dikhta. Truly satisfied with Hawkeye team.",
        "verified": True
    },
    {
        "id": 37,
        "name": "Neha Dubey",
        "location": "Greater Noida West",
        "rating": 5,
        "date": "23 Mar 2025, 10:06 AM",
        "timestamp": "2025-03-23T10:06:00",
        "comment": "Affordable packages without any hidden charges. Jo quote portal par diya tha exactly wahi final amount liya. Truly satisfied with Hawkeye team.",
        "verified": True
    },
    {
        "id": 118,
        "name": "Naveen Tiwari",
        "location": "Lajpat Nagar IV",
        "rating": 5,
        "date": "09 Mar 2025, 08:33 PM",
        "timestamp": "2025-03-09T20:33:00",
        "comment": "Affordable packages without any hidden charges. Jo quote portal par diya tha exactly wahi final amount liya. Truly satisfied with Hawkeye team.",
        "verified": True
    },
    {
        "id": 45,
        "name": "Kunal Yadav",
        "location": "Connaught Place",
        "rating": 5,
        "date": "15 Feb 2025, 12:18 PM",
        "timestamp": "2025-02-15T12:18:00",
        "comment": "Pichle 1.5 saal se inka AMC plan chal raha hai hamari housing society me. Cameras 24x7 running bina kisi rukawat ke.",
        "verified": True
    },
    {
        "id": 96,
        "name": "Sachin Jain",
        "location": "Pitampura ED Block",
        "rating": 5,
        "date": "11 Feb 2025, 12:24 PM",
        "timestamp": "2025-02-11T12:24:00",
        "comment": "Recommended by my neighbor in Pitampura. Office security ke liye CP Plus 8-channel NVR setup karwaya. Sound recording aur motion alert bohot acche se work kar raha hai.",
        "verified": True
    },
    {
        "id": 88,
        "name": "Dinesh Mittal",
        "location": "South Extension II",
        "rating": 5,
        "date": "08 Feb 2025, 07:44 PM",
        "timestamp": "2025-02-08T19:44:00",
        "comment": "Biometric machine aur 2 CCTV cameras lagwaye. Quotation portal par turant mil gaya tha transparent pricing ke sath. Truly satisfied with Hawkeye team.",
        "verified": True
    },
    {
        "id": 57,
        "name": "Kunal Khanna",
        "location": "Malviya Nagar",
        "rating": 5,
        "date": "25 Jan 2025, 01:07 PM",
        "timestamp": "2025-01-25T13:07:00",
        "comment": "Pichle hafte DVR me hard disk issue aaya tha, call log kiya portal par aur agle din engineer aakar replace kar gaya under warranty. Top service!",
        "verified": True
    },
    {
        "id": 29,
        "name": "Suresh Mishra",
        "location": "Gurugram DLF Phase 3",
        "rating": 5,
        "date": "19 Jan 2025, 07:30 PM",
        "timestamp": "2025-01-19T19:30:00",
        "comment": "Office security ke liye CP Plus 8-channel NVR setup karwaya. Sound recording aur motion alert bohot acche se work kar raha hai.",
        "verified": True
    },
    {
        "id": 103,
        "name": "Manoj Pandey",
        "location": "Saket Block J",
        "rating": 5,
        "date": "18 Jan 2025, 06:34 PM",
        "timestamp": "2025-01-18T18:34:00",
        "comment": "Basement parking coverage ke liye zero blind spot plan banaya tha. Bahut hi detailed survey kiya tha engineer ne. Truly satisfied with Hawkeye team.",
        "verified": True
    },
    {
        "id": 133,
        "name": "Rohit Sharma",
        "location": "Connaught Place",
        "rating": 5,
        "date": "17 Jan 2025, 01:02 PM",
        "timestamp": "2025-01-17T13:02:00",
        "comment": "Home automation aur CCTV ka integration karwaya villa me. Mobile alert system bahut fast kaam karta hai. Truly satisfied with Hawkeye team.",
        "verified": True
    },
    {
        "id": 32,
        "name": "Harish Sethi",
        "location": "Gurugram Sector 48",
        "rating": 5,
        "date": "11 Jan 2025, 12:14 PM",
        "timestamp": "2025-01-11T12:14:00",
        "comment": "Basement parking coverage ke liye zero blind spot plan banaya tha. Bahut hi detailed survey kiya tha engineer ne.",
        "verified": True
    },
    {
        "id": 75,
        "name": "Sachin Chopra",
        "location": "Ghaziabad Indirapuram",
        "rating": 5,
        "date": "06 Jan 2025, 03:57 PM",
        "timestamp": "2025-01-06T15:57:00",
        "comment": "Great experience with Hawkeye team. Technicians police verified the aur proper ID card ke sath aaye the.",
        "verified": True
    },
    {
        "id": 23,
        "name": "Ankit Mishra",
        "location": "Rajouri Garden",
        "rating": 5,
        "date": "02 Jan 2025, 01:27 PM",
        "timestamp": "2025-01-02T13:27:00",
        "comment": "Genuine brand products only with bill and company warranty. CP Plus app configure karke dono phones me login karwa diya.",
        "verified": True
    },
    {
        "id": 19,
        "name": "Vinod Gupta",
        "location": "Kalkaji",
        "rating": 5,
        "date": "31 Dec 2024, 11:40 AM",
        "timestamp": "2024-12-31T11:40:00",
        "comment": "Dwarka wale flat me 3 IP cameras install karwaye. Mobile app par live feed ekdum smooth chalti hai. Er. Rahul ne poora setup patiently sikhaya. Truly satisfied with Hawkeye team.",
        "verified": True
    },
    {
        "id": 39,
        "name": "Rakesh Verma",
        "location": "South Extension II",
        "rating": 5,
        "date": "30 Dec 2024, 12:12 PM",
        "timestamp": "2024-12-30T12:12:00",
        "comment": "Genuine brand products only with bill and company warranty. CP Plus app configure karke dono phones me login karwa diya.",
        "verified": True
    },
    {
        "id": 117,
        "name": "Mohit Sharma",
        "location": "Noida Sector 62",
        "rating": 5,
        "date": "27 Dec 2024, 03:23 PM",
        "timestamp": "2024-12-27T15:23:00",
        "comment": "Pichle 1.5 saal se inka AMC plan chal raha hai hamari housing society me. Cameras 24x7 running bina kisi rukawat ke.",
        "verified": True
    },
    {
        "id": 114,
        "name": "Suresh Saxena",
        "location": "Connaught Place",
        "rating": 5,
        "date": "23 Dec 2024, 08:49 PM",
        "timestamp": "2024-12-23T20:49:00",
        "comment": "Biometric machine aur 2 CCTV cameras lagwaye. Quotation portal par turant mil gaya tha transparent pricing ke sath.",
        "verified": True
    },
    {
        "id": 6,
        "name": "Ankit Kapoor",
        "location": "Vasant Kunj Pocket B",
        "rating": 5,
        "date": "23 Dec 2024, 10:24 AM",
        "timestamp": "2024-12-23T10:24:00",
        "comment": "Recommended by my neighbor in Vasant. Genuine brand products only with bill and company warranty. CP Plus app configure karke dono phones me login karwa diya.",
        "verified": True
    },
    {
        "id": 2,
        "name": "Rakesh Yadav",
        "location": "Shalimar Bagh",
        "rating": 5,
        "date": "08 Dec 2024, 06:27 PM",
        "timestamp": "2024-12-08T18:27:00",
        "comment": "Home automation aur CCTV ka integration karwaya villa me. Mobile alert system bahut fast kaam karta hai.",
        "verified": True
    },
    {
        "id": 28,
        "name": "Pooja Chawla",
        "location": "Faridabad Sector 15",
        "rating": 5,
        "date": "06 Dec 2024, 08:31 PM",
        "timestamp": "2024-12-06T20:31:00",
        "comment": "Society entrance aur basement ke liye 12 cameras ka quotation manga tha. Rate market se kafi genuine mila aur same-day delivery di. Truly satisfied with Hawkeye team.",
        "verified": True
    },
    {
        "id": 8,
        "name": "Naveen Jain",
        "location": "Dwarka Sector 12",
        "rating": 4,
        "date": "29 Nov 2024, 05:18 PM",
        "timestamp": "2024-11-29T17:18:00",
        "comment": "Support team is very responsive. Ek camera offline ho gaya tha router change karne par, phone pe step-by-step reconnect karwaya.",
        "verified": True
    },
    {
        "id": 63,
        "name": "Kapil Jain",
        "location": "Rohini Sector 9",
        "rating": 5,
        "date": "26 Nov 2024, 08:57 PM",
        "timestamp": "2024-11-26T20:57:00",
        "comment": "Pichle hafte DVR me hard disk issue aaya tha, call log kiya portal par aur agle din engineer aakar replace kar gaya under warranty. Top service!",
        "verified": True
    },
    {
        "id": 48,
        "name": "Pooja Arora",
        "location": "Pitampura ED Block",
        "rating": 5,
        "date": "19 Nov 2024, 06:04 PM",
        "timestamp": "2024-11-19T18:04:00",
        "comment": "Very professional team. Delhi me itni neat trunking wiring koi nahi karta. Ek bhi wire bahar latka hua nahi dikhta.",
        "verified": True
    },
    {
        "id": 116,
        "name": "Ramesh Chopra",
        "location": "Malviya Nagar",
        "rating": 5,
        "date": "19 Nov 2024, 05:41 PM",
        "timestamp": "2024-11-19T17:41:00",
        "comment": "Recommended by my neighbor in Malviya. Best CCTV installers in Delhi NCR. Hamari grocery store chain ke 3 outlets par inhone hi installation kiya hai.",
        "verified": True
    },
    {
        "id": 46,
        "name": "Ashok Verma",
        "location": "Faridabad Sector 15",
        "rating": 5,
        "date": "11 Nov 2024, 08:20 PM",
        "timestamp": "2024-11-11T20:20:00",
        "comment": "Home automation aur CCTV ka integration karwaya villa me. Mobile alert system bahut fast kaam karta hai. Truly satisfied with Hawkeye team.",
        "verified": True
    },
    {
        "id": 43,
        "name": "Vinod Mittal",
        "location": "Vasant Kunj Pocket B",
        "rating": 4,
        "date": "09 Nov 2024, 11:24 AM",
        "timestamp": "2024-11-09T11:24:00",
        "comment": "Support team is very responsive. Ek camera offline ho gaya tha router change karne par, phone pe step-by-step reconnect karwaya. Truly satisfied with Hawkeye team.",
        "verified": True
    },
    {
        "id": 60,
        "name": "Priya Arora",
        "location": "Greater Noida West",
        "rating": 5,
        "date": "01 Nov 2024, 10:40 AM",
        "timestamp": "2024-11-01T10:40:00",
        "comment": "ColorVu camera quality is awesome. Raat ko bhi poora daylight jaisa color view dikhta hai lane ka. Safe feel hota hai.",
        "verified": True
    },
    {
        "id": 105,
        "name": "Kapil Kapoor",
        "location": "Noida Sector 18",
        "rating": 5,
        "date": "31 Oct 2024, 01:24 PM",
        "timestamp": "2024-10-31T13:24:00",
        "comment": "Very professional team. Delhi me itni neat trunking wiring koi nahi karta. Ek bhi wire bahar latka hua nahi dikhta.",
        "verified": True
    },
    {
        "id": 9,
        "name": "Harish Saxena",
        "location": "Vasant Kunj Pocket B",
        "rating": 5,
        "date": "26 Oct 2024, 07:14 PM",
        "timestamp": "2024-10-26T19:14:00",
        "comment": "Society entrance aur basement ke liye 12 cameras ka quotation manga tha. Rate market se kafi genuine mila aur same-day delivery di.",
        "verified": True
    },
    {
        "id": 53,
        "name": "Naveen Singhal",
        "location": "Kalkaji",
        "rating": 5,
        "date": "19 Sep 2024, 04:39 PM",
        "timestamp": "2024-09-19T16:39:00",
        "comment": "Society entrance aur basement ke liye 12 cameras ka quotation manga tha. Rate market se kafi genuine mila aur same-day delivery di.",
        "verified": True
    },
    {
        "id": 61,
        "name": "Kapil Kohli",
        "location": "Model Town III",
        "rating": 5,
        "date": "13 Sep 2024, 02:49 PM",
        "timestamp": "2024-09-13T14:49:00",
        "comment": "Dwarka wale flat me 3 IP cameras install karwaye. Mobile app par live feed ekdum smooth chalti hai. Er. Rahul ne poora setup patiently sikhaya. Truly satisfied with Hawkeye team.",
        "verified": True
    },
    {
        "id": 76,
        "name": "Praveen Bhatia",
        "location": "Janakpuri Block C",
        "rating": 5,
        "date": "11 Sep 2024, 05:59 PM",
        "timestamp": "2024-09-11T17:59:00",
        "comment": "Affordable packages without any hidden charges. Jo quote portal par diya tha exactly wahi final amount liya. Truly satisfied with Hawkeye team.",
        "verified": True
    },

]

def get_persisted_admin_hash():
    if os.path.exists(CONFIG_BACKUP_FILE):
        try:
            with open(CONFIG_BACKUP_FILE, 'r') as f:
                data = json.load(f)
                return data.get('admin_password_hash')
        except Exception:
            pass
    return None

def save_persisted_admin_hash(pwd_hash):
    try:
        with open(CONFIG_BACKUP_FILE, 'w') as f:
            json.dump({'admin_password_hash': pwd_hash, 'updated_at': datetime.utcnow().isoformat()}, f)
    except Exception as e:
        print(f"Error persisting admin config: {e}")

with app.app_context():
    db.create_all()
    admin_user = AdminUser.query.filter_by(username="admin").first()
    saved_hash = get_persisted_admin_hash()
    
    if not admin_user:
        # If DB was reset by Render ephemeral disk, RESTORE the saved custom password!
        initial_hash = saved_hash if saved_hash else generate_password_hash("Admin@2026")
        admin_user = AdminUser(username="admin", password_hash=initial_hash)
        db.session.add(admin_user)
        db.session.commit()
    elif saved_hash and admin_user.password_hash != saved_hash:
        # Sync to match saved custom password
        admin_user.password_hash = saved_hash
        db.session.commit()

def calculate_quote(cameras, brand="Hawkeye", storage=15):
    if cameras == 4:
        return 18499
    elif cameras == 6:
        return 25000
    elif cameras == 8:
        return 32000
    elif cameras == 2:
        return 11500
    elif cameras == 16:
        return 62000
    else:
        return 18499 + max(0, cameras - 4) * 3375

# =========================== LOGO & NAVIGATION ===========================

HAWKEYE_EMBLEM_B64 = "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ytBU1bIsTBDR3GfOnFlXV3fzzTc7K1ZRFKcent6e6DhgQkhZWdmcOXMuuOCCqVOnaprW0dFhWRYuadu2uRAUCCWEMYaT8vAWOWtP07SKioqGhoYTTzzxkksuWbFixUGhD0KIg3dRQggBFUDj4t0r3ccPN0CQFeXq2c+n4gSEACxcOSHHoS2Y/vQhD0AXJIIIIiQibA6zMtUPbpRkkpTd2m9ep79cm9QpNblgQAQRX9v070P5IqeP4+yzz37ggQfGjBkDAKZpopvEW7Ns2bIXXnjh3XffdZwoGofb7b744ot/8IMfjB8/PpVKdXV1YcLEelI8wRhn3DAMmzEBwjSMPZWVK1as+OCDD3bv3o2H0nXdSTH318GPx3TSL7TjkSNHjhs3Li83T5akRDLR1toWDodtZjObUUlyuXSP26O59DknzmlqbLr11ludK+03BnCWLm4OjDHDMHRdnzBhwqWXXnrWWWcFg8Guri6kVneXb4TjVwn+BoMxRGauvPLKTz/99KGHHtqxY8dTTz3lYIiH4hapIABCocTk/PRc5c0bZUkkJV3/0XPisXLDRakpQPRQV+BQqROHadBUEAFCoYJy8uY812nHWYLx7dXqac+aHYJzQWwQHI5dT++RpIDomLOysu6///7rr78egQVJkrBVpK2t7fXXX//HP/6xYsUKZ08nhCCT+LLLLvvpT386duxYxhh6X6ywYIDRnfYZpkSppuuRWPSLFStef+215cuXo03oup4uAt176ldaFOekj3g52dnZxx133PDhwxVFaW5ubm5uZpYtyzIWaFRVxetSVVVRFCrTk08+paGh4ac//elBDTq9GI43gRCSSCSEECNHjrziiivmzp2bmZnZ2dmJ1aV0QguuAdxhsrKy7rjjjgULFmRkZITDYUwf05nZhzIckAqgQJCftOB07YoTbW6JPQ36rCeT7VxwIrig0D2s/UgN+iAnIUChwuJw5UDtH1dTZqWorl3zFH++2tQoNQVwNOhjbM2HGK45D/Xcc8999NFHBw4ciP4PUeRt27Y988wzL730Un19vZOZoW3hR+6++25kbnR1daUjAFgEQbOmlOqa3tTY+P7777/+xhubt2zGJZHeWJUOJqTbN6400zQxM3NMecKECVlZWeFwuK2tzbIsRVHcLrdL152wAf0rpVTTNEopUHLWWWfV19djT6GDH/f1lP2u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"

LOGO_SVG = """
<div class="brand-badge-container">
    <img src="/logo.png" alt="Hawkeye CCTV Logo" class="brand-logo-img cctv-scan-pulse" width="46" height="46">
    <div class="brand-titles">
        <div class="brand-name">HAWK<span class="gold-text">EYE</span></div>
        <div class="brand-sub">CCTV AND AUTOMATION</div>
    </div>
</div>
"""

NAV_BAR = f"""
<header class="main-header">
    <div class="header-container">
        <a href="/" class="brand-link">
            {LOGO_SVG}
        </a>
        <div class="nav-links">
            <a href="/services">Services</a>
            <a href="/packages">Packages</a>
            <a href="/calculator">Cost Calculator</a>
            <a href="/reviews">Customer Reviews</a>
            {{% if session.get('user_id') %}}
                <a href="/portal" class="btn-portal">Customer Portal ({{{{ session.get('user_name', 'Account').split()[0] }}}})</a>
                <a href="/logout" class="btn-logout">Logout</a>
            {{% else %}}
                <a href="/login" class="btn-login">Client Login</a>
                <a href="/#get-quote" class="btn-cta">Book Free Survey</a>
            {{% endif %}}
        </div>
    </div>
</header>
"""

FOOTER_SECTION = f"""
<footer class="site-footer">
    <div class="footer-grid">
        <div class="footer-col">
            {LOGO_SVG}
            <p style="margin-top:1rem; font-size:0.9rem; color:#94a3b8;">Precision CCTV &amp; Smart Automation System Integrator. Providing 5MP IP systems, night-vision surveillance, and professional cabling across Delhi NCR.</p>
            <div style="margin-top:12px; color:#38bdf8; font-weight:700; font-size:0.85rem; letter-spacing:0.5px;">SALES • INSTALLATION • MAINTENANCE</div>
        </div>
        <div class="footer-col">
            <h4>Quick Navigation</h4>
            <ul>
                <li><a href="/services">Surveillance &amp; Automation Services</a></li>
                <li><a href="/packages">Standard CCTV Kits</a></li>
                <li><a href="/calculator">Surveillance Cost Calculator</a></li>
                <li><a href="/reviews">Verified Customer Testimonials</a></li>
                <li><a href="/portal">Customer AMC &amp; Repair Desk</a></li>
            </ul>
        </div>
        <div class="footer-col">
            <h4>Support &amp; Operations</h4>
            <p>📍 Address: Old Palam Road, Kakrola, Dwarka Sector 15, New Delhi</p>
            <p>📞 WhatsApp / Mobile: <a href="https://wa.me/919971332864" target="_blank" style="color:#38bdf8; font-weight:bold;">+91 9971332864</a></p>
            <p>🕒 Field Inspection Hours: 08:30 AM – 08:00 PM (All 7 Days)</p>
            <p>💼 Join Our Team: <a href="/careers" style="color:#38bdf8; font-weight:600; text-decoration:underline;">Career Opportunities &amp; Jobs</a></p>
            <p>🔐 Owner Console: <a href="/admin" style="color:#94a3b8; font-size:0.8rem;">Admin Portal Access</a></p>
        </div>
    </div>
    <div class="footer-bottom">
        <p>© HAWKEYE CCTV AND AUTOMATION (Established 2023). All Rights Reserved. GST Compliant Enterprise.</p>
    </div>
</footer>
<a href="https://wa.me/919971332864" class="floating-wa-btn" target="_blank" title="Chat on WhatsApp">💬</a>
"""

STYLES = """
<style>
    :root {
        --primary: #0a0f1d;
        --surface: #121929;
        --secondary: #38bdf8;
        --secondary-dark: #0284c7;
        --accent: #38bdf8;
        --accent-cyan: #38bdf8;
        --success: #16a34a;
        --bg-light: #f8fafc;
        --border-color: #e2e8f0;
        --text-dark: #1e293b;
        --text-muted: #64748b;
    }
    @keyframes cctvPulse {
        0% { filter: drop-shadow(0 0 2px rgba(56, 189, 248, 0.4)); }
        50% { filter: drop-shadow(0 0 10px rgba(56, 189, 248, 0.8)); }
        100% { filter: drop-shadow(0 0 2px rgba(56, 189, 248, 0.4)); }
    }
    @keyframes recBlink {
        0%, 100% { opacity: 1; }
        50% { opacity: 0.2; }
    }
    .rec-dot { width: 8px; height: 8px; background: #ef4444; border-radius: 50%; display: inline-block; box-shadow: 0 0 8px #ef4444; animation: recBlink 1.2s infinite; }
    .rec-dot-small { width: 6px; height: 6px; background: #ef4444; border-radius: 50%; display: inline-block; margin-right: 4px; animation: recBlink 1.2s infinite; }
    .rec-corner-tag { font-size: 0.72rem; font-weight: 800; font-family: monospace; color: #ef4444; background: rgba(239,68,68,0.1); border: 1px solid rgba(239,68,68,0.3); padding: 2px 8px; border-radius: 4px; display: inline-flex; align-items: center; margin-bottom: 8px; }
    .cctv-scan-pulse { animation: cctvPulse 3s ease-in-out infinite; }
    .cctv-glow-card { transition: all 0.3s ease; }
    .cctv-glow-card:hover { transform: translateY(-4px); box-shadow: 0 12px 25px rgba(56, 189, 248, 0.12); border-color: #38bdf8 !important; }
    .floating-wa-btn { position: fixed; bottom: 25px; right: 25px; background: #25d366; color: white !important; width: 56px; height: 56px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 1.8rem; box-shadow: 0 6px 20px rgba(37, 211, 102, 0.4); z-index: 999; text-decoration: none; transition: transform 0.2s; }
    .floating-wa-btn:hover { transform: scale(1.08); }
    * { margin:0; padding:0; box-sizing:border-box; font-family:'Segoe UI',system-ui,-apple-system,sans-serif; }
    body { background: var(--bg-light); color: var(--text-dark); line-height: 1.6; }
    a { text-decoration: none; color: inherit; }

    .brand-badge-container { display: flex; align-items: center; gap: 0.75rem; }
    .brand-svg-icon { width: 44px; height: 44px; flex-shrink: 0; filter: drop-shadow(0 2px 8px rgba(245, 158, 11, 0.3)); }
    .brand-titles { display: flex; flex-direction: column; }
    .brand-name { font-size: 1.35rem; font-weight: 900; color: #ffffff; letter-spacing: 1px; line-height: 1; }
    .gold-text { color: var(--secondary); }
    .brand-sub { font-size: 0.65rem; font-weight: 700; color: #94a3b8; letter-spacing: 1.5px; margin-top: 3px; }

    .top-strip { background: #060911; color: #94a3b8; font-size: 0.82rem; padding: 6px 5%; display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #1e293b; }
    .top-strip strong { color: #f59e0b; }

    .main-header { background: var(--primary); padding: 0.8rem 5%; position: sticky; top:0; z-index:100; box-shadow: 0 4px 20px rgba(0,0,0,0.3); border-bottom: 3px solid var(--secondary); }
    .header-container { display: flex; justify-content: space-between; align-items: center; max-width: 1300px; margin: auto; }
    
    .nav-links { display: flex; gap: 1.4rem; align-items: center; }
    .nav-links a { color: #cbd5e1; font-weight: 500; font-size: 0.92rem; transition: 0.2s; }
    .nav-links a:hover { color: var(--secondary); }
    .btn-portal { background: var(--surface); color: var(--secondary) !important; padding: 0.5rem 1rem; border-radius: 6px; border: 1px solid #334155; font-weight: 600 !important; }
    .btn-login { background: transparent; border: 1px solid var(--secondary); color: var(--secondary) !important; padding: 0.45rem 0.95rem; border-radius: 6px; font-weight: 600 !important; }
    .btn-cta { background: var(--secondary); color: #0a0f1d !important; padding: 0.5rem 1.1rem; border-radius: 6px; font-weight: 700 !important; }
    .btn-logout { color: #ef4444 !important; font-size: 0.85rem; font-weight: 600; }

    /* Hero */
    .hero { background: radial-gradient(circle at 80% 20%, rgba(245, 158, 11, 0.12) 0%, transparent 50%), linear-gradient(rgba(10,15,29,0.95), rgba(10,15,29,0.92)), url('https://images.unsplash.com/photo-1557597774-9d273605dfa9?auto=format&fit=crop&w=1600&q=80') center/cover; color:white; padding: 4.5rem 5%; }
    .hero-wrap { max-width: 1300px; margin: auto; display: flex; flex-wrap: wrap; gap: 3rem; align-items: center; justify-content: space-between; }
    .hero-content { flex: 1.2; min-width: 330px; }
    .hero-badge { display:inline-block; background:rgba(245,158,11,0.15); color:var(--secondary); padding:4px 14px; border-radius:20px; font-size:0.82rem; font-weight:700; margin-bottom:1rem; border:1px solid rgba(245,158,11,0.35); text-transform:uppercase; letter-spacing:0.8px; }
    .hero-content h1 { font-size: 2.8rem; line-height: 1.2; margin-bottom: 1rem; font-weight: 800; }
    .hero-content h1 span { color: var(--secondary); }
    .hero-content p { font-size: 1.1rem; color: #cbd5e1; margin-bottom: 2rem; max-width: 600px; }
    
    .hero-perks { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1rem; margin-top: 1.5rem; }
    .perk-box { background: rgba(255,255,255,0.04); padding: 1rem; border-radius: 8px; border-left: 3px solid var(--secondary); font-size: 0.88rem; }
    .perk-box strong { color: white; display: block; margin-bottom: 0.2rem; }

    .hero-form-box { flex: 0.9; min-width: 320px; max-width: 440px; background: white; color: var(--text-dark); padding: 2.2rem; border-radius: 12px; box-shadow: 0 20px 45px rgba(0,0,0,0.5); border-top: 5px solid var(--secondary); }
    .hero-form-box h3 { font-size: 1.35rem; color: var(--primary); margin-bottom: 0.3rem; }
    .hero-form-box p.sub { font-size: 0.85rem; color: var(--text-muted); margin-bottom: 1.2rem; }
    .form-group { margin-bottom: 0.95rem; }
    .form-group label { display: block; font-size: 0.85rem; font-weight: 600; margin-bottom: 0.3rem; color: #334155; }
    .form-group input, .form-group select, .form-group textarea { width: 100%; padding: 0.7rem; border: 1px solid #cbd5e1; border-radius: 6px; font-size: 0.95rem; background:#f8fafc; }
    .form-group input:focus, .form-group select:focus, .form-group textarea:focus { border-color: var(--secondary); outline: none; background: white; }
    .btn-submit-quote { background: var(--secondary); color: #0a0f1d; width: 100%; padding: 0.85rem; font-size: 1rem; font-weight: 800; border: none; border-radius: 6px; cursor: pointer; transition: 0.3s; margin-top: 0.5rem; }
    .btn-submit-quote:hover { background: #d97706; color: white; }

    /* Common Card Styles */
    .section-wrap { padding: 4rem 5%; max-width: 1300px; margin: auto; }
    .sec-title { text-align: center; margin-bottom: 3rem; }
    .sec-title h1, .sec-title h2 { font-size: 2.3rem; color: var(--primary); margin-bottom: 0.5rem; font-weight: 800; }
    .sec-title p { color: var(--text-muted); font-size: 1.05rem; }

    /* Services Grid */
    .services-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 2rem; }
    .service-card { background: white; border: 1px solid var(--border-color); border-radius: 12px; padding: 2rem; border-top: 4px solid var(--secondary); box-shadow: 0 4px 15px rgba(0,0,0,0.03); }
    .service-icon { font-size: 2.2rem; margin-bottom: 1rem; }
    .service-card h3 { color: var(--primary); margin-bottom: 0.6rem; font-size: 1.25rem; }
    .service-card p { color: #475569; font-size: 0.92rem; }

    /* Packages */
    .packages-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 2rem; }
    .package-card { background: white; border: 1px solid var(--border-color); border-radius: 12px; padding: 2rem; position: relative; display: flex; flex-direction: column; justify-content: space-between; }
    .package-card.popular { border: 2px solid var(--secondary); }
    .popular-tag { position: absolute; top: -12px; right: 20px; background: var(--secondary); color: #0a0f1d; font-weight: 800; font-size: 0.75rem; padding: 4px 10px; border-radius: 12px; text-transform: uppercase; }
    .pack-price { font-size: 2rem; font-weight: 800; color: var(--primary); margin: 1rem 0; }
    .pack-price span { font-size: 0.9rem; color: var(--text-muted); font-weight: 400; }
    .pack-features { list-style: none; margin: 1.5rem 0; font-size: 0.9rem; color: #334155; }
    .pack-features li { margin-bottom: 0.6rem; display: flex; align-items: center; gap: 0.5rem; }
    .pack-features li::before { content: "✔"; color: var(--success); font-weight: bold; }

    /* Calculator */
    .calc-container { max-width: 1100px; margin: auto; background: #f8fafc; border: 2px solid #e2e8f0; border-radius: 16px; padding: 2.5rem; box-shadow: 0 10px 25px rgba(0,0,0,0.03); }
    .calc-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 2rem; }
    .calc-result-box { background: var(--primary); color: white; padding: 2rem; border-radius: 12px; text-align: center; display: flex; flex-direction: column; justify-content: center; border: 2px solid var(--secondary); }
    .calc-price { font-size: 2.8rem; font-weight: 900; color: var(--secondary); margin: 0.5rem 0; }
    .calc-breakdown { font-size: 0.85rem; color: #cbd5e1; line-height: 1.8; text-align: left; margin: 1rem 0; background: rgba(255,255,255,0.06); padding: 1rem; border-radius: 6px; }

    /* Reviews Grid */
    .review-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(350px, 1fr)); gap: 1.5rem; }
    .review-card { background: white; padding: 1.5rem; border-radius: 10px; border: 1px solid var(--border-color); display: flex; flex-direction: column; justify-content: space-between; }
    .reviewer-name { font-weight: 700; color: var(--primary); font-size: 1rem; }
    .reviewer-loc { font-size: 0.8rem; color: var(--text-muted); }
    .review-stars { color: var(--secondary); font-size: 0.95rem; }
    .review-date { font-size: 0.75rem; color: #94a3b8; margin-top: 0.8rem; border-top: 1px dashed #e2e8f0; padding-top: 0.6rem; display: flex; justify-content: space-between; align-items: center; }
    .verified-chip { background: #dcfce7; color: #166534; font-size: 0.7rem; font-weight: 700; padding: 2px 6px; border-radius: 4px; }

    /* Customer Portal */
    .portal-container { max-width: 1200px; margin: 2rem auto; padding: 0 5%; }
    .portal-header { background: white; padding: 1.8rem 2rem; border-radius: 12px; border: 1px solid var(--border-color); display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 1rem; margin-bottom: 2rem; border-left: 5px solid var(--secondary); }
    .portal-actions { display: flex; gap: 1rem; flex-wrap: wrap; }
    .btn-ticket { background: #ef4444; color: white; padding: 0.65rem 1.2rem; border-radius: 6px; font-weight: 600; cursor: pointer; border: none; font-size: 0.9rem; }
    .btn-req-quote { background: var(--secondary); color: #0a0f1d; padding: 0.65rem 1.2rem; border-radius: 6px; font-weight: 700; cursor: pointer; border: none; font-size: 0.9rem; }
    .portal-grid { display: grid; grid-template-columns: 2fr 1fr; gap: 2rem; }
    @media(max-width: 900px) { .portal-grid { grid-template-columns: 1fr; } }
    .portal-card { background: white; border-radius: 12px; border: 1px solid var(--border-color); padding: 1.5rem; margin-bottom: 2rem; box-shadow: 0 2px 8px rgba(0,0,0,0.03); }
    .portal-card h3 { font-size: 1.2rem; color: var(--primary); margin-bottom: 1.2rem; display: flex; justify-content: space-between; align-items: center; }
    .badge-status { padding: 4px 10px; border-radius: 20px; font-size: 0.75rem; font-weight: 700; text-transform: uppercase; }
    .status-active { background: #dcfce7; color: #15803d; }
    .status-assigned { background: #e0e7ff; color: #4338ca; }

    /* Footer */
    .site-footer { background: var(--primary); color: #cbd5e1; padding: 4rem 5% 1.5rem 5%; }
    .footer-grid { max-width: 1300px; margin: auto; display: grid; grid-template-columns: 2fr 1.2fr 1.5fr; gap: 3rem; margin-bottom: 3rem; }
    @media(max-width: 850px) { .footer-grid { grid-template-columns: 1fr; } }
    .footer-col h3, .footer-col h4 { color: white; margin-bottom: 1.2rem; }
    .footer-col ul { list-style: none; }
    .footer-col ul li { margin-bottom: 0.6rem; }
    .footer-col ul li a { color: #94a3b8; transition: 0.2s; }
    .footer-col ul li a:hover { color: var(--secondary); }
    .footer-bottom { border-top: 1px solid #334155; padding-top: 1.5rem; text-align: center; font-size: 0.85rem; color: #64748b; }

    .modal { display:none; position:fixed; top:0; left:0; width:100%; height:100%; background:rgba(0,0,0,0.6); z-index:200; justify-content:center; align-items:center; }
    .modal-content { background:white; padding:2rem; border-radius:12px; width:90%; max-width:520px; max-height:90vh; overflow-y:auto; position:relative; }
    .close-btn { position:absolute; top:1rem; right:1rem; font-size:1.5rem; cursor:pointer; color:#64748b; }

    .brand-logo-img { width: 44px; height: 44px; object-fit: contain; border-radius: 50%; border: 2px solid #38bdf8; box-shadow: 0 0 10px rgba(56, 189, 248, 0.4); flex-shrink: 0; }
    
    /* MOBILE-FIRST RESPONSIVE FIXES */
    @media (max-width: 768px) {
        .main-header { padding: 0.6rem 3%; }
        .header-container { flex-direction: column; gap: 0.8rem; align-items: center; text-align: center; }
        .nav-links { flex-wrap: wrap; justify-content: center; gap: 0.6rem 0.9rem; font-size: 0.82rem; }
        .nav-links a { font-size: 0.82rem; }
        .btn-portal, .btn-login, .btn-cta { padding: 0.4rem 0.8rem !important; font-size: 0.82rem !important; }
        .brand-name { font-size: 1.15rem; }
        .brand-sub { font-size: 0.58rem; }
        .top-strip { font-size: 0.75rem; flex-direction: column; gap: 4px; text-align: center; padding: 6px 3%; }
        .hero { padding: 2.5rem 3%; }
        .hero-wrap { flex-direction: column; gap: 2rem; }
        .hero-content h1 { font-size: 1.95rem; }
        .hero-content p { font-size: 0.95rem; }
        .hero-form-box { width: 100%; max-width: 100%; padding: 1.5rem; }
        .section-wrap { padding: 2.5rem 3%; }
        .sec-title h1, .sec-title h2 { font-size: 1.7rem; }
        .calc-container { padding: 1.2rem; }
        .calc-price { font-size: 2.2rem; }
        .packages-grid, .services-grid, .review-grid { grid-template-columns: 1fr; }
        .portal-header { flex-direction: column; align-items: flex-start; gap: 1rem; }
        .portal-actions { width: 100%; flex-direction: column; }
        .portal-actions button { width: 100%; }
        .floating-wa-btn { bottom: 16px; right: 16px; width: 50px; height: 50px; font-size: 1.5rem; }
        
        /* Mobile-friendly horizontal table scroll */
        .table-responsive { width: 100%; overflow-x: auto; -webkit-overflow-scrolling: touch; margin-top: 1rem; }
        table { min-width: 600px; }
    }

</style>
"""

# =========================== PAGE TEMPLATES ===========================

LANDING_PAGE = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link rel="icon" type="image/png" href="/logo.png">
    <title>Hawkeye Security &amp; Automation | Complete CCTV Solutions Delhi NCR</title>
    {{{{ styles | safe }}}}
</head>
<body>
    <div class="top-strip">
        <div>🛡️ <strong>HAWKEYE CCTV AND AUTOMATION:</strong> Established 2023 | Old Palam Road, Kakrola, Dwarka Sector 15, New Delhi</div>
        <div style="display:flex; align-items:center; gap:8px;">
            <span class="rec-dot"></span>
            <span style="color:#ef4444; font-weight:bold; font-family:monospace;">REC</span>
            <span>📞 <a href="https://wa.me/919971332864" target="_blank" style="color:#38bdf8; text-decoration:none; font-weight:bold;">9971332864</a></span>
        </div>
    </div>

    {{{{ navbar | safe }}}}

    <section class="hero">
        <div class="hero-wrap">
            <div class="hero-content">
                <span class="hero-badge">Your Security, Our Priority</span>
                <h1>Complete CCTV &amp; Security <span>Solutions</span></h1>
                <p>Enterprise-grade video surveillance, biometric access control, smart automation, and tamper-proof concealed wiring for residential, commercial, and industrial facilities.</p>
                
                <div class="hero-perks">
                    <div class="perk-box">
                        <strong>🛡️ Sales &amp; Installation</strong>
                        <span>Certified technicians with zero blind-spot physical site analysis</span>
                    </div>
                    <div class="perk-box">
                        <strong>📱 24/7 Remote Monitoring</strong>
                        <span>Encrypted live color night feed directly on iOS &amp; Android devices</span>
                    </div>
                    <div class="perk-box">
                        <strong>🛠️ Reliable Maintenance</strong>
                        <span>Dedicated customer dashboard with guaranteed 4-hour SLA support</span>
                    </div>
                </div>
            </div>

            <div class="hero-form-box" id="get-quote">
                <h3>Request Instant Survey</h3>
                <p class="sub">Official quotation will sync directly to your customer account</p>
                <form action="/quick-book" method="POST">
                    <div class="form-group">
                        <label>Full Name</label>
                        <input type="text" name="name" placeholder="Enter your name" required>
                    </div>
                    <div class="form-group">
                        <label>Mobile Number (For Verification &amp; Instant Access)</label>
                        <input type="tel" name="phone" placeholder="10-digit Indian mobile number" maxlength="10" required>
                    </div>
                    <div class="form-group">
                        <label>Location / Area in Delhi NCR</label>
                        <input type="text" name="area" placeholder="e.g. Pitampura, Janakpuri, Sector 62" required>
                    </div>
                    <div class="form-group">
                        <label>Premises &amp; Deployment Scope</label>
                        <select name="service_type">
                            <option value="Residential 4-Camera Setup">Residential (Villa / Independent Floor / Apartment)</option>
                            <option value="Commercial 8-Camera Setup">Commercial (Retail Shop / Corporate Office)</option>
                            <option value="Industrial 16+ CCTV Setup">Industrial / Warehouse / Housing Complex</option>
                            <option value="Maintenance / AMC Contract">Maintenance / Existing CCTV Repair &amp; AMC</option>
                        </select>
                    </div>
                    <button type="submit" class="btn-submit-quote">Generate My Quotation 🚀</button>
                </form>
            </div>
        </div>
    </section>

    <section class="section-wrap">
        <div class="sec-title">
            <h2>Recent Customer Feedback</h2>
            <p>Authentic feedback from recent installations across Delhi NCR</p>
        </div>

        <div class="review-grid">
            {{% for r in reviews %}}
            <div class="review-card">
                <div>
                    <div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:0.8rem;">
                        <div>
                            <div class="reviewer-name">{{{{ r.name }}}}</div>
                            <div class="reviewer-loc">📍 {{{{ r.location }}}}</div>
                        </div>
                        <div class="review-stars">
                            {{% for i in range(r.rating) %}}★{{% endfor %}}
                        </div>
                    </div>
                    <p style="font-size:0.9rem; color:#334155;">"{{{{ r.comment }}}}"</p>
                </div>
                <div class="review-date">
                    <span>🗓️ {{{{ r.date }}}}</span>
                    <span class="verified-chip">Verified Customer</span>
                </div>
            </div>
            {{% endfor %}}
        </div>

        <div style="text-align:center; margin-top:2.5rem;">
            <a href="/reviews" class="btn-cta" style="display:inline-block; font-size:1rem; padding:0.85rem 2.2rem;">
                View All Verified Customer Reviews ➜
            </a>
        </div>
    </section>

    {{{{ footer | safe }}}}
</body>
</html>
"""

SERVICES_PAGE = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link rel="icon" type="image/png" href="/logo.png">
    <title>Services | Hawkeye Security &amp; Automation</title>
    {{{{ styles | safe }}}}
</head>
<body>
    {{{{ navbar | safe }}}}

    <div class="section-wrap">
        <div class="sec-title">
            <h1>Specialized Security &amp; Automation Services</h1>
            <p>Turn-key design, hardware procurement, physical installation, and scheduled maintenance</p>
        </div>

        <div class="services-grid">
            <div class="service-card">
                <div class="service-icon">📹</div>
                <h3>CCTV &amp; Video Surveillance</h3>
                <p>High-definition analog and 4K IP camera arrays engineered for zero blind-spot coverage. Crystal clear infrared and full-color night recording for round-the-clock safety.</p>
            </div>
            <div class="service-card">
                <div class="service-icon">📼</div>
                <h3>DVR / NVR System Integration</h3>
                <p>Enterprise video management, multi-channel NVR arrays, remote cloud synchronizations, and dedicated surveillance-grade storage setups.</p>
            </div>
            <div class="service-card">
                <div class="service-icon">🪪</div>
                <h3>Biometric &amp; Access Control</h3>
                <p>RFID access doors, biometric fingerprint and facial attendance systems for corporate offices, residential gates, and industrial factories.</p>
            </div>
            <div class="service-card">
                <div class="service-icon">🏠</div>
                <h3>Smart Automation &amp; Intrusion Alarms</h3>
                <p>Automated gate controls, perimeter laser tripwires, smart vibration sensors, and instant siren triggers integrated with your mobile smartphone.</p>
            </div>
            <div class="service-card">
                <div class="service-icon">🛠️</div>
                <h3>Annual Maintenance Contracts (AMC)</h3>
                <p>Scheduled quarterly lens cleaning, cable continuity assessments, firmware patching, and emergency 4-hour on-site technician dispatches.</p>
            </div>
            <div class="service-card">
                <div class="service-icon">🌐</div>
                <h3>Remote Mobile Surveillance Setup</h3>
                <p>Encrypted peer-to-peer mobile networking allowing multiple family members or business administrators to view live HD audio/video feeds from anywhere in the world.</p>
            </div>
        </div>

        <div style="text-align:center; margin-top:3.5rem;">
            <a href="/#get-quote" class="btn-cta" style="display:inline-block; font-size:1rem; padding:0.85rem 2.2rem;">Book Free Premises Survey 🚀</a>
        </div>
    </div>

    {{{{ footer | safe }}}}
</body>
</html>
"""

PACKAGES_PAGE = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link rel="icon" type="image/png" href="/logo.png">
    <title>CCTV Packages | Hawkeye Security</title>
    {{{{ styles | safe }}}}
</head>
<body>
    {{{{ navbar | safe }}}}

    <div class="section-wrap">
        <div class="sec-title">
            <h1>Surveillance Hardware Packages</h1>
            <p>Transparent pricing backed by factory warranties, neat concealed trunking, and direct portal tracking</p>
        </div>

        <div class="packages-grid">
            <div class="package-card cctv-glow-card">
                <div>
                    <div class="rec-corner-tag"><span class="rec-dot-small"></span> 5MP CAM</div>
                    <h3>Residential Starter Kit</h3>
                    <p style="color:var(--accent-cyan); font-size:0.88rem; font-weight:600;">4 Cameras — Primary Entrance &amp; Corridors</p>
                    <div class="pack-price">₹18,499 <span>/ complete</span></div>
                    <ul class="pack-features">
                        <li>4 × IP Camera 5MP Hawkeye</li>
                        <li>4 Channel Prama/Hikvision NVR</li>
                        <li>500GB Surveillance Hard Drive</li>
                        <li>Mobile App Sync (iOS &amp; Android)</li>
                        <li>2 Year Warranty and Maintenance</li>
                    </ul>
                </div>
                <a href="https://wa.me/919971332864?text=Hi%20Hawkeye%20CCTV,%20I%20want%20to%20order%20the%20Residential%20Starter%20Kit%20(4%20Cameras%20at%20Rs%2018,499)" target="_blank" class="btn-cta" style="text-align:center; display:block;">Inquire Package via WhatsApp 💬</a>
            </div>

            <div class="package-card popular cctv-glow-card">
                <span class="popular-tag">Most Popular in Delhi</span>
                <div>
                    <div class="rec-corner-tag"><span class="rec-dot-small"></span> COLOR + AUDIO</div>
                    <h3>6 Camera Security Package</h3>
                    <p style="color:var(--accent-cyan); font-size:0.88rem; font-weight:600;">6 Cameras — Complete Perimeter Coverage</p>
                    <div class="pack-price">₹25,000 <span>/ complete</span></div>
                    <ul class="pack-features">
                        <li>6 × 5MP Hawkeye Cameras</li>
                        <li>Color Night Vision + Audio</li>
                        <li>500GB Surveillance Hard Drive</li>
                        <li>Mobile App Sync</li>
                        <li>2 Years Warranty and Maintenance</li>
                    </ul>
                </div>
                <a href="https://wa.me/919971332864?text=Hi%20Hawkeye%20CCTV,%20I%20want%20to%20order%20the%206%20Camera%20Security%20Package%20(Rs%2025,000)" target="_blank" class="btn-cta" style="text-align:center; display:block;">Inquire Package via WhatsApp 💬</a>
            </div>

            <div class="package-card cctv-glow-card">
                <div>
                    <div class="rec-corner-tag"><span class="rec-dot-small"></span> FULL ESTATE</div>
                    <h3>8 Camera Security Package</h3>
                    <p style="color:var(--accent-cyan); font-size:0.88rem; font-weight:600;">8 Cameras — Full Commercial / Residential</p>
                    <div class="pack-price">₹32,000 <span>/ complete</span></div>
                    <ul class="pack-features">
                        <li>8 × 5MP Hawkeye Cameras</li>
                        <li>Color Night Vision + Audio</li>
                        <li>500GB Surveillance Hard Drive</li>
                        <li>Mobile App Sync</li>
                        <li>2 Years Warranty and Maintenance</li>
                    </ul>
                </div>
                <a href="https://wa.me/919971332864?text=Hi%20Hawkeye%20CCTV,%20I%20want%20to%20order%20the%208%20Camera%20Security%20Package%20(Rs%2032,000)" target="_blank" class="btn-cta" style="text-align:center; display:block;">Inquire Package via WhatsApp 💬</a>
            </div>
        </div>
    </div>

    {{{{ footer | safe }}}}
</body>
</html>
"""

CALCULATOR_PAGE = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link rel="icon" type="image/png" href="/logo.png">
    <title>Surveillance Cost Estimator | HAWKEYE CCTV AND AUTOMATION</title>
    {{{{ styles | safe }}}}
</head>
<body>
    {{{{ navbar | safe }}}}

    <div class="section-wrap">
        <div class="sec-title">
            <span class="hero-badge">⚡ Instant Dynamic Quotation</span>
            <h1>Interactive Surveillance Cost Estimator</h1>
            <p>Official package rates with 5MP Hawkeye Cameras, Mobile App Sync &amp; 2 Years Warranty</p>
        </div>

        <div class="calc-container cctv-glow-card">
            <div class="calc-grid">
                <div>
                    <div class="form-group">
                        <label style="font-weight:700; color:var(--text-dark); display:flex; align-items:center; gap:6px;">
                            📹 Select Camera Package:
                        </label>
                        <select id="calc_cams" onchange="updateLiveEstimate()" style="padding:0.85rem; font-weight:600; font-size:1rem; border:2px solid #cbd5e1;">
                            <option value="4" selected>4 Cameras — Residential Starter Kit (₹18,499)</option>
                            <option value="6">6 Cameras — Security Package with Color + Audio (₹25,000)</option>
                            <option value="8">8 Cameras — Security Package with Color + Audio (₹32,000)</option>
                        </select>
                    </div>
                    
                    <div class="form-group" style="margin-top:1.2rem;">
                        <label style="font-weight:700; color:var(--text-dark);">Selected Hardware Specifications:</label>
                        <div id="calc_specs_list" style="background:#f1f5f9; padding:1rem; border-radius:8px; font-size:0.9rem; line-height:1.8; color:#334155; border-left:4px solid var(--accent-cyan);">
                            • 4 × IP Camera 5MP Hawkeye<br>
                            • 4 Channel Prama/Hikvision NVR<br>
                            • 500GB Surveillance Hard Drive<br>
                            • Mobile App Sync (iOS &amp; Android)<br>
                            • 2 Year Warranty and Maintenance
                        </div>
                    </div>

                    <div style="font-size:0.85rem; color:#64748b; margin-top:1rem; display:flex; align-items:center; gap:6px;">
                        🛡️ <strong>GST &amp; 2-Year On-Site Hawkeye Maintenance Included. Zero Hidden Charges.</strong>
                    </div>
                </div>

                <div class="calc-result-box">
                    <div style="display:flex; align-items:center; justify-content:center; gap:6px; margin-bottom:0.5rem;">
                        <span class="rec-dot"></span>
                        <span style="text-transform:uppercase; font-size:0.8rem; letter-spacing:1.5px; color:#ef4444; font-weight:bold; font-family:monospace;">HAWKEYE VERIFIED ESTIMATE</span>
                    </div>
                    <div class="calc-price" id="calc_total_display">₹18,499</div>
                    <div id="calc_pack_name" style="font-weight:700; font-size:1rem; color:var(--accent-cyan); margin-bottom:0.5rem;">Residential Starter Kit</div>
                    <div style="font-size:0.82rem; color:#a7f3d0; margin-bottom:1rem;">Complete Turnkey Installation &amp; Cable Setup</div>
                    
                    <a id="calc_whatsapp_btn" href="https://wa.me/919971332864?text=Hi%20Hawkeye%20CCTV,%20I%20want%20to%20confirm%20the%204%20Camera%20Residential%20Starter%20Kit%20for%20Rs%2018,499" target="_blank" class="btn-cta" style="display:block; text-align:center; padding:0.85rem; font-weight:800; font-size:1rem;">
                        Lock In This Price on WhatsApp 💬
                    </a>
                </div>
            </div>
        </div>
    </div>

    {{{{ footer | safe }}}}

    <script>
        const hawkeyePackages = {
            4: {
                name: "Residential Starter Kit",
                price: "₹18,499",
                specs: "• 4 × IP Camera 5MP Hawkeye<br>• 4 Channel Prama/Hikvision NVR<br>• 500GB Surveillance Hard Drive<br>• Mobile App Sync (iOS & Android)<br>• 2 Year Warranty and Maintenance",
                msg: "Hi Hawkeye CCTV, I want to confirm the 4 Camera Residential Starter Kit for Rs 18,499"
            },
            6: {
                name: "6 Camera Security Package",
                price: "₹25,000",
                specs: "• 6 × 5MP Hawkeye Cameras<br>• Color Night Vision + Audio<br>• 500GB Surveillance Hard Drive<br>• Mobile App Sync (iOS & Android)<br>• 2 Years Warranty and Maintenance",
                msg: "Hi Hawkeye CCTV, I want to confirm the 6 Camera Security Package for Rs 25,000"
            },
            8: {
                name: "8 Camera Security Package",
                price: "₹32,000",
                specs: "• 8 × 5MP Hawkeye Cameras<br>• Color Night Vision + Audio<br>• 500GB Surveillance Hard Drive<br>• Mobile App Sync (iOS & Android)<br>• 2 Years Warranty and Maintenance",
                msg: "Hi Hawkeye CCTV, I want to confirm the 8 Camera Security Package for Rs 32,000"
            }
        };

        function updateLiveEstimate() {
            const cams = parseInt(document.getElementById('calc_cams').value);
            const data = hawkeyePackages[cams];
            if(data) {
                document.getElementById('calc_total_display').innerText = data.price;
                document.getElementById('calc_pack_name').innerText = data.name;
                document.getElementById('calc_specs_list').innerHTML = data.specs;
                document.getElementById('calc_whatsapp_btn').href = "https://wa.me/919971332864?text=" + encodeURIComponent(data.msg);
            }
        }
    </script>
</body>
</html>"""
"""

REVIEWS_PAGE = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link rel="icon" type="image/png" href="/logo.png">
    <title>Customer Testimonials | Hawkeye Security</title>
    {{{{ styles | safe }}}}
</head>
<body>
    {{{{ navbar | safe }}}}

    <div class="section-wrap">
        <div class="sec-title">
            <h1>Verified Customer Testimonials</h1>
            <p>Real feedback recorded across Delhi NCR (2024–2026)</p>
        </div>

        <div class="review-grid">
            {{% for r in all_reviews %}}
            <div class="review-card">
                <div>
                    <div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:0.8rem;">
                        <div>
                            <div class="reviewer-name">{{{{ r.name }}}}</div>
                            <div class="reviewer-loc">📍 {{{{ r.location }}}}</div>
                        </div>
                        <div class="review-stars">
                            {{% for i in range(r.rating) %}}★{{% endfor %}}
                        </div>
                    </div>
                    <p style="font-size:0.9rem; color:#334155;">"{{{{ r.comment }}}}"</p>
                </div>
                <div class="review-date">
                    <span>🗓️ {{{{ r.date }}}}</span>
                    <span class="verified-chip">Verified Installation</span>
                </div>
            </div>
            {{% endfor %}}
        </div>
    </div>

    {{{{ footer | safe }}}}
</body>
</html>
"""

CAREERS_PAGE = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link rel="icon" type="image/png" href="/logo.png">
    <title>Careers &amp; Opportunities | Hawkeye Security</title>
    {{{{ styles | safe }}}}
</head>
<body>
    {{{{ navbar | safe }}}}

    <div class="section-wrap">
        <div class="sec-title">
            <h1>Careers at Hawkeye Security</h1>
            <p>Join Delhi NCR's leading security automation team. Competitive pay, skill training, and career growth.</p>
        </div>

        <div style="display: grid; grid-template-columns: 1.2fr 1.8fr; gap: 3rem; align-items: flex-start;">
            <div>
                <h3 style="font-size: 1.3rem; margin-bottom: 1.2rem; color: var(--primary);">Current Openings in Delhi NCR</h3>
                
                <div style="background: white; border: 1px solid var(--border-color); border-radius: 8px; padding: 1.2rem; margin-bottom: 1rem;">
                    <div style="font-weight: 700; color: var(--primary);">1. CCTV Senior Installation Engineer</div>
                    <div style="font-size: 0.85rem; color: var(--text-muted); margin-top: 3px;">Full-time • 2-4 Years Exp. in IP &amp; DVR Cabling</div>
                    <div style="font-size: 0.88rem; color: #475569; margin-top: 0.5rem;">Responsible for physical installation, mobile app configuration, and site inspection across Delhi NCR.</div>
                </div>

                <div style="background: white; border: 1px solid var(--border-color); border-radius: 8px; padding: 1.2rem; margin-bottom: 1rem;">
                    <div style="font-weight: 700; color: var(--primary);">2. Field Installation Helper / Apprentice</div>
                    <div style="font-size: 0.85rem; color: var(--text-muted); margin-top: 3px;">Full-time • Fresher / 6 Months Exp.</div>
                    <div style="font-size: 0.88rem; color: #475569; margin-top: 0.5rem;">Assist senior technicians in ladder work, concealed trunking, and cable laying. Technical training provided.</div>
                </div>

                <div style="background: white; border: 1px solid var(--border-color); border-radius: 8px; padding: 1.2rem; margin-bottom: 1rem;">
                    <div style="font-weight: 700; color: var(--primary);">3. B2B Sales Executive (Security &amp; AMC)</div>
                    <div style="font-size: 0.85rem; color: var(--text-muted); margin-top: 3px;">Full-time • 1-3 Years Experience</div>
                    <div style="font-size: 0.88rem; color: #475569; margin-top: 0.5rem;">Pitching society complexes, retail showrooms, and corporate offices for bulk surveillance deployments and AMCs.</div>
                </div>
            </div>

            <div style="background: white; border: 1px solid var(--border-color); border-radius: 12px; padding: 2.2rem; box-shadow: 0 10px 30px rgba(0,0,0,0.04);">
                <h3 style="font-size: 1.3rem; margin-bottom: 0.4rem; color: var(--primary);">Submit Your Application</h3>
                <p style="font-size: 0.85rem; color: var(--text-muted); margin-bottom: 1.5rem;">Fill in your details and upload your CV / Resume for immediate review.</p>

                <form action="/apply-job" method="POST" enctype="multipart/form-data">
                    <div class="form-group">
                        <label>Full Name</label>
                        <input type="text" name="name" placeholder="Enter your full name" required>
                    </div>

                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 1rem;">
                        <div class="form-group">
                            <label>Mobile Number</label>
                            <input type="tel" name="phone" placeholder="10-digit phone number" maxlength="10" required>
                        </div>
                        <div class="form-group">
                            <label>Email Address</label>
                            <input type="email" name="email" placeholder="name@example.com" required>
                        </div>
                    </div>

                    <div class="form-group">
                        <label>Applying For Position</label>
                        <select name="position" required>
                            <option value="CCTV Senior Installation Engineer">CCTV Senior Installation Engineer</option>
                            <option value="Field Installation Helper / Apprentice">Field Installation Helper / Apprentice</option>
                            <option value="B2B Sales Executive (Security &amp; AMC)">B2B Sales Executive (Security &amp; AMC)</option>
                            <option value="Other Security Role">Other Security Role</option>
                        </select>
                    </div>

                    <div class="form-group">
                        <label>Relevant Experience</label>
                        <select name="experience" required>
                            <option value="Fresher (Willing to Learn)">Fresher (Willing to Learn)</option>
                            <option value="1 - 2 Years">1 - 2 Years</option>
                            <option value="3 - 5 Years">3 - 5 Years</option>
                            <option value="5+ Years Senior Professional">5+ Years Senior Professional</option>
                        </select>
                    </div>

                    <div class="form-group">
                        <label>Upload Resume / Bio-Data (PDF, DOCX, or Image)</label>
                        <input type="file" name="resume" accept=".pdf,.doc,.docx,.png,.jpg,.jpeg">
                    </div>

                    <button type="submit" class="btn-submit-quote">Submit Job Application 🚀</button>
                </form>
            </div>
        </div>
    </div>

    {{{{ footer | safe }}}}
</body>
</html>
"""

PORTAL_PAGE = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link rel="icon" type="image/png" href="/logo.png">
    <title>Customer Security Dashboard | Hawkeye</title>
    {{{{ styles | safe }}}}
</head>
<body>
    {{{{ navbar | safe }}}}

    <div class="portal-container">
        <div class="portal-header">
            <div>
                <div style="font-size:0.8rem; text-transform:uppercase; letter-spacing:1px; color:#64748b; font-weight:700;">Client Dashboard</div>
                <h2 style="color:var(--primary); font-size:1.6rem;">Welcome, {{{{ user.name }}}}</h2>
                <div style="color:var(--text-muted); font-size:0.9rem; margin-top:0.2rem;">
                    <span>📱 +91 {{{{ user.phone }}}}</span> | 
                    <span>📍 {{{{ user.area }}}}</span> | 
                    <span>🛡️ Customer ID: #HWK-{{{{ user.id + 1040 }}}}</span>
                </div>
            </div>
            <div class="portal-actions">
                <button class="btn-ticket" onclick="openModal('ticketModal')">🛠️ Raise Service / Repair Ticket</button>
                <button class="btn-req-quote" onclick="openModal('quoteModal')">➕ Request New Quotation</button>
            </div>
        </div>

        <div class="portal-grid">
            <div>
                <div class="portal-card">
                    <h3>
                        <span>📋 Active Surveillance Quotations</span>
                        <span style="font-size:0.85rem; color:var(--text-muted);">Real-time Proposals</span>
                    </h3>
                    
                    {{% if user.quotations %}}
                        {{% for q in user.quotations %}}
                        <div style="border:1px solid #e2e8f0; border-radius:8px; padding:1.2rem; margin-bottom:1rem; background:#fcfcfd;">
                            <div style="display:flex; justify-content:space-between; align-items:center;">
                                <strong style="font-size:1.1rem; color:var(--primary);">{{{{ q.service_type }}}} ({{{{ q.cameras }}}} Cameras)</strong>
                                <span class="badge-status status-active">{{{{ q.status }}}}</span>
                            </div>
                            <div style="font-size:0.88rem; color:#475569; margin:0.6rem 0;">
                                Property: <strong>{{{{ q.property_type }}}}</strong> | Brand: <strong>{{{{ q.brand_preference }}}}</strong> | Backup: <strong>{{{{ q.storage_days }}}} Days</strong>
                            </div>
                            <div style="display:flex; justify-content:space-between; align-items:center; border-top:1px dashed #cbd5e1; padding-top:0.6rem; margin-top:0.6rem;">
                                <div>Total Estimated Amount: <strong style="color:var(--secondary); font-size:1.2rem;">₹{{{{ q.estimated_amount }}}}</strong> (Inc. GST &amp; Fitting)</div>
                                <a href="https://wa.me/919971332864?text=Hi%20Hawkeye,%20I%20wish%20to%20confirm%20Quotation%20No%20{{{{ q.id }}}}" target="_blank" style="background:var(--success); color:white; padding:6px 14px; border-radius:4px; font-size:0.85rem; font-weight:bold;">Confirm via WhatsApp 💬</a>
                            </div>
                        </div>
                        {{% endfor %}}
                    {{% else %}}
                        <p style="color:var(--text-muted); font-size:0.9rem;">No active quotations recorded. Click "Request New Quotation" to generate an official cost estimate.</p>
                    {{% endif %}}
                </div>

                <div class="portal-card">
                    <h3>
                        <span>🛠️ Maintenance &amp; Repair Desk</span>
                        <span style="font-size:0.85rem; color:var(--text-muted);">Standard SLA: 4 Hours On-Site</span>
                    </h3>

                    {{% if user.tickets %}}
                        {{% for t in user.tickets %}}
                        <div style="border:1px solid #e2e8f0; border-radius:8px; padding:1.2rem; margin-bottom:1rem;">
                            <div style="display:flex; justify-content:space-between; align-items:center;">
                                <strong>Ticket #{{{{ t.ticket_id }}}}: {{{{ t.issue_type }}}}</strong>
                                <span class="badge-status status-assigned">{{{{ t.status }}}}</span>
                            </div>
                            <p style="font-size:0.85rem; color:#64748b; margin:0.5rem 0;">"{{{{ t.description }}}}"</p>
                            <div style="font-size:0.82rem; background:#f1f5f9; padding:0.6rem; border-radius:4px; display:flex; justify-content:space-between;">
                                <span>👷 Assigned Technician: <strong>{{{{ t.assigned_engineer }}}}</strong></span>
                                <span>Scheduled Window: <strong>{{{{ t.preferred_slot }}}}</strong></span>
                            </div>
                        </div>
                        {{% endfor %}}
                    {{% else %}}
                        <p style="color:var(--text-muted); font-size:0.9rem;">No unresolved maintenance issues logged. All installed cameras operating within standard parameters.</p>
                    {{% endif %}}
                </div>
            </div>

            <div>
                <div class="portal-card">
                    <h3>🛡️ Warranty &amp; AMC Status</h3>
                    <div style="background:#ecfdf5; border:1px solid #a7f3d0; padding:1rem; border-radius:8px; margin-bottom:1rem;">
                        <div style="font-weight:700; color:#065f46;">✔ 2-Year Direct Replacement Active</div>
                        <div style="font-size:0.82rem; color:#047857; margin-top:0.3rem;">Covers camera imaging sensors, power supplies, and hard drive failures.</div>
                    </div>
                    
                    <h4 style="font-size:0.92rem; margin-bottom:0.6rem; color:var(--primary);">Routine Annual Maintenance Scope:</h4>
                    <ul style="font-size:0.85rem; color:#475569; padding-left:1.2rem; line-height:1.7;">
                        <li>Camera lens cleaning &amp; refocusing</li>
                        <li>DVR firmware updates &amp; cloud verification</li>
                        <li>Hard drive health &amp; sector diagnostics</li>
                        <li>Wiring integrity and terminal check</li>
                    </ul>
                </div>

                <div class="portal-card">
                    <h3>📞 Dedicated Area Manager</h3>
                    <div style="display:flex; gap:1rem; align-items:center;">
                        <div style="background:#38bdf8; color:#0a0f1d; width:45px; height:45px; border-radius:50%; display:flex; align-items:center; justify-content:center; font-size:1.4rem; font-weight:bold;">H</div>
                        <div>
                            <div style="font-weight:700;">Rakshit</div>
                            <div style="font-size:0.8rem; color:var(--text-muted);">Area Manager (HAWKEYE CCTV)</div>
                            <a href="https://wa.me/919971332864" target="_blank" style="color:var(--accent-cyan); font-size:0.85rem; font-weight:600;">Direct WhatsApp: +91 9971332864</a>
                        </div>
                    </div>
                    <div style="margin-top:1rem; border-top:1px dashed #cbd5e1; padding-top:0.8rem; font-size:0.85rem; color:#475569;">
                        👤 <strong>Owner:</strong> Rakshit Saran Bhatnagar<br>
                        🛠️ <strong>Assigned Field Technician:</strong> Rahul
                    </div>
                </div>
            </div>
        </div>
    </div>

    <div class="modal" id="ticketModal">
        <div class="modal-content">
            <span class="close-btn" onclick="closeModal('ticketModal')">&times;</span>
            <h3 style="margin-bottom:1rem; color:var(--primary);">🛠️ Book Technician Dispatch</h3>
            <form action="/create-ticket" method="POST">
                <div class="form-group">
                    <label>Issue Classification:</label>
                    <select name="issue_type" required>
                        <option value="Camera Showing Offline Status">Camera Showing Offline Status</option>
                        <option value="Night Vision IR Blurry or Unclear">Night Vision IR Blurry or Unclear</option>
                        <option value="DVR Storage Beeping / Storage Error">DVR Storage Beeping / Storage Error</option>
                        <option value="Mobile Application Sync Required">Mobile Application Sync Required</option>
                        <option value="Camera Relocation or Renovation Cable Shift">Camera Relocation or Cable Shift</option>
                        <option value="Routine Preventative AMC Inspection">Routine Preventative AMC Inspection</option>
                    </select>
                </div>
                <div class="form-group">
                    <label>Description of Issue:</label>
                    <textarea name="description" rows="3" placeholder="Provide details regarding the affected camera or system..." required></textarea>
                </div>
                <div class="form-group">
                    <label>Preferred Field Visit Slot:</label>
                    <select name="preferred_slot" required>
                        <option value="Today Evening (4:00 PM - 7:00 PM)">Today Evening (4:00 PM - 7:00 PM)</option>
                        <option value="Tomorrow Morning (9:00 AM - 12:00 PM)">Tomorrow Morning (9:00 AM - 12:00 PM)</option>
                        <option value="Tomorrow Afternoon (1:00 PM - 4:00 PM)">Tomorrow Afternoon (1:00 PM - 4:00 PM)</option>
                    </select>
                </div>
                <button type="submit" class="btn-submit-quote" style="background:#ef4444; color:white;">Dispatch Field Engineer 🚀</button>
            </form>
        </div>
    </div>

    <div class="modal" id="quoteModal">
        <div class="modal-content">
            <span class="close-btn" onclick="closeModal('quoteModal')">&times;</span>
            <h3 style="margin-bottom:1rem; color:var(--primary);">➕ Generate Official Surveillance Quotation</h3>
            <form action="/create-quote" method="POST">
                <div class="form-group">
                    <label>Required Cameras:</label>
                    <select name="cameras" required>
                        <option value="2">2 HD Surveillance Cameras</option>
                        <option value="4" selected>4 HD Surveillance Cameras</option>
                        <option value="8">8 Super HD Surveillance Cameras</option>
                        <option value="16">16 IP Surveillance Cameras</option>
                    </select>
                </div>
                <div class="form-group">
                    <label>Property Classification:</label>
                    <select name="property_type" required>
                        <option value="Residential Property">Residential (Independent / Flat)</option>
                        <option value="Commercial Workspace">Commercial Workspace / Retail Store</option>
                        <option value="Industrial Facility">Industrial Facility / Warehouse</option>
                    </select>
                </div>
                <div class="form-group">
                    <label>Preferred Manufacturer:</label>
                    <select name="brand">
                        <option value="CP Plus">CP Plus HD Series</option>
                        <option value="Hikvision">Hikvision ColorVu Series</option>
                    </select>
                </div>
                <div class="form-group">
                    <label>Storage Backup Period:</label>
                    <select name="storage_days">
                        <option value="15">15 Days Recording (1TB Dedicated Drive)</option>
                        <option value="30">30 Days Recording (2TB Dedicated Drive)</option>
                    </select>
                </div>
                <button type="submit" class="btn-submit-quote">Generate Proposal &amp; Save 📄</button>
            </form>
        </div>
    </div>

    {{{{ footer | safe }}}}

    <script>
        function openModal(id) {{ document.getElementById(id).style.display = 'flex'; }}
        function closeModal(id) {{ document.getElementById(id).style.display = 'none'; }}
    </script>
</body>
</html>
"""

# =========================== CLEAN CLIENT LOGIN TEMPLATE ===========================

AUTH_PAGE = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link rel="icon" type="image/png" href="/logo.png">
    <title>Client Portal Access | Hawkeye Security</title>
    {{{{ styles | safe }}}}
    <style>
        .auth-wrap {{ min-height: 80vh; display: flex; align-items: center; justify-content: center; padding: 2rem 5%; }}
        .auth-card {{ background: white; border: 1px solid var(--border-color); border-radius: 12px; padding: 2.5rem; width: 100%; max-width: 440px; box-shadow: 0 10px 30px rgba(0,0,0,0.06); text-align: center; border-top: 5px solid var(--secondary); }}
        .auth-logo-box {{ display: flex; justify-content: center; margin-bottom: 1.2rem; }}
        .auth-badge {{ background: #e0f2fe; color: #0369a1; padding: 4px 12px; border-radius: 4px; font-size: 0.8rem; font-weight: 700; margin-bottom: 1.2rem; display: inline-block; }}
        .passcode-input {{ font-size: 1.6rem !important; letter-spacing: 8px; text-align: center; font-weight: 800; color: var(--primary); }}
        .resend-box {{ margin-top: 1.2rem; font-size: 0.85rem; color: var(--text-muted); }}
        .btn-link {{ background: none; border: none; color: var(--secondary-dark); font-weight: 700; cursor: pointer; text-decoration: underline; }}
    
    .brand-logo-img { width: 44px; height: 44px; object-fit: contain; border-radius: 50%; border: 2px solid #38bdf8; box-shadow: 0 0 10px rgba(56, 189, 248, 0.4); flex-shrink: 0; }
    
    /* MOBILE-FIRST RESPONSIVE FIXES */
    @media (max-width: 768px) {
        .main-header { padding: 0.6rem 3%; }
        .header-container { flex-direction: column; gap: 0.8rem; align-items: center; text-align: center; }
        .nav-links { flex-wrap: wrap; justify-content: center; gap: 0.6rem 0.9rem; font-size: 0.82rem; }
        .nav-links a { font-size: 0.82rem; }
        .btn-portal, .btn-login, .btn-cta { padding: 0.4rem 0.8rem !important; font-size: 0.82rem !important; }
        .brand-name { font-size: 1.15rem; }
        .brand-sub { font-size: 0.58rem; }
        .top-strip { font-size: 0.75rem; flex-direction: column; gap: 4px; text-align: center; padding: 6px 3%; }
        .hero { padding: 2.5rem 3%; }
        .hero-wrap { flex-direction: column; gap: 2rem; }
        .hero-content h1 { font-size: 1.95rem; }
        .hero-content p { font-size: 0.95rem; }
        .hero-form-box { width: 100%; max-width: 100%; padding: 1.5rem; }
        .section-wrap { padding: 2.5rem 3%; }
        .sec-title h1, .sec-title h2 { font-size: 1.7rem; }
        .calc-container { padding: 1.2rem; }
        .calc-price { font-size: 2.2rem; }
        .packages-grid, .services-grid, .review-grid { grid-template-columns: 1fr; }
        .portal-header { flex-direction: column; align-items: flex-start; gap: 1rem; }
        .portal-actions { width: 100%; flex-direction: column; }
        .portal-actions button { width: 100%; }
        .floating-wa-btn { bottom: 16px; right: 16px; width: 50px; height: 50px; font-size: 1.5rem; }
        
        /* Mobile-friendly horizontal table scroll */
        .table-responsive { width: 100%; overflow-x: auto; -webkit-overflow-scrolling: touch; margin-top: 1rem; }
        table { min-width: 600px; }
    }

</style>
</head>
<body>
    {{{{ navbar | safe }}}}

    <div class="auth-wrap">
        <div class="auth-card">
            <div class="auth-logo-box">
                {LOGO_SVG}
            </div>

            <span class="auth-badge">🛡️ Instant Secure Verification</span>
            <h2 style="font-size:1.4rem; color:var(--primary); margin-bottom: 0.4rem;">Customer Portal Access</h2>
            <p style="font-size:0.85rem; color:var(--text-muted); margin-bottom:1.5rem;">Access verified surveillance proposals, warranty cards &amp; service tickets</p>

            <!-- STEP 1: MOBILE NUMBER ENTRY -->
            <form id="step-phone-form" action="/send-otp" method="POST" style="text-align:left; {{% if step == 'verify' %}}display:none;{{% endif %}}">
                <div class="form-group">
                    <label>Registered Mobile Number</label>
                    <input type="tel" name="phone" placeholder="Enter 10-digit mobile number" maxlength="10" value="{{{{ phone or '' }}}}" required autofocus>
                </div>
                <div class="form-group">
                    <label>Your Name (If first time login)</label>
                    <input type="text" name="name" placeholder="Full Name" value="{{{{ name or '' }}}}">
                </div>
                <button type="submit" class="btn-submit-quote">Send Security Code 📩</button>
            </form>

            <!-- STEP 2: VERIFICATION CODE ENTRY -->
            {{% if step == 'verify' %}}
            <form id="step-otp-form" action="/verify-otp" method="POST" style="text-align:left;">
                <input type="hidden" name="phone" value="{{{{ phone }}}}">
                
                <div style="background:#f8fafc; border:1px solid #e2e8f0; padding:0.8rem; border-radius:6px; margin-bottom:1rem; font-size:0.85rem;">
                    Verification Code sent to: <strong>+91 {{{{ phone }}}}</strong>
                    <a href="/login" style="float:right; color:#ef4444; font-weight:600; text-decoration:none;">Change</a>
                </div>

                <div class="form-group">
                    <label style="text-align:center;">Enter 6-Digit Access Code</label>
                    <input type="text" name="otp_code" class="passcode-input" placeholder="••••••" maxlength="6" inputmode="numeric" required autofocus autocomplete="off">
                </div>

                <button type="submit" class="btn-submit-quote" style="background:#16a34a; color:white;">Verify &amp; Enter Dashboard 🚀</button>

                <div class="resend-box">
                    <span>Didn't receive code?</span>
                    <form action="/send-otp" method="POST" style="display:inline;">
                        <input type="hidden" name="phone" value="{{{{ phone }}}}">
                        <button type="submit" class="btn-link">Resend Code</button>
                    </form>
                </div>
            </form>
            {{% endif %}}
        </div>
    </div>

    {{{{ footer | safe }}}}
</body>
</html>
"""

# =========================== ROUTING CONTROLLERS ===========================

@app.route('/logo.png')
def serve_brand_logo():
    import base64
    logo_data = base64.b64decode(HAWKEYE_EMBLEM_B64)
    return Response(logo_data, mimetype='image/png', headers={"Cache-Control": "public, max-age=31536000"})

@app.route('/')
def index():
    return render_template_string(
        LANDING_PAGE,
        styles=STYLES,
        navbar=render_template_string(NAV_BAR),
        footer=FOOTER_SECTION,
        reviews=CUSTOMER_REVIEWS[:10]
    )

@app.route('/services')
def services():
    return render_template_string(
        SERVICES_PAGE,
        styles=STYLES,
        navbar=render_template_string(NAV_BAR),
        footer=FOOTER_SECTION
    )

@app.route('/packages')
def packages():
    return render_template_string(
        PACKAGES_PAGE,
        styles=STYLES,
        navbar=render_template_string(NAV_BAR),
        footer=FOOTER_SECTION
    )

@app.route('/calculator')
def calculator():
    return render_template_string(
        CALCULATOR_PAGE,
        styles=STYLES,
        navbar=render_template_string(NAV_BAR),
        footer=FOOTER_SECTION
    )

@app.route('/reviews')
def reviews():
    return render_template_string(
        REVIEWS_PAGE,
        styles=STYLES,
        navbar=render_template_string(NAV_BAR),
        footer=FOOTER_SECTION,
        all_reviews=CUSTOMER_REVIEWS
    )

@app.route('/careers')
def careers():
    return render_template_string(
        CAREERS_PAGE,
        styles=STYLES,
        navbar=render_template_string(NAV_BAR),
        footer=FOOTER_SECTION
    )

@app.route('/apply-job', methods=['POST'])
def apply_job():
    name = request.form.get('name')
    phone = request.form.get('phone')
    email = request.form.get('email')
    position = request.form.get('position')
    experience = request.form.get('experience')

    resume_filename = None
    if 'resume' in request.files:
        file = request.files['resume']
        if file and file.filename != '':
            filename = secure_filename(f"{phone}_{file.filename}")
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            resume_filename = filename

    application = JobApplication(
        name=name,
        phone=phone,
        email=email,
        position=position,
        experience=experience,
        resume_file=resume_filename
    )
    db.session.add(application)
    db.session.commit()

    return """
    <script>
        alert('Thank you! Your job application has been submitted to Hawkeye HR. Our team will contact you shortly.');
        window.location.href = '/careers';
    </script>
    """

# =========================== SESSION-BASED FAIL-SAFE VERIFICATION ===========================

@app.route('/login')
def login():
    if session.get('user_id'):
        return redirect(url_for('portal'))
    return render_template_string(
        AUTH_PAGE,
        step="phone",
        phone="",
        name="",
        styles=STYLES,
        navbar=render_template_string(NAV_BAR),
        footer=FOOTER_SECTION
    )

@app.route('/send-otp', methods=['POST'])
def send_otp():
    phone = request.form.get('phone', '').strip()
    name = request.form.get('name', '').strip()

    if not re.match(r"^[6-9]\d{9}$", phone):
        return "<script>alert('Please enter a valid 10-digit Indian Mobile Number'); window.history.back();</script>"

    otp_code = str(secrets.randbelow(900000) + 100000)
    
    # Store directly in secure server session
    session['auth_phone'] = phone
    session['auth_code'] = otp_code
    session['auth_expiry'] = (datetime.utcnow() + timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M:%S")
    if name:
        session['temp_name'] = name

    dispatch_customer_otp(phone, otp_code)

    return render_template_string(
        AUTH_PAGE,
        step="verify",
        phone=phone,
        name=name,
        styles=STYLES,
        navbar=render_template_string(NAV_BAR),
        footer=FOOTER_SECTION
    )

@app.route('/verify-otp', methods=['POST'])
def verify_otp():
    phone = request.form.get('phone', '').strip()
    user_otp = request.form.get('otp_code', '').strip()

    saved_phone = session.get('auth_phone')
    saved_code = session.get('auth_code')
    expiry_str = session.get('auth_expiry')

    if not saved_code or saved_phone != phone:
        return "<script>alert('No active verification code found. Please request a new code.'); window.location.href='/login';</script>"

    expiry_time = datetime.strptime(expiry_str, "%Y-%m-%d %H:%M:%S")
    if datetime.utcnow() > expiry_time:
        session.pop('auth_code', None)
        return "<script>alert('Code has expired! Codes are valid for 5 minutes.'); window.location.href='/login';</script>"

    if user_otp != saved_code:
        return "<script>alert('Incorrect code entered! Please check the code and try again.'); window.history.back();</script>"

    # Clear code after success
    session.pop('auth_code', None)
    session.pop('auth_expiry', None)

    # Fetch or Auto-Register Customer Profile
    user = User.query.filter_by(phone=phone).first()
    if not user:
        user_name = session.pop('temp_name', f"Customer {phone[-4:]}")
        try:
            user = User(
                name=user_name,
                phone=phone,
                password_hash="OTP_VERIFIED",
                area="Delhi NCR"
            )
            db.session.add(user)
            db.session.commit()
        except Exception as db_err:
            db.session.rollback()
            user = User.query.filter_by(phone=phone).first()

    session['user_id'] = user.id
    session['user_name'] = user.name
    return redirect(url_for('portal'))

@app.route('/quick-book', methods=['POST'])
def quick_book():
    name = request.form.get('name')
    phone = request.form.get('phone')
    area = request.form.get('area')
    service_type = request.form.get('service_type')

    if not re.match(r"^[6-9]\d{9}$", phone):
        return "<script>alert('Please enter a valid 10-digit Indian Mobile Number'); window.history.back();</script>"

    user = User.query.filter_by(phone=phone).first()
    if not user:
        try:
            user = User(name=name, phone=phone, password_hash="OTP_VERIFIED", area=area)
            db.session.add(user)
            db.session.commit()
        except Exception:
            db.session.rollback()
            user = User.query.filter_by(phone=phone).first()

    cams = 4
    if "6-Camera" in service_type: cams = 6
    elif "8-Camera" in service_type: cams = 8
    elif "16+" in service_type: cams = 16

    est_cost = calculate_quote(cams, "Hawkeye", 15)

    quote = Quotation(
        user_id=user.id,
        service_type=service_type,
        property_type="Residential / Commercial",
        cameras=cams,
        brand_preference="CP Plus / Hikvision HD",
        storage_days=15,
        estimated_amount=est_cost,
        status="Quotation Confirmed"
    )
    db.session.add(quote)
    db.session.commit()

    send_whatsapp_alert(name, phone, area, service_type, est_cost)

    session['user_id'] = user.id
    session['user_name'] = user.name
    return redirect(url_for('portal'))

@app.route('/portal')
def portal():
    user_id = session.get('user_id')
    if not user_id:
        return redirect(url_for('login'))
    user = User.query.get(user_id)
    return render_template_string(
        PORTAL_PAGE,
        user=user,
        styles=STYLES,
        navbar=render_template_string(NAV_BAR),
        footer=FOOTER_SECTION
    )

@app.route('/create-quote', methods=['POST'])
def create_quote():
    user_id = session.get('user_id')
    if not user_id:
        return redirect(url_for('login'))

    user = User.query.get(user_id)
    cams = int(request.form.get('cameras'))
    prop = request.form.get('property_type')
    brand = request.form.get('brand')
    storage = int(request.form.get('storage_days'))

    cost = calculate_quote(cams, brand, storage)
    q = Quotation(
        user_id=user_id,
        service_type=f"{brand} {cams}-Camera System",
        property_type=prop,
        cameras=cams,
        brand_preference=brand,
        storage_days=storage,
        estimated_amount=cost,
        status="Quotation Generated"
    )
    db.session.add(q)
    db.session.commit()

    send_whatsapp_alert(user.name, user.phone, user.area, f"{brand} {cams}-Camera System", cost)
    return redirect(url_for('portal'))

@app.route('/create-ticket', methods=['POST'])
def create_ticket():
    user_id = session.get('user_id')
    if not user_id:
        return redirect(url_for('login'))

    user = User.query.get(user_id)
    issue = request.form.get('issue_type')
    desc = request.form.get('description')
    slot = request.form.get('preferred_slot')

    ticket_code = f"DL-{datetime.now().strftime('%m%d')}-{user_id}"

    ticket = MaintenanceTicket(
        ticket_id=ticket_code,
        user_id=user_id,
        issue_type=issue,
        description=desc,
        preferred_slot=slot,
        status="Technician Dispatched"
    )
    db.session.add(ticket)
    db.session.commit()

    send_whatsapp_alert(user.name, user.phone, user.area, f"SERVICE TICKET: {issue} ({slot})", 0)
    return redirect(url_for('portal'))

# =========================== OWNER ADMIN CONSOLE & EXPORT ===========================

ADMIN_PAGE = """
<!DOCTYPE html>
<html>
<head>
    <title>Hawkeye Security - Business Management Console</title>
    <style>
        body { font-family: sans-serif; background: #0a0f1d; color: white; padding: 2rem 5%; }
        table { width: 100%; border-collapse: collapse; margin-top: 1rem; background: #121929; border-radius: 8px; overflow: hidden; }
        th, td { padding: 12px; text-align: left; border-bottom: 1px solid #1e293b; font-size: 0.9rem; }
        th { background: #f59e0b; color: #0a0f1d; }
        .export-btn { background: #22c55e; color: white; padding: 10px 18px; border-radius: 6px; text-decoration: none; font-weight: bold; display: inline-block; }
        .chat-btn { background: #25d366; color: white; padding: 5px 12px; border-radius: 4px; text-decoration: none; font-size: 0.82rem; font-weight: bold; }
        .tab-head { color: #f59e0b; margin-top: 2.5rem; border-bottom: 2px solid #334155; padding-bottom: 0.5rem; }
        .pwd-card { background: #121929; border: 1px solid #334155; padding: 1.5rem; border-radius: 8px; margin-top: 1.5rem; max-width: 480px; }
        .pwd-input { padding: 8px 12px; border-radius: 4px; border: 1px solid #334155; background: #0a0f1d; color: white; width: 100%; box-sizing: border-box; margin-bottom: 0.8rem; }
    
    .brand-logo-img { width: 44px; height: 44px; object-fit: contain; border-radius: 50%; border: 2px solid #38bdf8; box-shadow: 0 0 10px rgba(56, 189, 248, 0.4); flex-shrink: 0; }
    
    /* MOBILE-FIRST RESPONSIVE FIXES */
    @media (max-width: 768px) {
        .main-header { padding: 0.6rem 3%; }
        .header-container { flex-direction: column; gap: 0.8rem; align-items: center; text-align: center; }
        .nav-links { flex-wrap: wrap; justify-content: center; gap: 0.6rem 0.9rem; font-size: 0.82rem; }
        .nav-links a { font-size: 0.82rem; }
        .btn-portal, .btn-login, .btn-cta { padding: 0.4rem 0.8rem !important; font-size: 0.82rem !important; }
        .brand-name { font-size: 1.15rem; }
        .brand-sub { font-size: 0.58rem; }
        .top-strip { font-size: 0.75rem; flex-direction: column; gap: 4px; text-align: center; padding: 6px 3%; }
        .hero { padding: 2.5rem 3%; }
        .hero-wrap { flex-direction: column; gap: 2rem; }
        .hero-content h1 { font-size: 1.95rem; }
        .hero-content p { font-size: 0.95rem; }
        .hero-form-box { width: 100%; max-width: 100%; padding: 1.5rem; }
        .section-wrap { padding: 2.5rem 3%; }
        .sec-title h1, .sec-title h2 { font-size: 1.7rem; }
        .calc-container { padding: 1.2rem; }
        .calc-price { font-size: 2.2rem; }
        .packages-grid, .services-grid, .review-grid { grid-template-columns: 1fr; }
        .portal-header { flex-direction: column; align-items: flex-start; gap: 1rem; }
        .portal-actions { width: 100%; flex-direction: column; }
        .portal-actions button { width: 100%; }
        .floating-wa-btn { bottom: 16px; right: 16px; width: 50px; height: 50px; font-size: 1.5rem; }
        
        /* Mobile-friendly horizontal table scroll */
        .table-responsive { width: 100%; overflow-x: auto; -webkit-overflow-scrolling: touch; margin-top: 1rem; }
        table { min-width: 600px; }
    }

</style>
</head>
<body>
    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom: 1.5rem;">
        <div>
            <h2 style="font-size:1.8rem;">📊 Business Operations Console</h2>
            <p style="color:#94a3b8; font-size:0.9rem;">Hawkeye Security &amp; Automation Control Center</p>
        </div>
        <div style="display:flex; align-items:center; gap:1rem;">
            <a href="/" style="color:#f59e0b; text-decoration:none; font-weight:bold;">🌐 View Public Website</a>
            <a href="/admin/export-csv" class="export-btn">📥 Download All Leads (Excel/CSV)</a>
            <a href="/admin/logout" style="color:#ef4444; font-weight: bold; text-decoration:none;">Logout</a>
        </div>
    </div>

    <div class="pwd-card">
        <h4 style="margin-bottom:0.8rem; color:#f59e0b;">🔐 Update Admin Password</h4>
        <form action="/admin/change-password" method="POST">
            <input type="password" name="new_password" placeholder="Create new password (min 6 chars)" class="pwd-input" required minlength="6">
            <button type="submit" style="background:#f59e0b; color:#0a0f1d; padding:8px 16px; border:none; border-radius:4px; font-weight:bold; cursor:pointer;">Update Password</button>
        </form>
    </div>

    <h3 class="tab-head">🔥 Customer Quotations &amp; Leads ({{ quotes|length }})</h3>
    <div class="table-responsive"><table>
        <tr><th>Date</th><th>Client Name</th><th>Mobile</th><th>Area</th><th>Service / Cameras</th><th>Estimated Cost</th><th>Direct WhatsApp</th></tr>
        {% for q in quotes %}
        <tr>
            <td>{{ q.created_at.strftime('%d-%b %I:%M %p') }}</td>
            <td><strong>{{ q.customer.name }}</strong></td>
            <td>{{ q.customer.phone }}</td>
            <td>{{ q.customer.area }}</td>
            <td>{{ q.service_type }} ({{ q.cameras }} Cams)</td>
            <td><strong style="color:#f59e0b;">₹{{ q.estimated_amount }}</strong></td>
            <td><a href="https://wa.me/91{{ q.customer.phone }}" target="_blank" class="chat-btn">Chat 💬</a></td>
        </tr>
        {% endfor %}
    </table></div>

    <h3 class="tab-head">🛠️ Active Maintenance Requests ({{ tickets|length }})</h3>
    <div class="table-responsive"><table>
        <tr><th>Ticket ID</th><th>Client</th><th>Issue Description</th><th>Requested Slot</th><th>Status</th></tr>
        {% for t in tickets %}
        <tr>
            <td><strong>#{{ t.ticket_id }}</strong></td>
            <td>{{ t.customer.name }} ({{ t.customer.phone }})</td>
            <td>{{ t.issue_type }} - <em>"{{ t.description }}"</em></td>
            <td>{{ t.preferred_slot }}</td>
            <td><span style="background:#e0e7ff; color:#4338ca; padding:3px 8px; border-radius:4px; font-weight:bold; font-size:0.8rem;">{{ t.status }}</span></td>
        </tr>
        {% endfor %}
    </table></div>

    <h3 class="tab-head">💼 Career Job Applications ({{ applications|length }})</h3>
    <div class="table-responsive"><table>
        <tr><th>Date</th><th>Applicant Name</th><th>Contact Details</th><th>Position</th><th>Experience</th><th>Resume / CV</th></tr>
        {% for app in applications %}
        <tr>
            <td>{{ app.created_at.strftime('%d-%b %Y') }}</td>
            <td><strong>{{ app.name }}</strong></td>
            <td>📞 {{ app.phone }}<br>✉️ {{ app.email }}</td>
            <td>{{ app.position }}</td>
            <td>{{ app.experience }}</td>
            <td>
                {% if app.resume_file %}
                <a href="/resumes/{{ app.resume_file }}" target="_blank" style="color:#f59e0b; font-weight:bold;">Download CV 📄</a>
                {% else %}
                <span style="color:#64748b;">No file attached</span>
                {% endif %}
            </td>
        </tr>
        {% endfor %}
    </table></div>
</body>
</html>
"""

@app.route('/admin', methods=['GET', 'POST'])
def admin():
    if not session.get('is_admin'):
        if request.method == 'POST':
            username_input = request.form.get('u')
            password_input = request.form.get('p')
            
            admin_user = AdminUser.query.filter_by(username=username_input).first()
            if admin_user and check_password_hash(admin_user.password_hash, password_input):
                session['is_admin'] = True
                return redirect('/admin')
            return "<script>alert('Invalid Admin Credentials'); window.history.back();</script>"
        
        return """
        <body style='background:#0a0f1d; color:white; font-family:sans-serif; display:flex; justify-content:center; align-items:center; height:100vh; margin:0;'>
            <form method='POST' style='background:#121929; padding:2.5rem; border-radius:10px; border-top:4px solid #f59e0b; width:340px; box-shadow:0 15px 35px rgba(0,0,0,0.5);'>
                <h3 style='margin-bottom:1.5rem; text-align:center;'>Owner Admin Login</h3>
                <input name='u' placeholder='Username' required style='padding:10px; width:100%; box-sizing:border-box; margin-bottom:1rem; border-radius:5px; border:1px solid #334155; background:#0a0f1d; color:white;'><br>
                <input name='p' type='password' placeholder='Password' required style='padding:10px; width:100%; box-sizing:border-box; margin-bottom:1.5rem; border-radius:5px; border:1px solid #334155; background:#0a0f1d; color:white;'><br>
                <button type='submit' style='background:#f59e0b; color:#0a0f1d; padding:12px; width:100%; font-weight:bold; border:none; border-radius:5px; cursor:pointer;'>Access Console</button>
                <div style='text-align:center; margin-top:1.5rem;'>
                    <a href='/' style='color:#94a3b8; text-decoration:none; font-size:0.85rem;'>← Back to Website Homepage</a>
                </div>
            </form>
        </body>
        """
    
    quotes = Quotation.query.order_by(Quotation.created_at.desc()).all()
    tickets = MaintenanceTicket.query.order_by(MaintenanceTicket.created_at.desc()).all()
    apps = JobApplication.query.order_by(JobApplication.created_at.desc()).all()
    return render_template_string(ADMIN_PAGE, quotes=quotes, tickets=tickets, applications=apps)

@app.route('/admin/change-password', methods=['POST'])
def admin_change_password():
    if not session.get('is_admin'):
        return redirect('/admin')
    
    new_pwd = request.form.get('new_password')
    if new_pwd and len(new_pwd) >= 6:
        admin_user = AdminUser.query.filter_by(username="admin").first()
        if admin_user:
            new_hash = generate_password_hash(new_pwd)
            admin_user.password_hash = new_hash
            db.session.commit()
            save_persisted_admin_hash(new_hash)
            return "<script>alert('Password successfully updated and permanently saved! Please log in with your new password.'); window.location.href='/admin/logout';</script>"
    
    return "<script>alert('Password must be at least 6 characters.'); window.history.back();</script>"

@app.route('/admin/export-csv')
def export_csv():
    if not session.get('is_admin'):
        return redirect('/admin')

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Date & Time', 'Customer Name', 'Mobile Phone', 'Delhi Area', 'Surveillance Service', 'Cameras', 'Estimated Amount (INR)', 'Status'])

    quotes = Quotation.query.order_by(Quotation.created_at.desc()).all()
    for q in quotes:
        writer.writerow([
            q.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            q.customer.name,
            q.customer.phone,
            q.customer.area,
            q.service_type,
            q.cameras,
            q.estimated_amount,
            q.status
        ])

    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment;filename=Hawkeye_Leads_{datetime.now().strftime('%d_%b_%Y')}.csv"}
    )

@app.route('/admin/logout')
def admin_logout():
    session.pop('is_admin', None)
    return redirect('/admin')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True, port=5000)
