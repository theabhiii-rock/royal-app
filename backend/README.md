# Royal BetKing analysis backend

This FastAPI service accepts a PNG, JPG, or WEBP screenshot, asks Gemini Vision to extract clearly visible multiplier values, and returns descriptive statistics. It does not generate betting predictions or process payments.

It also implements server-side, one-device access-key activation:

- User keys are stored only as a salted PBKDF2 hash plus a server-side lookup hash.
- The original user keys are not present in HTML, JavaScript, or source files.
- First successful activation binds a key to one locally generated device ID.
- Reusing the same key on another device returns an already-active message.
- The same registered device can reopen its session until it expires.
- Five failed attempts lock that device/IP combination for ten minutes.

## Setup

1. Create a virtual environment:

   ```powershell
   python -m venv backend/.venv
   ```

2. Install the dependencies:

   ```powershell
   backend/.venv/Scripts/python -m pip install -r backend/requirements.txt
   ```

3. Create `backend/.env` from `backend/.env.example`, then set:

   - `GEMINI_API_KEY` to your own Gemini API key.
   - `ACCESS_KEY_PEPPER` to a long, random server-only value.
   - `ADMIN_ACCESS_KEY` to your private nine-digit admin code.

   Never put any of these values into the HTML or commit `.env` to Git.
   Do not change `ACCESS_KEY_PEPPER` after keys have been imported; it is required to validate their stored hashes.

4. Start the service:

   ```powershell
   backend/.venv/Scripts/python -m uvicorn main:app --app-dir backend --reload --port 8000
   ```

5. Open <http://127.0.0.1:8000>. The same server hosts the frontend and the analysis API.

The API health endpoint is available at <http://127.0.0.1:8000/api/health>. Gemini API availability and quota depend on the Google account and current plan.

## Key management

The supplied user keys have already been imported into the ignored SQLite database at `backend/data/access_keys.sqlite3`. The plaintext values are not saved there.

Use the admin command from the project root. It asks privately for the admin key instead of putting it in command history:

    python backend/manage_keys.py status

When a user changes phone, clears app/browser storage, or needs a device replacement, release only that person's key:

    python backend/manage_keys.py release --key 123456789

After release, that key can activate on exactly one new device. Do not release it unless you have verified the user.

`seed_keys.py` is for a fresh empty key database only. It imports newline-separated keys from standard input after an admin prompt and refuses to import into a populated database.
