import requests
import os
import uuid
import argparse

# --- NEW: Import Google Auth libraries ---
# These will help us get the necessary token for Cloud Run.
try:
    import google.auth
    from google.oauth2 import id_token
    from google.auth.transport.requests import Request as GoogleAuthRequest
except ImportError:
    print("Error: The 'google-auth' and 'requests' libraries are required.")
    print("Please install them using: pip install google-auth requests")
    exit(1)


# --- Configuration ---
# Get the agent service URL from an environment variable, with a default for your deployed service.
AGENT_SERVICE_URL = os.getenv("AGENT_ENDPOINT_URL", "https://everlight-agents-258412455920.us-west1.run.app")
MESSAGE_ENDPOINT = f"{AGENT_SERVICE_URL}/message"


def get_gcp_identity_token(audience: str) -> str | None:
    return "eyJhbGciOiJSUzI1NiIsImtpZCI6ImRkNTMwMTIwNGZjMWQ2YTBkNjhjNzgzYTM1Y2M5YzEwYjI1ZTFmNGEiLCJ0eXAiOiJKV1QifQ.eyJpc3MiOiJodHRwczovL2FjY291bnRzLmdvb2dsZS5jb20iLCJhenAiOiIzMjU1NTk0MDU1OS5hcHBzLmdvb2dsZXVzZXJjb250ZW50LmNvbSIsImF1ZCI6IjMyNTU1OTQwNTU5LmFwcHMuZ29vZ2xldXNlcmNvbnRlbnQuY29tIiwic3ViIjoiMTAwMDAzMjQwNTEwODIyNjU2NDc3IiwiZW1haWwiOiJ0b21teXlsaXVAZ21haWwuY29tIiwiZW1haWxfdmVyaWZpZWQiOnRydWUsImF0X2hhc2giOiJ3UlZJY2EwbTg0TjViT055WW02Qi1nIiwiaWF0IjoxNzUzNDk4MDU1LCJleHAiOjE3NTM1MDE2NTV9.VMShPQZfMRWbY2ci0fh3iav84pZnAbysu8FQNtrkM_11xX9WVcJ0dvcW3Dm4ECEn1hsR7W_nag2UL4l-xhUMOJ5V-b5tW3r5kz9IswhcKI6K_wENZyQyhroyFWq8oIyKBsuRsdupcIyJj7RWbCP1-_X5uXy8jWOqbHOTwxL3HXWtXnpcdI2WPdVv8Sd6SRm3jStJInDod0H_z4s-gJ3T2c2cUlWX-WJl8TBmvguDY0qhF1HwKDh00tSpuKxldNT0irKCNpP-8OX1xYthc8TP4bo7bAZhncFd7j3DESUr2MkTsGM6HHyZnInqbM2tNwj0khTVfm36ebCJtGRvAgFpuQ"


def send_agent_message(user_id: str, channel: str, message: str, sender: str):
    """
    Sends a message to the Everlight Agents service endpoint.
    It automatically adds an auth token if the target is a Cloud Run URL.
    """
    # Basic validation to ensure the user_id is a valid UUID format.
    try:
        uuid.UUID(user_id)
    except ValueError:
        print(f"Error: '{user_id}' is not a valid UUID. Please provide a valid user ID.")
        return

    payload = {
        "user_id": user_id,
        "channel": channel,
        "message": message,
        "sender": sender,
    }

    headers = {
        "Content-Type": "application/json"
    }

    # --- NEW: Add auth token for deployed services ---
    # We check if the URL is a Cloud Run URL and add the token if it is.
    if "run.app" in AGENT_SERVICE_URL:
        print("Detected Cloud Run URL. Attempting to fetch identity token...")
        token = get_gcp_identity_token(audience=AGENT_SERVICE_URL)
        if not token:
            print("Could not obtain auth token. Aborting request.")
            return
        headers["Authorization"] = f"Bearer {token}"
        print("Successfully added Authorization header.")
    else:
        print("Localhost URL detected. Skipping authentication.")


    print(f"\nSending message to: {MESSAGE_ENDPOINT}")
    print(f"Payload: {payload}")

    try:
        # Make the POST request to the FastAPI endpoint
        response = requests.post(MESSAGE_ENDPOINT, json=payload, headers=headers)

        # Raise an exception for bad status codes (e.g., 403, 404, 500)
        response.raise_for_status()

        print("\n--- Server Response ---")
        print(f"Status Code: {response.status_code}")
        print(f"Response Body: {response.json()}")
        print("-----------------------")

    except requests.exceptions.RequestException as e:
        print(f"\n--- An Error Occurred ---")
        print(f"Failed to send message: {e}")
        print("--------------------------")


if __name__ == "__main__":
    # --- Command-Line Interface Setup ---
    parser = argparse.ArgumentParser(
        description="Send a test message to the Everlight Agents service.",
        formatter_class=argparse.RawTextHelpFormatter
    )

    parser.add_argument("user_id", help="The UUID of the user.")
    parser.add_argument("message", help="The message content to send.")

    parser.add_argument(
        "--channel",
        default="user-input",
        help="The channel to send the message to (default: user-input)."
    )
    parser.add_argument(
        "--sender",
        default="test-script",
        help="The name of the sender (default: test-script)."
    )

    args = parser.parse_args()

    send_agent_message(
        user_id=args.user_id,
        channel=args.channel,
        message=args.message,
        sender=args.sender
    )
