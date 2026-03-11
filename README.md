# 📱 YouTube Shorts Automation System

A fully automated, cloud-only pipeline that generates and uploads **YouTube Shorts** using AI — runs entirely on **GitHub Actions**, zero local execution required after setup.

---

## 🔄 How It Works

```
GitHub Actions Cron (3×/day)
        │
        ▼
  1. Generate Topic      ← Curated pool, seeded by UTC hour
  2. Generate Script     ← OpenRouter LLM (Llama 3 8B, free tier)
  3. Generate Voiceover  ← gTTS (no API key needed)
  4. Download Video      ← Pexels vertical stock video (free tier)
  5. Edit Video          ← Crop to 1080×1920, merge audio, title overlay
  6. Generate Metadata   ← OpenRouter LLM → title + description + tags
  7. Upload to YouTube   ← YouTube Data API v3 (OAuth 2.0)
```

---

## 📁 Project Structure

```
├── .github/
│   └── workflows/
│       └── shorts_automation.yml   # GitHub Actions pipeline
├── modules/
│   ├── __init__.py
│   ├── topic_generator.py          # Random topic selection from pool
│   ├── script_generator.py         # LLM script via OpenRouter
│   ├── voice_generator.py          # gTTS text-to-speech
│   ├── video_downloader.py         # Pexels vertical video downloader
│   ├── video_editor.py             # MoviePy + FFmpeg video assembly
│   ├── metadata_generator.py       # LLM title/description/tags
│   └── youtube_uploader.py         # YouTube Data API upload
├── output/                         # Runtime only, gitignored
├── config.py                       # Centralized config + constants
├── main.py                         # Pipeline orchestrator
├── requirements.txt
├── .env.example
└── .gitignore
```

---

## 🚀 Setup Guide

### Step 1 — Fork & Clone

```bash
git clone https://github.com/YOUR_USERNAME/youtube-shorts-automation.git
cd youtube-shorts-automation
```

### Step 2 — Get API Keys

| Service | URL | Free Tier |
|---|---|---|
| **OpenRouter** | https://openrouter.ai/ | ~$1 credit free, models like Llama 3 8B are free |
| **Pexels** | https://www.pexels.com/api/ | 200 req/hour, 20k/month |
| **YouTube API** | Google Cloud Console (see below) | Free (quota limits apply) |

---

### Step 3 — YouTube OAuth Setup (one-time, local)

This is the only step requiring local action. YouTube requires OAuth to upload videos to your channel.

#### 3a. Create OAuth Credentials

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project (or select existing)
3. Enable **YouTube Data API v3**:
   - APIs & Services → Library → search "YouTube Data API v3" → Enable
4. Create OAuth 2.0 credentials:
   - APIs & Services → Credentials → Create Credentials → **OAuth client ID**
   - Application type: **Desktop app**
   - Name: `YouTube Shorts Bot`
   - Download the JSON — note your `client_id` and `client_secret`
5. Add your Google account as a test user:
   - APIs & Services → OAuth consent screen → Test users → Add your Gmail

#### 3b. Generate Refresh Token (run once locally)

```bash
pip install google-auth-oauthlib requests
```

Save this as `get_token.py` and run it locally:

```python
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

flow = InstalledAppFlow.from_client_secrets_file(
    "client_secret.json",   # downloaded from Cloud Console
    scopes=SCOPES,
)
credentials = flow.run_local_server(port=0)

print("CLIENT_ID:", credentials.client_id)
print("CLIENT_SECRET:", credentials.client_secret)
print("REFRESH_TOKEN:", credentials.refresh_token)
```

```bash
python get_token.py
```

This opens a browser for one-time authorization. Copy the printed `REFRESH_TOKEN`.

---

### Step 4 — Add GitHub Secrets

Go to your repository → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**

Add all 5 secrets:

| Secret Name | Value |
|---|---|
| `OPENROUTER_API_KEY` | From openrouter.ai |
| `PEXELS_API_KEY` | From pexels.com/api |
| `YOUTUBE_CLIENT_ID` | From Google Cloud Console |
| `YOUTUBE_CLIENT_SECRET` | From Google Cloud Console |
| `YOUTUBE_REFRESH_TOKEN` | Generated in Step 3b |

---

### Step 5 — Push & Activate

```bash
git add .
git commit -m "initial setup"
git push origin main
```

The workflow runs automatically at **06:00, 12:00, and 18:00 UTC**.

---

## ▶️ Manual Trigger

1. Go to your repository on GitHub
2. Click **Actions** tab
3. Select **YouTube Shorts Automation**
4. Click **Run workflow** → **Run workflow**

---

## ⚙️ Configuration

Edit `.env` (local) or GitHub Secrets (CI) to customize:

| Variable | Default | Description |
|---|---|---|
| `TTS_LANGUAGE` | `en` | gTTS language code |
| `TTS_SLOW` | `false` | Slower speech speed |
| `YT_PRIVACY` | `public` | `public`, `unlisted`, or `private` |
| `YT_CATEGORY_ID` | `22` | YouTube category (22 = People & Blogs) |

---

## 🕐 Schedule

The workflow runs 3× per day by default:

```yaml
schedule:
  - cron: '0 6 * * *'    # 11:30 AM IST
  - cron: '0 12 * * *'   # 05:30 PM IST
  - cron: '0 18 * * *'   # 11:30 PM IST
```

To change frequency, edit `.github/workflows/shorts_automation.yml`.

---

## 🐛 Debugging

- View step-by-step logs: **Actions** tab → select a workflow run
- Download output videos: each run uploads `output/` as a build artifact (kept 3 days)
- Failed runs: check the ❌ step for error details

---

## 📋 YouTube Shorts Requirements

The system automatically ensures:
- ✅ Vertical format (1080×1920 / 9:16)
- ✅ Under 60 seconds (capped at 59s)
- ✅ `#Shorts` in title/description for YouTube classification
- ✅ H.264 video + AAC audio
- ✅ 30 FPS

---

## ⚠️ Quota Notes

- **OpenRouter**: Free models (Llama 3 8B) have rate limits. System uses 2 calls/run.
- **Pexels**: 200 requests/hour — well within limits at 3 runs/day.
- **YouTube Data API**: Default quota is 10,000 units/day. Each upload costs ~1,600 units, so ~6 uploads/day max before quota exhaustion. 3 runs/day is safe.

---

## 📄 License

MIT — free to use, modify, and distribute.
