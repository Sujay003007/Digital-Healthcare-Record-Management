# Deploy to the Web (Render, Railway, etc.)

This guide helps you host your Digital Health Record app so **everyone can access it** and **QR codes work when scanned** from any phone.

---

## 1. Set PUBLIC_URL (Required for QR codes)

When deployed, set this environment variable to your live site URL:

```
PUBLIC_URL=https://your-app-name.onrender.com
```

- **Why:** QR codes encode this URL. Without it, QR codes may use localhost or wrong host and won’t work when scanned.
- **Where:** Your hosting dashboard → Your service → Environment → Add Variable.

---

## 2. Deploy on Render (Free)

1. Push your project to **GitHub** (create a repo and push).
2. Go to [render.com](https://render.com) → Sign up/Log in.
3. **New +** → **Web Service**.
4. Connect your GitHub repo.
5. Use these settings:

| Field | Value |
|-------|-------|
| Name | `digital-health-record` (or any name) |
| Region | Choose nearest to you |
| Branch | `main` |
| Runtime | Python 3 |
| Build Command | `pip install -r requirements.txt` |
| Start Command | `gunicorn --bind 0.0.0.0:$PORT app:app` |

6. **Environment** → Add:
   - `SECRET_KEY` = any random string (e.g. `your-secret-key-here`)
   - `PUBLIC_URL` = `https://your-app-name.onrender.com` (use the URL Render gives you after first deploy)

7. **Create Web Service**. Wait for the build to finish.

8. After deploy, update `PUBLIC_URL` to match your exact URL (e.g. `https://digital-health-record-xyz.onrender.com`) and redeploy if needed.

---

## 3. Deploy on Railway

1. Go to [railway.app](https://railway.app) → Connect GitHub.
2. **New Project** → **Deploy from GitHub repo** → Select your repo.
3. Railway auto-detects Python. If not, set:
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `gunicorn --bind 0.0.0.0:$PORT app:app`
4. **Settings** → **Variables** → Add:
   - `SECRET_KEY` = random string
   - `PUBLIC_URL` = `https://your-app.up.railway.app` (your Railway URL)
5. **Deploy**. QR codes will use `PUBLIC_URL` and work from any network.

---

## 4. After Deployment

- **QR codes:** Scanned QR codes will open the patient profile from any phone, anywhere.
- **Patient login:** Patients go to `https://your-url/patient/login`.
- **Admin/Doctor:** Use `https://your-url/admin/login` and `https://your-url/doctor/login`.

---

## Notes

- **Free tier:** Render free tier sleeps after ~15 min of no traffic. First load may be slow.
- **Database:** SQLite is used. On free tiers, the database may reset on restart. For production, consider PostgreSQL (Render/Railway support it).
