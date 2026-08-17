import os
import json
import base64
import requests
import urllib3  # 🟢 SSL ওয়ার্নিং ডিসেবল করার জন্য
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad

# ❌ পাইথনের ইনসিকিউর রিকোয়েস্ট ওয়ার্নিংগুলো বন্ধ করা হচ্ছে
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


# 🔑 আপনার মেইন সিক্রেট ভ্যালুগুলো (Environment / GitHub Secrets থেকে আসবে)
AES_KEY = os.environ.get("MY_AES_KEY", "").encode("utf-8")
AES_IV = os.environ.get("MY_AES_IV", "").encode("utf-8")


# 🌐 হোস্টিং ১ ও ২ এর ডিটেইলস (GitHub Secrets থেকে আসবে)
RECEIVER_URL_1 = os.environ.get("MY_RECEIVER_URL", "")
HOSTING_AUTH_TOKEN_1 = os.environ.get("MY_HOSTING_TOKEN", "")
RECEIVER_URL_2 = os.environ.get("MY_RECEIVER_URL_2", "")
HOSTING_AUTH_TOKEN_2 = os.environ.get("MY_HOSTING_TOKEN", "")


# 🔤 সিক্রেট থেকে কাস্টম ডিক্রিপশন টেবিল রিকভার করা হচ্ছে
try:
    f13875a = json.loads(os.environ.get("SECRET_ARRAY_A", "[]"))
    f13876b = json.loads(os.environ.get("SECRET_ARRAY_B", "[]"))
except Exception as table_err:
    print(f"❌ ডিক্রিপশন টেবিল লোড করতে সমস্যা: {table_err}")
    f13875a, f13876b = [], []


# ⚙️ কাস্টম প্রতিস্থাপন টেবিল জেনারেট করা (যদি সিক্রেট ডাটা ঠিক থাকে)
f13878d = [chr(i) for i in range(128)]
if f13875a and f13876b and len(f13875a) == len(f13876b):
    for i in range(len(f13875a)):
        source_char_ord = ord(f13876b[i])
        if source_char_ord < 128:
            f13878d[source_char_ord] = f13875a[i]


def fetch_firebase_remote_config():
    """১ম ধাপ: সম্পূর্ণ হাইড করা সিক্রেট থেকে ফায়ারবেস ডাটা এনে মেমোরিতে লোড করে"""
    api_key = os.environ.get("FIREBASE_SECRET_API_KEY", "")
    project_id = os.environ.get("FIREBASE_SECRET_PROJECT_ID", "")
    app_id = os.environ.get("FIREBASE_SECRET_APP_ID", "")
    package_name = os.environ.get("FIREBASE_SECRET_PACKAGE_NAME", "")

    if not api_key or not project_id or not app_id:
        print("❌ ভুল: ফায়ারবেসের প্রয়োজনীয় সিক্রেট ভ্যালুগুলো এনভায়রনমেন্টে সেট করা নেই!")
        return None

    url = f"https://firebaseremoteconfig.googleapis.com/v1/projects/{project_id}/namespaces/firebase:fetch?key={api_key}"

    payload = {
        "appId": app_id,
        "appInstanceId": "REQUIRED_BUT_CAN_BE_RANDOM_12345",
        "countryCode": "BD",
        "languageCode": "bn-BD",
        "platformVersion": "33",
        "timeZone": "Asia/Dhaka",
        "packageName": package_name if package_name else "com.livxow.tv",
        "sdkVersion": "23.0.1",
    }

    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Dalvik/2.1.0 (Linux; U; Android 13; Build/TP1A.220624.014)",
    }

    print("🛰️ Firebase Remote Config থেকে ডাইনামিক API URL খোঁজা হচ্ছে...")

    try:
        response = requests.post(
            url, data=json.dumps(payload), headers=headers, timeout=15
        )
        if response.status_code == 200:
            config_data = response.json()

            with open("remote_config_response.json", "w", encoding="utf-8") as f:
                json.dump(config_data, f, indent=4, ensure_ascii=False)

            if "entries" in config_data:
                entries = config_data["entries"]
                os.environ["FIREBASE_LIVE_API_URL"] = entries.get("api_url", "")
                os.environ["FIREBASE_NEW_TELEGRAM_URL"] = entries.get(
                    "new_telegram_url", ""
                )
                os.environ["FIREBASE_TELEGRAM_URL"] = entries.get("telegram_url", "")
                os.environ["FIREBASE_WEB_URL"] = entries.get("web_url", "")

            print("💾 Firebase থেকে লাইভ URL সফলভাবে মেমোরিতে লোড করা হয়েছে।")
            return entries.get("api_url", "")
        else:
            print(
                f"❌ ফায়ারবেস থেকে ডাটা পাওয়া যায়নি। স্ট্যাটাস: {response.status_code}"
            )
            return None
    except Exception as e:
        print(f"❌ ফায়ারবেস কানেকশন এরর: {e}")
        return None


def custom_substitute(raw_str):
    decrypted_chars = []
    for char in raw_str:
        char_code = ord(char)
        if char_code < 128:
            decrypted_chars.append(f13878d[char_code])
        else:
            decrypted_chars.append(char)
    return "".join(decrypted_chars)


def decrypt_data(encrypted_text):
    if not encrypted_text or len(encrypted_text.strip()) == 0:
        return None
    try:
        fixed_base64_str = custom_substitute(encrypted_text.strip())
        encrypted_bytes = base64.b64decode(fixed_base64_str)
        cipher = AES.new(AES_KEY, AES.MODE_CBC, AES_IV)
        decrypted_bytes = unpad(cipher.decrypt(encrypted_bytes), AES.block_size)
        return decrypted_bytes.decode("utf-8")
    except Exception:
        return encrypted_text.strip()


def fetch_and_decrypt_link(base_url, link_path):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) GitHubActions/1.0"
    }
    full_url = f"{base_url}{link_path.lstrip('/')}"
    try:
        res = requests.get(full_url, headers=headers, timeout=15, verify=False)
        if res.status_code == 200:
            decrypted_content = decrypt_data(res.text)
            if decrypted_content:
                try:
                    parsed_links = json.loads(decrypted_content)
                    if isinstance(parsed_links, str):
                        parsed_links = json.loads(parsed_links)
                    return parsed_links
                except json.JSONDecodeError:
                    return [
                        l.strip()
                        for l in decrypted_content.split("\n")
                        if l.strip()
                    ]
        return []
    except Exception:
        return []


def clean_and_parse_events(raw_json_str):
    try:
        raw_list = json.loads(raw_json_str)
        cleaned_list = []
        for item in raw_list:
            if "event" in item:
                event_data = item["event"]
                if isinstance(event_data, str):
                    try:
                        parsed_event = json.loads(event_data)
                        cleaned_list.append(parsed_event)
                    except json.JSONDecodeError:
                        continue
                else:
                    cleaned_list.append(event_data)
        return cleaned_list
    except Exception as e:
        print(f"❌ ইভেন্ট পার্সিং এরর: {e}")
        return None


def run():
    base_url_from_firebase = os.environ.get("FIREBASE_LIVE_API_URL", "")

    if not base_url_from_firebase:
        print("❌ মেমোরিতে কোনো BASE_URL পাওয়া যায়নি। স্ক্রিপ্ট বন্ধ করা হচ্ছে।")
        return

    BASE_URL = base_url_from_firebase.rstrip("/") + "/"
    TARGET_URL = f"{BASE_URL}events.txt"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) GitHubActions/1.0"
    }

    try:
        response = requests.get(
            TARGET_URL, headers=headers, timeout=20, verify=False
        )
        response.raise_for_status()

        print("🔓 মূল ইভেন্ট ডাটা ডিক্রিপ্ট করা হচ্ছে...")
        decrypted_json_str = decrypt_data(response.text)

        if decrypted_json_str:
            final_events = clean_and_parse_events(decrypted_json_str)

            if final_events:
                total_events = len(final_events)
                print(f"✅ মোট {total_events} টি ম্যাচ/ইভেন্ট পাওয়া গেছে।")

                for index, event in enumerate(final_events, 1):
                    link_file_path = event.get("links")
                    event["stream_links"] = []

                    if link_file_path and (
                        "pro/" in link_file_path or ".txt" in link_file_path
                    ):
                        print(
                            f"   [{index}/{total_events}] লিঙ্ক ডিকোর্ড হচ্ছে ➔ {event.get('teamAName')} vs {event.get('teamBName')}"
                        )
                        real_links_json = fetch_and_decrypt_link(
                            BASE_URL, link_file_path
                        )
                        event["stream_links"] = real_links_json

                    if "links" in event:
                        del event["links"]

                # 🔄 টার্গেট সার্ভার লিস্টে ডাটা পাঠানো (২টি হোস্টিংয়েই ডেটা যাবে)
                targets = []
                if RECEIVER_URL_1 and HOSTING_AUTH_TOKEN_1:
                    targets.append(("সার্ভার ১", RECEIVER_URL_1, HOSTING_AUTH_TOKEN_1))
                if RECEIVER_URL_2 and HOSTING_AUTH_TOKEN_2:
                    targets.append(
                        ("সার্ভার ২ (নতুন)", RECEIVER_URL_2, HOSTING_AUTH_TOKEN_2)
                    )

                if not targets:
                    print(
                        "\n❌ এরর: কোনো হোস্টিং ইউআরএল অথবা টোকেন সেট করা নেই!"
                    )
                    return

                for name, url, token in targets:
                    print(f"\n🌐 {name}-এ ফাইনাল ডাটা পাঠানো হচ্ছে...")
                    post_headers = {
                        "Content-Type": "application/json",
                        "X-Auth-Token": token,
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) GitHubActions/1.0",
                    }
                    try:
                        upload_res = requests.post(
                            url,
                            json=final_events,
                            headers=post_headers,
                            timeout=60,
                            verify=False,
                        )
                        if upload_res.status_code == 200:
                            print(f"🚀 সফলভাবে {name}-এ ডেটা আপডেট হয়েছে!")
                        else:
                            print(
                                f"❌ {name} আপলোড ফেল করেছে। স্ট্যাটাস কোড: {upload_res.status_code}"
                            )
                    except Exception as upload_error:
                        print(
                            f"❌ {name}-এ ডেটা পাঠানোর সময় এরর: {upload_error}"
                        )

    except Exception as e:
        print(f"❌ রানটাইম এরর: {e}")


if __name__ == "__main__":
    fetch_firebase_remote_config()
    run()
