# ♿ Accessibility Autopilot

> Voice-controlled AI agent that acts as a universal cursor for users with motor disabilities. Built with Gemini 2.0 Flash, Google ADK, and Cloud Run.

**Category:** UI Navigator ☸️ | **Hackathon:** Google Gemini AI Hackathon

---

## 🎥 Demo Video

[Link to your demo video]

---

## 🧩 What It Does

Accessibility Autopilot watches your screen via screenshots, listens to your voice, and performs browser actions (click, type, scroll) on your behalf — across **any web application** without needing accessibility APIs or DOM access.

**Example flow on Outlook 365:**
```
You say: "Open the email from Alex"
→ Agent sees your inbox screenshot
→ Gemini identifies Alex's email at coordinates (475, 155)
→ Agent clicks it and says: "Opening Alex's email about Project Deadline"

You say: "Reply: Thanks, I'll have it ready by Monday"
→ Agent clicks Reply, types your message
→ Agent says: "I've typed your reply. Should I send it?"

You say: "Yes, send it"
→ Agent clicks Send, confirms: "Email sent."
```

---

## 📁 Project Structure

```
accessibility-autopilot/
├── backend/
│   ├── backend.py              # FastAPI server + Gemini integration
│   ├── test_single_scenario.py # Quick single-scenario Gemini test
│   ├── test_autopilot.py       # Full test suite (25 tests)
│   ├── requirements.txt        # Python dependencies
│   ├── Dockerfile              # Cloud Run container
│   └── .env.example            # Environment variable template
├── chrome-extension/
│   ├── manifest.json           # Chrome Extension config (Manifest V3)
│   ├── background.js           # Service worker — capture, execute, communicate
│   ├── popup.html              # Extension UI — start/stop, mic capture, settings
│   └── icons/                  # Extension icons (16, 48, 128px)
│       ├── icon16.png
│       ├── icon48.png
│       └── icon128.png
└── README.md
```

---

## 🛠️ Tech Stack

| Technology | Role |
|---|---|
| **Gemini 2.0 Flash** (Live API) | Vision understanding, speech processing, action planning |
| **Google GenAI SDK** (Python) | Gemini API client |
| **Google Cloud Run** | Backend hosting (WebSocket support) |
| **Google Firestore** | Session storage & user preferences (optional) |
| **Google Cloud Storage** | Screenshot history buffer (optional) |
| **Chrome Extension** (Manifest V3) | Screen capture, mic input, action execution |
| **FastAPI + Uvicorn** | Python backend server |
| **Pillow** | Screenshot preprocessing & grid overlay |

---

## 🚀 Quick Start — Local Setup

### Prerequisites

- **Python 3.10+** installed
- **Google Chrome** browser
- **Google Cloud account** with a Gemini API key
- **Git** installed

### Step 1: Clone the Repository

```bash
git clone https://github.com/YOUR_USERNAME/accessibility-autopilot.git
cd accessibility-autopilot
```

### Step 2: Get a Gemini API Key

1. Go to [aistudio.google.com/apikey](https://aistudio.google.com/apikey)
2. Click **Create API Key**
3. Select or create a Google Cloud project
4. Copy the key

### Step 3: Set Up the Backend

```bash
cd backend

# Create virtual environment
python3 -m venv venv
source venv/bin/activate        # Mac/Linux
# venv\Scripts\activate          # Windows

# Install dependencies
pip install -r requirements.txt

# Set your API key
cp .env.example .env
# Edit .env and paste your GEMINI_API_KEY

# OR set it directly:
export GEMINI_API_KEY=your_api_key_here
```

### Step 4: Run the Quick Test (Verify Gemini Works)

```bash
python test_single_scenario.py
```

**Expected output:**
```
=================================================================
  ♿ Accessibility Autopilot — Single Scenario Test
=================================================================

  Step 1: Generate fake Outlook inbox screenshot
  ✅ PASS: Screenshot created (142 KB, 1920x1080)

  Step 3: Send screenshot + voice command to Gemini
  ✅ PASS: Gemini responded in 1.84s

  Step 5: Validate action structure
  ✅ PASS: action is 'click'
  ✅ PASS: has 'x' coordinate
  ✅ PASS: has 'y' coordinate
  ✅ PASS: has 'confirmation' message

  Step 6: Validate coordinate accuracy
  ✅ PASS: Coordinate accuracy is GOOD (32px from ideal)
```

This confirms your API key works and Gemini can understand Outlook screenshots.

### Step 5: Start the Backend Server

```bash
uvicorn backend:app --host 0.0.0.0 --port 8080 --reload
```

You should see:
```
INFO:     Uvicorn running on http://0.0.0.0:8080
INFO:     Started reloader process
```

Verify it's running:
```bash
curl http://localhost:8080/health
# → {"status":"ok","service":"accessibility-autopilot","target":"outlook-365"}
```

### Step 6: Load the Chrome Extension

1. Open Chrome and go to `chrome://extensions/`
2. Enable **Developer mode** (toggle in top-right)
3. Click **Load unpacked**
4. Select the `chrome-extension/` folder
5. Pin the extension icon in your Chrome toolbar

### Step 7: Run It

1. Open **[outlook.office.com](https://outlook.office.com)** in a Chrome tab
2. Set browser zoom to **100%** (Ctrl+0 / Cmd+0)
3. Click the **Autopilot extension icon** in the toolbar
4. Set backend URL to: `ws://localhost:8080/ws`
5. Click **🎙️ Start Autopilot**
6. Allow microphone access when prompted
7. Start speaking: **"What's in my inbox?"**

---

## ☁️ Deploy to Google Cloud Run

### Step 1: Set Up Google Cloud

```bash
# Install gcloud CLI if not already installed
# https://cloud.google.com/sdk/docs/install

# Login and set project
gcloud auth login
gcloud config set project YOUR_PROJECT_ID

# Enable required APIs
gcloud services enable run.googleapis.com
gcloud services enable aiplatform.googleapis.com
gcloud services enable cloudbuild.googleapis.com
```

### Step 2: Deploy

```bash
cd backend

gcloud run deploy accessibility-autopilot \
  --source . \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars GEMINI_API_KEY=your_api_key_here \
  --memory 512Mi \
  --timeout 300 \
  --session-affinity
```

### Step 3: Update the Extension

After deployment, you'll see a URL like:
```
Service URL: https://accessibility-autopilot-abc123-uc.a.run.app
```

Open the extension popup and change the backend URL to:
```
wss://accessibility-autopilot-abc123-uc.a.run.app/ws
```

---

## 🧪 Running Tests

### Quick test (no server needed, calls Gemini directly):
```bash
cd backend
python test_single_scenario.py
```

### Full test suite (backend must be running):
```bash
# Terminal 1: Start backend
uvicorn backend:app --port 8080

# Terminal 2: Run tests
cd backend
python test_autopilot.py

# Skip Gemini API tests (faster, no API cost):
SKIP_GEMINI_TESTS=1 python test_autopilot.py

# Run a specific test class:
python test_autopilot.py TestGridOverlay -v
```

### Test suite coverage:

| Test Class | Tests | What It Verifies |
|---|---|---|
| TestHealthCheck | 3 | Server endpoints responding |
| TestScreenshotGeneration | 4 | Fake Outlook screenshots render correctly |
| TestGridOverlay | 4 | Grid overlay + cell-to-coordinate math |
| TestScreenshotComparison | 3 | Duplicate frame detection |
| TestSystemPrompt | 5 | Prompt contains all Outlook UI knowledge |
| TestWebSocket | 5 | Real-time WebSocket communication |
| TestEdgeCases | 4 | Rapid sends, empty data, unknown types |
| TestGeminiIntegration | 5 | End-to-end Gemini vision + action responses |

---

## 🎬 Demo Script (2 Minutes)

For judges to reproduce the demo:

1. Open Outlook 365 in Chrome with a few test emails in inbox
2. Start Autopilot via the extension
3. Try these commands in order:

| Say This | Expected Result |
|---|---|
| "What's in my inbox?" | Agent describes visible emails |
| "Open the first email" | Agent clicks the top email |
| "Reply to this" | Agent clicks Reply icon |
| "Type: Thanks, I'll review this by Monday" | Agent types the text |
| "Wait — change Monday to Wednesday" | Agent corrects the text |
| "Send it" | Agent asks: "Should I send?" → say "Yes" |
| "Go to my sent items" | Agent clicks Sent Items in sidebar |

---

## ⚙️ Configuration

Settings available in the extension popup:

| Setting | Default | Description |
|---|---|---|
| Screenshot interval | 1500ms | How often to capture the screen |
| Image quality | 90% | JPEG quality (higher = better accuracy, more bandwidth) |
| Confirm before actions | ✅ On | Ask user before Send/Delete actions |

---

## 🔧 Troubleshooting

| Issue | Fix |
|---|---|
| "WebSocket connection failed" | Check backend is running. Verify URL in popup matches server address. |
| "Microphone not working" | The popup must stay open for mic capture (Manifest V3 limitation). Re-click the extension icon if it closed. |
| "Agent clicks the wrong spot" | Ensure browser zoom is exactly 100%. Try increasing image quality to 95%. |
| "Debugger detached" warning | Normal Chrome security banner. Don't close it — it's needed for click simulation. |
| "Permission denied" errors | Reload extension at chrome://extensions. Re-grant permissions. |
| Gemini returns non-JSON | Rare — the backend handles this by treating it as a spoken response. |

---

## 💰 Cost

| Usage | Estimated Cost |
|---|---|
| Hackathon (10 hrs testing) | ~$1-3 (likely free with Gemini free tier) |
| Daily use (2 hrs/day, 30 days) | ~$5-15/month |

Google Cloud offers **$300 free credits** for new accounts, and Gemini Flash has a **generous free tier** (1,500 requests/day).

---

## 📄 Environment Variables

Create a `backend/.env` file:

```env
# Required
GEMINI_API_KEY=your_gemini_api_key_here

# Optional
PORT=8080
LOG_LEVEL=INFO
```

---

## 🏗️ Architecture

```
  Chrome Extension                    Cloud Run (Python)
 ┌────────────────────┐            ┌────────────────────────┐
 │ Tab Screenshot ────┼── WS ────▶│ FastAPI Backend         │
 │ Microphone Audio ──┼── WS ────▶│   ├─▶ Grid Overlay     │
 │ Execute Actions ◀──┼── WS ◀───│   ├─▶ Gemini Live API  │
 │ Play Audio ◀───────┼── WS ◀───│   └─▶ Action Parser    │
 └────────────────────┘            └────────────────────────┘
```

**Core loop:** Capture screen → Stream to Gemini with voice → Get action + confirmation → Execute click/type/scroll → Verify result → Repeat

---

## 🤝 Team

| Name | Role |
|---|---|
| [Your Name] | [Your Role] |
| [Team Member 2] | [Role] |
| [Team Member 3] | [Role] |

---

## 📜 License

MIT License — see [LICENSE](LICENSE) file.
