# Till

An AI coach for young founders and side hustles, built with Streamlit and Groq. Users log what comes in and goes out. Till works out what they keep, spots problems and suggests their next move.

## Run it

Requires Python 3.10 or newer.

```bash
pip install -r requirements.txt
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
# paste your key from https://console.groq.com/keys into secrets.toml
streamlit run app.py
```

Users never see or enter a key. The app uses the one you set here for everyone.
Never paste the key into the code or commit `secrets.toml`.

## Put it online

1. Push this folder to a private GitHub repo.
2. Deploy it on Streamlit Community Cloud, or another host.
3. Paste `GROQ_API_KEY = "your_key"` into the host's Secrets box.

Read "Before real users" first, because the storage point matters.

## How it fits together

| File | Job |
|---|---|
| `app.py` | Login check and navigation |
| `till/analytics.py` | All business maths and automatic alerts |
| `till/copilot.py` | Groq calls, prompts and model fallback |
| `till/views.py` | Every screen |
| `till/ui.py` | Styling and charts |
| `till/db.py` | SQLite storage |
| `till/demo.py` | The sample thrift business |

The app calculates every figure and hands the AI a fact sheet, so the AI explains the numbers rather than producing them.

## Settings

| Setting | Purpose |
|---|---|
| `GROQ_API_KEY` | Your Groq key, shared by all users |
| `TILL_DAILY_AI_LIMIT` | AI requests per user per day. Default is 25 |
| `GROQ_MODEL` | Optional preferred model. Default is `openai/gpt-oss-120b`, with `openai/gpt-oss-20b` as backup |
| `TILL_DB` | Optional database file path. Default is `data/till.db` |

Groq changes its model list often. If both models are retired, update `MODELS` in `till/copilot.py`.

## Tests

```bash
pip install pytest
python -m pytest
```

## Before real users

- **Storage:** Streamlit Community Cloud wipes local files on restart, so accounts and records would disappear. Use a host with a persistent disk, or move `till/db.py` to a hosted database.
- **Cost:** every user runs on your Groq account. The daily limit caps each user, but not the number of users. Set a spend limit in your Groq console.
- **Sign-in:** refreshing the browser logs the user out, and there is no password reset or login attempt limit yet.
- **Privacy:** summaries including customer names go to Groq. Publish a privacy notice and check local data protection rules, including any rules for users under 18.
- **Market data:** Till has no web access, so it only knows about competitors from what users enter.
