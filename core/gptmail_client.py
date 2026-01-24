import time
import requests
from typing import Optional
from datetime import datetime
from core.mail_utils import extract_verification_code

class GPTMailClient:
    """GPTMail API Client"""

    def __init__(
        self,
        base_url: str = "https://mail.chatgpt.org.uk",
        api_key: str = "",
        log_callback=None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key.strip()
        self.log_callback = log_callback
        self.email: Optional[str] = None

    def _log(self, level: str, message: str) -> None:
        if self.log_callback:
            try:
                self.log_callback(level, message)
            except Exception:
                pass

    def _request(self, method: str, url: str, **kwargs) -> requests.Response:
        """Send request with logging"""
        headers = kwargs.pop("headers", {})
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        
        # Default headers
        headers.setdefault("Content-Type", "application/json")
        kwargs["headers"] = headers

        self._log("info", f"📤 Sending {method} request: {url}")
        
        try:
            res = requests.request(method, url, timeout=kwargs.pop("timeout", 15), **kwargs)
            # self._log("info", f"📥 Received response: HTTP {res.status_code}") # Reduce verbosity
            return res
        except Exception as e:
            self._log("error", f"❌ Network request failed: {e}")
            raise

    def register_account(self, domain: Optional[str] = None) -> bool:
        """Generate a new email address"""
        url = f"{self.base_url}/api/generate-email"
        
        try:
            if domain:
                # If domain is provided, use POST to specify it
                # We can generate a random prefix
                import random
                import string
                prefix = "".join(random.choices(string.ascii_lowercase + string.digits, k=10))
                payload = {"prefix": prefix, "domain": domain}
                self._log("info", f"📤 Requesting email with domain: {domain}")
                res = self._request("POST", url, json=payload)
            else:
                # Otherwise use GET for a fully random email
                self._log("info", "📤 Requesting random email...")
                res = self._request("GET", url)

            if res.status_code == 200:
                data = res.json()
                if data.get("success"):
                    self.email = data["data"]["email"]
                    self._log("info", f"✅ Email generated: {self.email}")
                    return True
                else:
                    self._log("error", f"❌ API Error: {data.get('error')}")
            else:
                self._log("error", f"❌ Request failed: HTTP {res.status_code}")
                
        except Exception as e:
            self._log("error", f"❌ Exception during registration: {e}")
        
        return False

    def poll_for_code(
        self,
        timeout: int = 120,
        interval: int = 4,
        since_time=None,
    ) -> Optional[str]:
        """Poll for verification code"""
        if not self.email:
            self._log("error", "❌ No email address to poll for")
            return None

        max_retries = timeout // interval
        self._log("info", f"⏱️ Polling for code (timeout {timeout}s)...")

        for i in range(1, max_retries + 1):
            code = self._fetch_verification_code(since_time=since_time)
            if code:
                return code
            
            if i < max_retries:
                time.sleep(interval)

        self._log("error", f"⏰ Polling timed out after {timeout}s")
        return None

    def _fetch_verification_code(self, since_time=None) -> Optional[str]:
        """Fetch emails and extract code"""
        url = f"{self.base_url}/api/emails"
        try:
            res = self._request("GET", url, params={"email": self.email})
            if res.status_code != 200:
                return None

            data = res.json()
            if not data.get("success"):
                return None

            emails = data.get("data", {}).get("emails", [])
            if not emails:
                return None

            for msg in emails:
                # Check timestamp if needed
                # format: "2025-11-14 10:30:00"
                if since_time:
                    created_at_str = msg.get("created_at")
                    if created_at_str:
                        try:
                            msg_time = datetime.strptime(created_at_str, "%Y-%m-%d %H:%M:%S")
                            if msg_time < since_time:
                                continue
                        except ValueError:
                            pass # If parsing fails, ignore time check or log warning

                # Check content
                content = msg.get("content", "")
                html_content = msg.get("html_content", "")
                full_text = content + " " + html_content
                
                code = extract_verification_code(full_text)
                if code:
                    self._log("info", f"🎉 Verification code found: {code}")
                    return code

            return None

        except Exception as e:
            self._log("error", f"❌ Fetch error: {e}")
            return None
