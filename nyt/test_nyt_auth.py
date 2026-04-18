"""
Quick smoke test: load nyt_cookies.json, make one authenticated GET request to
NYT Cooking, print the HTTP status and first 500 chars of the response body.
Warns if the response looks like a login redirect.
"""

import json
import sys
import requests

COOKIE_FILE = "nyt_cookies.json"
TARGET_URL = "https://nl.nytimes.com/f/cooking/y11xySWACuXa95rhmVUiIg~~/AAAAARA~/or6OhBKPioVWtZe7Jf2aHFm97gbWQW9PaoUcBn0gRe3IaqQnKOLjvFOhV-yAuSQYGeYO9IBwwss3j_rZideqbzIj5v094epzAjferf-VYOciASDY1vdc5V1a_PzdxQCxIAYbQhnDvLSFYiafBUahWGu0brVK9MbETp0GO5IifRpRwQEIfoPSdpghtxfkaGLBAobstsuaTVN10_9uVDfELEu1LhaZoshO5ZZga-KNKoUxAMD0rMy2rTE_4Ul213IJMfEAynJe-sJEyMcEY8lvh6XcW63nyb1pj0bmTF3NcfEYAz_rVvc1CsH_OoErobdXghWfaPnFGcuj-mzj073AB-GMPdMNmZAfC-otzHJxJKr4k42I822f5Fjojwz7kVQM"

# Signals that the session is not authenticated / was redirected to login.
LOGIN_SIGNALS = [
    "login",
    "sign in",
    "create an account",
    "nytimes.com/auth",
    "myaccount.nytimes.com",
]


def load_cookies(path: str) -> dict[str, str]:
    """
    Load a browser-exported cookie JSON array and return a name→value dict
    suitable for passing to requests.

    Args:
        path: Path to the JSON file containing cookie objects with at least
              ``name`` and ``value`` keys.

    Returns:
        A flat {name: value} dictionary of all cookies in the file.
    """
    with open(path) as f:
        raw: list[dict] = json.load(f)
    return {c["name"]: c["value"] for c in raw if "name" in c and "value" in c}


def check_login_redirect(text: str) -> bool:
    """
    Return True if any known login-wall signal appears in *text* (case-insensitive).

    Args:
        text: The response body (or a prefix of it).

    Returns:
        True if a login redirect is detected, False otherwise.
    """
    lower = text.lower()
    return any(signal in lower for signal in LOGIN_SIGNALS)


def main() -> None:
    cookies = load_cookies(COOKIE_FILE)
    print(f"Loaded {len(cookies)} cookies from {COOKIE_FILE}")

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }

    resp = requests.get(TARGET_URL, cookies=cookies, headers=headers, timeout=15)

    print(f"\nHTTP status : {resp.status_code}")
    print(f"Final URL   : {resp.url}")
    print(f"\n--- First 500 chars of response body ---")
    snippet = resp.text[:500]
    print(snippet)
    print("--- end ---")

    if check_login_redirect(snippet) or check_login_redirect(resp.url):
        print("\n⚠  WARNING: Response appears to contain a login redirect. "
              "Cookies may be expired or missing required auth tokens.")
    else:
        print("\n✓  No login redirect detected.")


if __name__ == "__main__":
    main()
