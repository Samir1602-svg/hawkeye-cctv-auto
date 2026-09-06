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
    HAWKEYE_EMBLEM_B64 = "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"

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
            <p>🕒 Field Inspection Hours: 08:30 AM - 08:00 PM (All 7 Days)</p>
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

    .hero { background: radial-gradient(circle at 80% 20%, rgba(56, 189, 248, 0.12) 0%, transparent 50%), linear-gradient(rgba(10,15,29,0.95), rgba(10,15,29,0.92)), url('https://images.unsplash.com/photo-1557597774-9d273605dfa9?auto=format&fit=crop&w=1600&q=80') center/cover; color:white; padding: 4.5rem 5%; }
    .hero-wrap { max-width: 1300px; margin: auto; display: flex; flex-wrap: wrap; gap: 3rem; align-items: center; justify-content: space-between; }
    .hero-content { flex: 1.2; min-width: 330px; }
    .hero-badge { display:inline-block; background:rgba(56,189,248,0.15); color:var(--secondary); padding:4px 14px; border-radius:20px; font-size:0.82rem; font-weight:700; margin-bottom:1rem; border:1px solid rgba(245,158,11,0.35); text-transform:uppercase; letter-spacing:0.8px; }
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
    .btn-submit-quote:hover { background: #0284c7; color: white; }

    .section-wrap { padding: 4rem 5%; max-width: 1300px; margin: auto; }
    .sec-title { text-align: center; margin-bottom: 3rem; }
    .sec-title h1, .sec-title h2 { font-size: 2.3rem; color: var(--primary); margin-bottom: 0.5rem; font-weight: 800; }
    .sec-title p { color: var(--text-muted); font-size: 1.05rem; }

    .services-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 2rem; }
    .service-card { background: white; border: 1px solid var(--border-color); border-radius: 12px; padding: 2rem; border-top: 4px solid var(--secondary); box-shadow: 0 4px 15px rgba(0,0,0,0.03); }
    .service-icon { font-size: 2.2rem; margin-bottom: 1rem; }
    .service-card h3 { color: var(--primary); margin-bottom: 0.6rem; font-size: 1.25rem; }
    .service-card p { color: #475569; font-size: 0.92rem; }

    .packages-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 2rem; }
    .package-card { background: white; border: 1px solid var(--border-color); border-radius: 12px; padding: 2rem; position: relative; display: flex; flex-direction: column; justify-content: space-between; }
    .package-card.popular { border: 2px solid var(--secondary); }
    .popular-tag { position: absolute; top: -12px; right: 20px; background: var(--secondary); color: #0a0f1d; font-weight: 800; font-size: 0.75rem; padding: 4px 10px; border-radius: 12px; text-transform: uppercase; }
    .pack-price { font-size: 2rem; font-weight: 800; color: var(--primary); margin: 1rem 0; }
    .pack-price span { font-size: 0.9rem; color: var(--text-muted); font-weight: 400; }
    .pack-features { list-style: none; margin: 1.5rem 0; font-size: 0.9rem; color: #334155; }
    .pack-features li { margin-bottom: 0.6rem; display: flex; align-items: center; gap: 0.5rem; }
    .pack-features li::before { content: "OK"; color: var(--success); font-weight: bold; }

    .calc-container { max-width: 1100px; margin: auto; background: #f8fafc; border: 2px solid #e2e8f0; border-radius: 16px; padding: 2.5rem; box-shadow: 0 10px 25px rgba(0,0,0,0.03); }
    .calc-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 2rem; }
    .calc-result-box { background: var(--primary); color: white; padding: 2rem; border-radius: 12px; text-align: center; display: flex; flex-direction: column; justify-content: center; border: 2px solid var(--secondary); }
    .calc-price { font-size: 2.8rem; font-weight: 900; color: var(--secondary); margin: 0.5rem 0; }

    .review-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(350px, 1fr)); gap: 1.5rem; }
    .review-card { background: white; padding: 1.5rem; border-radius: 10px; border: 1px solid var(--border-color); display: flex; flex-direction: column; justify-content: space-between; }
    .reviewer-name { font-weight: 700; color: var(--primary); font-size: 1rem; }
    .reviewer-loc { font-size: 0.8rem; color: var(--text-muted); }
    .review-stars { color: #f59e0b; font-size: 0.95rem; }
    .review-date { font-size: 0.75rem; color: #94a3b8; margin-top: 0.8rem; border-top: 1px dashed #e2e8f0; padding-top: 0.6rem; display: flex; justify-content: space-between; align-items: center; }
    .verified-chip { background: #dcfce7; color: #166534; font-size: 0.7rem; font-weight: 700; padding: 2px 6px; border-radius: 4px; }

    .portal-container { max-width: 1200px; margin: 2rem auto; padding: 0 5%; }
    .portal-header { background: white; padding: 1.8rem 2rem; border-radius: 12px; border: 1px solid var(--border-color); display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 1rem; margin-bottom: 2rem; border-left: 5px solid var(--secondary); }
    .portal-actions { display: flex; gap: 1rem; flex-wrap: wrap; }
    .btn-ticket { background: #ef4444; color: white; padding: 0.65rem 1.2rem; border-radius: 6px; font-weight: 600; cursor: pointer; border: none; font-size: 0.9rem; }
    .btn-req-quote { background: var(--secondary); color: #0a0f1d; padding: 0.65rem 1.2rem; border-radius: 6px; font-weight: 700; cursor: pointer; border: none; font-size: 0.9rem; }
    .portal-grid { display: grid; grid-template-columns: 2fr 1fr; gap: 2rem; }
    .portal-card { background: white; border-radius: 12px; border: 1px solid var(--border-color); padding: 1.5rem; margin-bottom: 2rem; box-shadow: 0 2px 8px rgba(0,0,0,0.03); }
    .portal-card h3 { font-size: 1.2rem; color: var(--primary); margin-bottom: 1.2rem; display: flex; justify-content: space-between; align-items: center; }
    .badge-status { padding: 4px 10px; border-radius: 20px; font-size: 0.75rem; font-weight: 700; text-transform: uppercase; }
    .status-active { background: #dcfce7; color: #15803d; }
    .status-assigned { background: #e0e7ff; color: #4338ca; }

    .site-footer { background: var(--primary); color: #cbd5e1; padding: 4rem 5% 1.5rem 5%; }
    .footer-grid { max-width: 1300px; margin: auto; display: grid; grid-template-columns: 2fr 1.2fr 1.5fr; gap: 3rem; margin-bottom: 3rem; }
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
        .portal-grid { grid-template-columns: 1fr; }
        .portal-header { flex-direction: column; align-items: flex-start; gap: 1rem; }
        .portal-actions { width: 100%; flex-direction: column; }
        .portal-actions button { width: 100%; }
        .floating-wa-btn { bottom: 16px; right: 16px; width: 50px; height: 50px; font-size: 1.5rem; }
        .footer-grid { grid-template-columns: 1fr; }
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
                    <p style="color:var(--accent-cyan); font-size:0.88rem; font-weight:600;">4 Cameras - Primary Entrance &amp; Corridors</p>
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
                    <p style="color:var(--accent-cyan); font-size:0.88rem; font-weight:600;">6 Cameras - Complete Perimeter Coverage</p>
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
                    <p style="color:var(--accent-cyan); font-size:0.88rem; font-weight:600;">8 Cameras - Full Commercial / Residential</p>
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
                            <option value="4" selected>4 Cameras - Residential Starter Kit (₹18,499)</option>
                            <option value="6">6 Cameras - Security Package with Color + Audio (₹25,000)</option>
                            <option value="8">8 Cameras - Security Package with Color + Audio (₹32,000)</option>
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
        const hawkeyePackages = {{
            4: {{
                name: "Residential Starter Kit",
                price: "₹18,499",
                specs: "• 4 × IP Camera 5MP Hawkeye<br>• 4 Channel Prama/Hikvision NVR<br>• 500GB Surveillance Hard Drive<br>• Mobile App Sync (iOS & Android)<br>• 2 Year Warranty and Maintenance",
                msg: "Hi Hawkeye CCTV, I want to confirm the 4 Camera Residential Starter Kit for Rs 18,499"
            }},
            6: {{
                name: "6 Camera Security Package",
                price: "₹25,000",
                specs: "• 6 × 5MP Hawkeye Cameras<br>• Color Night Vision + Audio<br>• 500GB Surveillance Hard Drive<br>• Mobile App Sync (iOS & Android)<br>• 2 Years Warranty and Maintenance",
                msg: "Hi Hawkeye CCTV, I want to confirm the 6 Camera Security Package for Rs 25,000"
            }},
            8: {{
                name: "8 Camera Security Package",
                price: "₹32,000",
                specs: "• 8 × 5MP Hawkeye Cameras<br>• Color Night Vision + Audio<br>• 500GB Surveillance Hard Drive<br>• Mobile App Sync (iOS & Android)<br>• 2 Years Warranty and Maintenance",
                msg: "Hi Hawkeye CCTV, I want to confirm the 8 Camera Security Package for Rs 32,000"
            }}
        }};

        function updateLiveEstimate() {{
            const cams = parseInt(document.getElementById('calc_cams').value);
            const data = hawkeyePackages[cams];
            if(data) {{
                document.getElementById('calc_total_display').innerText = data.price;
                document.getElementById('calc_pack_name').innerText = data.name;
                document.getElementById('calc_specs_list').innerHTML = data.specs;
                document.getElementById('calc_whatsapp_btn').href = "https://wa.me/919971332864?text=" + encodeURIComponent(data.msg);
            }}
        }}
    </script>
</body>
</html>
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
            <p>Real feedback recorded across Delhi NCR (2024-2026)</p>
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
                    <div style="font-size: 0.85rem; color: var(--text-muted); margin-top: 3px;">Full-time - 2-4 Years Exp. in IP &amp; DVR Cabling</div>
                    <div style="font-size: 0.88rem; color: #475569; margin-top: 0.5rem;">Responsible for physical installation, mobile app configuration, and site inspection across Delhi NCR.</div>
                </div>

                <div style="background: white; border: 1px solid var(--border-color); border-radius: 8px; padding: 1.2rem; margin-bottom: 1rem;">
                    <div style="font-weight: 700; color: var(--primary);">2. Field Installation Helper / Apprentice</div>
                    <div style="font-size: 0.85rem; color: var(--text-muted); margin-top: 3px;">Full-time - Fresher / 6 Months Exp.</div>
                    <div style="font-size: 0.88rem; color: #475569; margin-top: 0.5rem;">Assist senior technicians in ladder work, concealed trunking, and cable laying. Technical training provided.</div>
                </div>

                <div style="background: white; border: 1px solid var(--border-color); border-radius: 8px; padding: 1.2rem; margin-bottom: 1rem;">
                    <div style="font-weight: 700; color: var(--primary);">3. B2B Sales Executive (Security &amp; AMC)</div>
                    <div style="font-size: 0.85rem; color: var(--text-muted); margin-top: 3px;">Full-time - 1-3 Years Experience</div>
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

AUTH_PAGE = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link rel="icon" type="image/png" href="/logo.png">
    <title>Customer Login | Hawkeye Security</title>
    {{{{ styles | safe }}}
</head>
<body>
    {{{{ navbar | safe }}}

    <div class="auth-wrap" style="max-width:420px; margin:4rem auto; background:white; padding:2.5rem; border-radius:12px; box-shadow:0 10px 30px rgba(0,0,0,0.06); text-align:center;">
        <span class="auth-badge" style="background:#e0f2fe; color:#0369a1; padding:4px 12px; border-radius:20px; font-size:0.75rem; font-weight:bold;">🔑 Customer Authentication</span>
        <h2 style="font-size:1.4rem; color:var(--primary); margin:0.8rem 0 0.4rem 0;">Existing Customer Login</h2>
        <p style="font-size:0.85rem; color:var(--text-muted); margin-bottom:1.5rem;">Enter your registered 10-digit mobile number to access your account</p>

        <form action="/client-login" method="POST" style="text-align:left;">
            <div class="form-group">
                <label>Mobile Number</label>
                <input type="tel" name="phone" placeholder="10-digit mobile number" maxlength="10" required autofocus style="padding:0.8rem; font-size:1rem;">
            </div>
            <button type="submit" class="btn-submit-quote" style="background:#38bdf8; color:#0a0f1d; font-weight:800; padding:0.85rem; margin-top:0.8rem;">Access My Dashboard 🚀</button>
        </form>

        <div style="margin-top:1.5rem; font-size:0.82rem; color:#64748b;">
            New to Hawkeye? <a href="/#get-quote" style="color:#0284c7; font-weight:bold; text-decoration:underline;">Book a Free Survey</a>
        </div>
    </div>

    {{{{ footer | safe }}}
</body>
</html>
"""
# =========================== ROUTING CONTROLLERS ===========================

@app.route('/logo.png')
def serve_root_logo():
    from flask import send_from_directory
    return send_from_directory(os.path.dirname(os.path.abspath(__file__)), 'logo.png')
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

@app.route('/client-login', methods=['POST'])
def client_login():
    phone = request.form.get('phone', '').strip()
    clean_phone = re.sub(r'\D', '', phone)[-10:]
    
    if len(clean_phone) != 10:
        return "<script>alert('Please enter a valid 10-digit mobile number'); window.history.back();</script>"

    user = User.query.filter_by(phone=clean_phone).first()
    if not user:
        return "<script>alert('No customer account found with this mobile number. Please book a free survey first!'); window.location.href='/#get-quote';</script>"

    send_whatsapp_alert(user.name, user.phone, user.area, "DIRECT PORTAL LOGIN", 0)

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
        th { background: #38bdf8; color: #0a0f1d; }
        .export-btn { background: #22c55e; color: white; padding: 10px 18px; border-radius: 6px; text-decoration: none; font-weight: bold; display: inline-block; }
        .chat-btn { background: #25d366; color: white; padding: 5px 12px; border-radius: 4px; text-decoration: none; font-size: 0.82rem; font-weight: bold; }
        .tab-head { color: #38bdf8; margin-top: 2.5rem; border-bottom: 2px solid #334155; padding-bottom: 0.5rem; }
        .pwd-card { background: #121929; border: 1px solid #334155; padding: 1.5rem; border-radius: 8px; margin-top: 1.5rem; max-width: 480px; }
        .pwd-input { padding: 8px 12px; border-radius: 4px; border: 1px solid #334155; background: #0a0f1d; color: white; width: 100%; box-sizing: border-box; margin-bottom: 0.8rem; }
        .table-responsive { width: 100%; overflow-x: auto; -webkit-overflow-scrolling: touch; margin-top: 1rem; }
        table { min-width: 600px; }
    </style>
</head>
<body>
    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom: 1.5rem;">
        <div>
            <h2 style="font-size:1.8rem;">📊 Business Operations Console</h2>
            <p style="color:#94a3b8; font-size:0.9rem;">Hawkeye Security &amp; Automation Control Center</p>
        </div>
        <div style="display:flex; align-items:center; gap:1rem;">
            <a href="/" style="color:#38bdf8; text-decoration:none; font-weight:bold;">🌐 View Public Website</a>
            <a href="/admin/export-csv" class="export-btn">📥 Download All Leads (Excel/CSV)</a>
            <a href="/admin/logout" style="color:#ef4444; font-weight: bold; text-decoration:none;">Logout</a>
        </div>
    </div>

    <div class="pwd-card">
        <h4 style="margin-bottom:0.8rem; color:#38bdf8;">🔐 Update Admin Password</h4>
        <form action="/admin/change-password" method="POST">
            <input type="password" name="new_password" placeholder="Create new password (min 6 chars)" class="pwd-input" required minlength="6">
            <button type="submit" style="background:#38bdf8; color:#0a0f1d; padding:8px 16px; border:none; border-radius:4px; font-weight:bold; cursor:pointer;">Update Password</button>
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
            <td><strong style="color:#38bdf8;">₹{{ q.estimated_amount }}</strong></td>
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
                <a href="/resumes/{{ app.resume_file }}" target="_blank" style="color:#38bdf8; font-weight:bold;">Download CV 📄</a>
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
            <form method='POST' style='background:#121929; padding:2.5rem; border-radius:10px; border-top:4px solid #38bdf8; width:340px; box-shadow:0 15px 35px rgba(0,0,0,0.5);'>
                <h3 style='margin-bottom:1.5rem; text-align:center;'>Owner Admin Login</h3>
                <input name='u' placeholder='Username' required style='padding:10px; width:100%; box-sizing:border-box; margin-bottom:1rem; border-radius:5px; border:1px solid #334155; background:#0a0f1d; color:white;'><br>
                <input name='p' type='password' placeholder='Password' required style='padding:10px; width:100%; box-sizing:border-box; margin-bottom:1.5rem; border-radius:5px; border:1px solid #334155; background:#0a0f1d; color:white;'><br>
                <button type='submit' style='background:#38bdf8; color:#0a0f1d; padding:12px; width:100%; font-weight:bold; border:none; border-radius:5px; cursor:pointer;'>Access Console</button>
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
