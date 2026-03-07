# Digital Health Record & Prescription System for Migrant Workers

QR-Based Health Identity and **Digital Prescription System**: doctor login, scan patient QR (mobile/laptop camera), view full profile, write prescriptions (diagnosis, medicines, dosage, advice), auto-generate PDF, attach to patient record. Patient can download prescription and use it anywhere.

## Technology Stack

- **Backend:** Python Flask  
- **Frontend:** HTML5, CSS3, Bootstrap 5  
- **Database:** SQLite  
- **QR Code:** Python `qrcode` library  
- **ORM:** Flask-SQLAlchemy  
- **Authentication:** Flask-Login  
- **Security:** Werkzeug password hashing, session management  

## Project Structure

```
digital healthcare/
├── app.py              # Flask app, routes, QR generation
├── models.py           # User, Worker, Vaccination (Flask-SQLAlchemy)
├── requirements.txt
├── database.db         # SQLite (created on first run)
├── static/
│   ├── css/
│   │   └── main.css    # Premium theme
│   └── qr_codes/       # Generated QR images
├── templates/
│   ├── base.html
│   ├── login.html
│   ├── dashboard.html
│   ├── register.html
│   ├── profile.html
│   ├── add_vaccine.html
│   ├── edit_worker.html
│   └── edit_vaccine.html
└── README.md
```

## Setup

### 1. Create virtual environment (recommended)

```bash
python -m venv venv
venv\Scripts\activate
```

### 2. Install dependencies

```bash
pip install flask flask_sqlalchemy flask_login werkzeug qrcode pillow python-dotenv
```

Or from file:

```bash
pip install -r requirements.txt
```

### 3. Run the application

```bash
python app.py
```

- Open **http://localhost:5000** → choose **Admin Login** or **Doctor Login**
- **Admin:** username `admin`, password `admin123` — full access, register workers, manage all
- **Doctor:** username `doctor`, password `doctor123` — log in once; **session stays active 8 hours**; scan patient QR for instant profile

### 4. Use from same WiFi (local)

1. Keep the app running on your PC.
2. On the **dashboard** you’ll see a shareable URL (e.g. `http://192.168.1.x:5000`). Use it on any device on the **same WiFi**.
3. **QR codes** use this URL so scanning a patient’s QR opens the profile on that device.

### 5. QR not opening on mobile from another network?

If you open the app with **localhost** or **192.168.x.x**, QR codes contain that address. Your phone on **mobile data** or **another WiFi** cannot reach it — so the page won’t load.

**Fix: use ngrok (free, 2 minutes)**  
1. Start the app: `python app.py` (keep it running).  
2. Open a **new terminal**, run: `ngrok http 5000` (see **Windows install** below).  
3. ngrok will show a line like: `Forwarding  https://abc123.ngrok-free.app -> http://localhost:5000`  
4. **In your browser, open that https URL** (e.g. `https://abc123.ngrok-free.app`) — do **not** use localhost or 192.168.x.x.  
5. Log in and use the app from that ngrok URL.  
6. From now on, **QR codes will use the ngrok URL**. When someone scans the QR from **any network** (mobile data, different WiFi), the profile will open.

**Important:** You must **use the app by opening the ngrok URL** in the browser. If you keep using localhost, QR codes will still point to localhost and won’t work from another network.

#### ngrok on Windows (exact commands)

**Install (choose one):**

- **Option A – winget (Windows 10/11):**  
  Open **PowerShell** or **Command Prompt** and run:
  ```cmd
  winget install ngrok.ngrok
  ```
  Close and reopen the terminal after install.

- **Option B – Manual download:**  
  1. Go to [https://ngrok.com/download](https://ngrok.com/download).  
  2. Download **Windows (64-bit)**.  
  3. Unzip `ngrok-v3-amd64.zip` to a folder (e.g. `C:\ngrok`).  
  4. Open **Command Prompt** or **PowerShell**, go to that folder:
     ```cmd
     cd C:\ngrok
     ```

**One-time signup (free):**  
1. Sign up at [https://dashboard.ngrok.com/signup](https://dashboard.ngrok.com/signup).  
2. In the dashboard, copy your **Authtoken**.  
3. In the same terminal where `ngrok` works, run (replace with your token):
   ```cmd
   ngrok config add-authtoken YOUR_AUTHTOKEN_HERE
   ```

**Run the app and ngrok:**

1. **Terminal 1** – start the app:
   ```cmd
   cd "C:\Users\ramla\OneDrive\Desktop\digital healthcare"
   python app.py
   ```
   Leave this window open.

2. **Terminal 2** – start ngrok:
   ```cmd
   ngrok http 5000
   ```
   Copy the **https** URL (e.g. `https://xxxx.ngrok-free.app`) and open it in your browser. Use the app only from that URL so QR codes work from any network.

**Option B: Deploy online (24/7)**  
Deploy to [Render](https://render.com) or [Railway](https://railway.app). Set **PUBLIC_URL** to your app URL. Then the site and all QR codes work from anywhere.

## Database Design

| Table       | Key fields |
|------------|------------|
| **User**   | id, username, password (hashed) – Admin/Health worker login |
| **Worker** | id, name, age, gender, phone, address, blood_group, allergies, diseases, qr_code_path, created_at, updated_at |
| **Vaccination** | id, worker_id (FK), vaccine_name, date |
| **Document** | id, worker_id (FK), document_type (report/prescription/lab_result), original_filename, stored_path, notes, uploaded_at |
| **Prescription** | id, worker_id (FK), diagnosis, advice, prescribed_at, prescribed_by_id, pdf_path |
| **PrescriptionMedicine** | id, prescription_id (FK), medicine_name, dosage, frequency, duration |

## Routes

| Route | Description |
|-------|-------------|
| `/` | Landing: choose Admin or Doctor login |
| `/admin/login` | Admin login (admin role only) |
| `/doctor/login` | Doctor login (doctor role only; 8-hour session) |
| `/logout` | Logout (login required) |
| `/dashboard` | Dashboard: stats, same-WiFi URL, search, worker list, Edit/Delete (login required) |
| `/register` | Register new worker + generate QR (login required) |
| `/profile/<id>` | Worker profile + vaccinations + QR; public when opened via scan |
| `/edit_worker/<id>` | Edit worker details; regenerates QR (login required) |
| `/delete_worker/<id>` | Remove worker and all vaccinations (POST, login required) |
| `/add_vaccine/<id>` | Add vaccination for worker (login required) |
| `/edit_vaccine/<worker_id>/<vac_id>` | Edit a vaccination record (login required) |
| `/delete_vaccine/<worker_id>/<vac_id>` | Remove a vaccination (POST, login required) |
| `/upload_document/<worker_id>` | Upload report or prescription (POST, login required; PDF, images, max 10MB) |
| `/download_document/<worker_id>/<doc_id>` | Download file with original name |
| `/delete_document/<worker_id>/<doc_id>` | Remove uploaded document (POST, login required) |
| `/prescribe/<worker_id>` | Write digital prescription: diagnosis, medicines, dosage, advice (GET/POST, login required) |
| `/download_prescription/<worker_id>/<prescription_id>` | Download prescription PDF |

## User Flow

### Doctor workflow (separate login, 8-hour session)
1. **Doctor logs in** at **Doctor Login** (once in the morning).
2. **Session stays active for 8 hours** — no need to log in again for each patient.
3. **Scan patient QR** (mobile/laptop camera or QR scanner) → **Patient Profile** opens instantly. Or search/open from Doctor Dashboard.
3. Profile shows: **Patient name**, **Age**, **Blood group**, **Previous illness**, **Uploaded reports (PDF)**, **Lab results**, **Previous prescriptions**, **Digital prescriptions**.
4. Doctor clicks **Write Prescription** → fills **Diagnosis**, **Medicines** (name, dosage, frequency, duration), **Advice** → **Submit**.
5. System saves the prescription, **generates PDF**, attaches to patient record; patient can **download prescription** and use it anywhere.

### Patient & general
6. Patient (or anyone with profile link) can download prescription PDF from the profile.
7. Register workers, edit/delete, upload reports/lab results; profile is **print-friendly**.

## Security

- Passwords hashed with Werkzeug.
- `@login_required` on dashboard, register, add_vaccine, logout.
- Session-based auth via Flask-Login.
- Form validation for registration and vaccination.

## Testing Checklist

- [ ] Registration: New worker saves and redirects to profile.
- [ ] Login: Correct admin credentials allow access; wrong ones show error.
- [ ] QR code: Generated after registration and visible on profile.
- [ ] QR redirect: Scanning QR opens correct `/profile/<id>`.
- [ ] Data in DB: Workers and vaccinations visible in dashboard and profile.
- [ ] Add vaccination: Saves and appears in worker profile.
- [ ] No duplicate errors: Register multiple workers; add multiple vaccines.
- [ ] Dashboard: Loads with total count, search, and worker list.
- [ ] Logout: Session cleared and redirect to login.
- [ ] Same WiFi: Dashboard shows URL; QR scan on phone opens profile.
- [ ] Edit worker: Changes save; QR regenerates.
- [ ] Delete worker: Confirmation; worker and vaccinations removed.
- [ ] Edit/Delete vaccination: Updates and removals reflect on profile.
- [ ] Print profile: Print view hides nav and buttons.

## Optional: Deployment

For production, use a proper secret key and WSGI server:

```bash
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:5000 app:app
```

Set `SECRET_KEY` (and optionally `SQLALCHEMY_DATABASE_URI`) via environment variables.
