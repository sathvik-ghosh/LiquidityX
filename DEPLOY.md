# Hosting LIQUIDITYX

The web app is `app.py` (Streamlit). It uses the same Python engines as the desktop version.
Each visitor gets a **private, in-memory workspace with synthetic demo data**; nothing is stored or shared, and a restart resets it.

## 0. Run it locally first
```bash
pip install -r requirements.txt
streamlit run app.py          # opens http://localhost:8501
pip install -r requirements-dev.txt && pytest -q   # optional: 25 tests
```

## 1. Streamlit Community Cloud (free, easiest)
1. Create a GitHub account → **New repository** (public is simplest).
2. Upload everything in this folder (keep `app.py`, `requirements.txt`, `liquidityx/` and `.streamlit/` at the repo root).
   Command line alternative:
   ```bash
   git init && git add . && git commit -m "LiquidityX"
   git branch -M main && git remote add origin https://github.com/<you>/liquidityx.git && git push -u origin main
   ```
3. Go to https://share.streamlit.io → sign in with GitHub → **Create app** → choose the repo, branch `main`, main file `app.py`.
4. (Advanced settings → Python 3.12.) Click **Deploy**. In ~2 minutes you get `https://<name>.streamlit.app`.

## 2. Render (free tier, sleeps when idle)
Push to GitHub, then Render → **New → Blueprint** → select the repo (it reads `render.yaml`). Or **New → Web Service** with
build `pip install -r requirements.txt` and start `streamlit run app.py --server.port $PORT --server.address 0.0.0.0`.

## 3. Docker / any VPS / Railway / Fly.io / Cloud Run
```bash
docker build -t liquidityx .
docker run -p 8501:8501 liquidityx            # http://localhost:8501
```
Push the image or connect the repo; the container honours the `$PORT` variable.

## 4. Hugging Face Spaces
New Space → SDK **Streamlit** → upload the files (or push the repo). Spaces runs `app.py` automatically.

## Before sharing the link publicly
* It is a **demo on synthetic data**: do not enter real company data (no login, no encryption at rest, sessions live in server memory).
* Anyone with the link can use it. For a private demo use Streamlit Cloud "Viewer authentication" (private app) or put it behind an auth proxy.
* For real users you would add authentication, a real database (PostgreSQL) and per-company data separation, as listed in the roadmap.
* Free tiers sleep after inactivity; the first visit after a nap takes ~30 s.

---
## Option B — the real Tkinter app, shown in a browser (Docker only)
`Dockerfile.tk` runs `main.py` on a virtual screen (Xvfb) and streams it to the browser with noVNC. Same Tkinter UI, no rewrite.
```bash
docker build -f Dockerfile.tk -t liquidityx-tk .
docker run -p 8080:8080 -e VNC_PASSWORD=choose-one liquidityx-tk
# open: http://localhost:8080/vnc.html?autoconnect=true&resize=scale
```
Host it on Render (`render-tk.yaml`, needs a paid instance), Railway, Fly.io, or any VPS with Docker.
Limits you must know: **all visitors share ONE desktop session** (they see and control the same window), so use it for a single presenter, set
`VNC_PASSWORD`, and use `VIEW_ONLY=1` if viewers should only watch. It is heavier and laggier than the Streamlit version (Option A, `app.py`),
which gives every visitor a private session — prefer Option A for a public link.
