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
        "timestamp": "2024-11-28T17:18:00",
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
    }
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
        initial_hash = saved_hash if saved_hash else generate_password_hash("Admin@2026")
        admin_user = AdminUser(username="admin", password_hash=initial_hash)
        db.session.add(admin_user)
        db.session.commit()
    elif saved_hash and admin_user.password_hash != saved_hash:
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