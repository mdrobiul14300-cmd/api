import os
import json
import base64
import requests
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad

# 🔐 গিটহাব সিক্রেটস থেকে ডাটা লোড করা হচ্ছে (লোকালি না থাকলে ফলব্যাক ভ্যালু ব্যবহার করবে)
AES_KEY = os.environ.get("MY_AES_KEY", "").encode('utf-8')
AES_IV = os.environ.get("MY_AES_IV", "").encode('utf-8')
BASE_URL = os.environ.get("MY_BASE_URL", "")
TARGET_URL = f"{BASE_URL}events.txt"

# 🔄 কাস্টম ক্যারেক্টার ম্যাপিং সেটআপ (yb.a.b)
f13875a = ['a', 'A', 'b', 'B', 'c', 'C', 'd', 'D', 'e', 'E', 'f', 'F', 'g', 'G', 'h', 'H', 'i', 'I', 'j', 'J', 'k', 'K', 'l', 'L', 'm', 'M', 'n', 'N', 'o', 'O', 'p', 'P', 'q', 'Q', 'r', 'R', 's', 'S', 't', 'T', 'u', 'U', 'v', 'V', 'w', 'W', 'x', 'X', 'y', 'Y', 'z', 'Z']
f13876b = ['f', 'F', 'g', 'G', 'j', 'J', 'k', 'K', 'a', 'A', 'p', 'P', 'b', 'B', 'm', 'M', 'o', 'O', 'z', 'Z', 'e', 'E', 'n', 'N', 'c', 'C', 'd', 'D', 'r', 'R', 'q', 'Q', 't', 'T', 'v', 'V', 'u', 'U', 'x', 'X', 'h', 'H', 'i', 'I', 'w', 'W', 'y', 'Y', 'l', 'L', 's', 'S']

f13878d = [chr(i) for i in range(128)]
for i in range(len(f13875a)):
    source_char_ord = ord(f13876b[i])
    if source_char_ord < 128:
        f13878d[source_char_ord] = f13875a[i]

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
        return decrypted_bytes.decode('utf-8')
    except Exception:
        return encrypted_text.strip()

def fetch_and_decrypt_link(link_path):
    headers = {"User-Agent": "okhttp/4.9.0"}
    full_url = f"{BASE_URL}{link_path.lstrip('/')}"
    try:
        res = requests.get(full_url, headers=headers, timeout=10)
        if res.status_code == 200:
            decrypted_content = decrypt_data(res.text)
            if decrypted_content:
                try:
                    parsed_links = json.loads(decrypted_content)
                    if isinstance(parsed_links, str):
                        parsed_links = json.loads(parsed_links)
                    return parsed_links
                except json.JSONDecodeError:
                    return [l.strip() for l in decrypted_content.split('\n') if l.strip()]
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
    print("⏳ সার্ভার থেকে মূল ইভেন্ট লিস্ট নামানো হচ্ছে...")
    headers = {"User-Agent": "okhttp/4.9.0"}
    
    try:
        response = requests.get(TARGET_URL, headers=headers, timeout=20)
        response.raise_for_status()
        
        print("🔓 মূল ইভেন্ট ডাটা ডিক্রিপ্ট করা হচ্ছে...")
        decrypted_json_str = decrypt_data(response.text)
        
        if decrypted_json_str:
            final_events = clean_and_parse_events(decrypted_json_str)
            
            if final_events:
                total_events = len(final_events)
                print(f"✅ মোট {total_events} টি ম্যাচ/ইভেন্ট পাওয়া গেছে।")
                
                for index, event in enumerate(final_events, 1):
                    link_file_path = event.get("links")
                    event["stream_links"] = [] 
                    
                    if link_file_path and ("pro/" in link_file_path or ".txt" in link_file_path):
                        print(f"   [{index}/{total_events}] লিঙ্ক ডিকোড হচ্ছে ➔ {event.get('teamAName')} vs {event.get('teamBName')}")
                        real_links_json = fetch_and_decrypt_link(link_file_path)
                        event["stream_links"] = real_links_json
                    
                    if "links" in event:
                        del event["links"]
                
                # ফাইলটি সেভ করা হচ্ছে
                with open("decrypted_events.json", "w", encoding="utf-8") as f:
                    json.dump(final_events, f, indent=4, ensure_ascii=False)
                print("\n💾 ডাটা সফলভাবে 'decrypted_events.json' ফাইলে সেভ হয়েছে।")
                
    except Exception as e:
        print(f"❌ রানটাইম এরর: {e}")

if __name__ == "__main__":
    run()
