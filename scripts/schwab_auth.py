"""One-time Schwab OAuth2 authentication flow.

Run this script first to generate the token file:
    python -m scripts.schwab_auth

You'll be prompted to:
1. Open a URL in your browser
2. Log in to Schwab
3. Paste the redirect URL back into the terminal
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import settings


def main():
    print("=" * 50)
    print("  Schwab OAuth2 Authentication")
    print("=" * 50)

    if not settings.schwab_api_key or not settings.schwab_app_secret:
        print("\nERROR: Set SCHWAB_API_KEY and SCHWAB_APP_SECRET in .env first.")
        print("Get these from https://developer.schwab.com/")
        sys.exit(1)

    token_path = Path(settings.schwab_token_path)
    token_path.parent.mkdir(parents=True, exist_ok=True)

    if token_path.exists():
        overwrite = input(f"\nToken file already exists at {token_path}. Overwrite? [y/N]: ")
        if overwrite.lower() != "y":
            print("Keeping existing token.")
            return

    try:
        import schwab

        print(f"\nCallback URL: {settings.schwab_callback_url}")
        print("A browser window will open. Log in and authorize the app.")
        print("Then paste the full redirect URL (from your browser's address bar) below.\n")

        client = schwab.auth.client_from_manual_flow(
            api_key=settings.schwab_api_key,
            app_secret=settings.schwab_app_secret,
            callback_url=settings.schwab_callback_url,
            token_path=str(token_path),
        )

        print(f"\nAuthentication successful! Token saved to {token_path}")

        # Fetch account hash
        resp = client.get_account_numbers()
        accounts = resp.json()
        print("\nAvailable accounts:")
        for acct in accounts:
            print(f"  Hash: {acct['hashValue']}  Number: {acct.get('accountNumber', 'N/A')}")

        print("\nAdd your preferred SCHWAB_ACCOUNT_HASH to .env")

    except ImportError:
        print("ERROR: schwab-py not installed. Run: pip install schwab-py")
        sys.exit(1)
    except Exception as e:
        print(f"\nAuthentication failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
