# Royal BetKing Demo Setup

## Required

- Keep backend/.env private. It contains the server-side access-key pepper and admin access key.
- Run the FastAPI backend before testing authentication or Gemini screenshot extraction.
- Keep the project in demo mode until it has been reviewed for its intended educational use.

## Quick Start Without Installing Packages

If FastAPI dependencies are not installed, double-click `start-demo.ps1` from the project folder. Then open `http://127.0.0.1:8000` and enter the admin key `777333111`. This launcher supports the frontend and secure access/session demo; Gemini screenshot analysis and cross-device demo announcements need the full FastAPI setup below.

## Optional

- Add a new Gemini API key to backend/.env as GEMINI_API_KEY. The previously shared key should be revoked and replaced.
- Replace the profile/image placeholders with course-approved artwork.
- Set a custom Android package name when preparing a Capacitor wrapper.
- Add local sound files only if you do not want the built-in browser sound.

## Demo Defaults

- Referral code: RBETKING
- Credit: $10 DEMO per qualifying simulated referral
- Maximum qualifying referrals: 10
- Demo threshold: $100 DEMO
- Telegram contact: Royal_BetKing

## Platform References

Platform URLs and promotion values intentionally remain disabled in config/app-config.js. Add only course-approved, lawful reference URLs after independently reviewing the platform and local regulations. Do not place wallet addresses, private API keys, or real payment details in frontend code.

## APK Packaging

1. Serve the app from the FastAPI backend, not a file URL.
2. Verify the app at phone widths before wrapping it.
3. Create a Capacitor project and set its webDir to the deployed frontend build.
4. Store device/session data using the platform secure storage plugin before distribution.
5. Use HTTPS for every deployed API endpoint.

The full FastAPI service exposes `/ws/demo`. An authenticated admin can publish a clearly labelled demo announcement, and authenticated user sessions connected to the same deployment receive it in real time. This channel is not a betting prediction or payment channel.
