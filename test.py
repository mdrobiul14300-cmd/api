import os
import json
import base64
import requests
from datetime import datetime
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad, pad

# ========== ENV VARIABLES ==========
# Source 1 (Doc 1 - events.txt style)
AES_KEY = os.environ.get("MY_AES_KEY", "").encode('utf-8')
AES_IV  = os.environ.get("MY_AES_IV",  "").encode('utf-8')
BASE_URL   = os.environ.get("MY_BASE_URL", "").rstrip('/') + "/"
TARGET_URL = f"{BASE_URL}events.txt"

# Source 2 (Doc 2 - SportzX/Firebase style)
APP_PASSWORD   = os.environ.get("APP_PASSWORD", "")
FIREBASE_API_KEY = os.environ.get("FIREBASE_API_KEY", "")
FIREBASE_FID     = os.environ.get("FIREBASE_FID", "")
FIREBASE_APP_ID  = os.environ.get("FIREBASE_APP_ID", "")
PROJECT_NUMBER   = os.environ.get("PROJECT_NUMBER", "")
PACKAGE_NAME     = os.environ.get("PACKAGE_NAME", "")
AES_SECRET       = os.environ.get("AES_SECRET", "")

# Output
RECEIVER_URL        = os.environ.get("MY_RECEIVER_URL", "")
HOSTING_AUTH_TOKEN  = os.environ.get("MY_HOSTING_TOKEN", "")

HEADERS = {"User-Agent": "okhttp/4.9.0"}

# =====================================================================
# SOURCE 1 HELPERS  (Doc-1 / events.txt approach)
# =====================================================================
f13875a = ['a','A','b','B','c','C','d','D','e','E','f','F','g','G','h','H','i','I','j','J','k','K','l','L','m','M','n','N','o','O','p','P','q','Q','r','R','s','S','t','T','u','U','v','V','w','W','x','X','y','Y','z','Z']
f13876b = ['f','F','g','G','j','J','k','K','a','A','p','P','b','B','m','M','o','O','z','Z','e','E','n','N','c','C','d','D','r','R','q','Q','t','T','v','V','u','U','x','X','h','H','i','I','w','W','y','Y','l','L','s','S']

f13878d = [chr(i) for i in range(128)]
for _i in range(len(f13875a)):
    _src = ord(f13876b[_i])
    if _src < 128:
        f13878d[_src] = f13875a[_i]

def _custom_sub(raw):
    out = []
    for ch in raw:
        c = ord(ch)
        out.append(f13878d[c] if c < 128 else ch)
    return "".join(out)

def _decrypt_s1(enc_text):
    if not enc_text or not enc_text.strip():
        return None
    try:
        fixed = _custom_sub(enc_text.strip())
        enc_bytes = base64.b64decode(fixed)
        cipher = AES.new(AES_KEY, AES.MODE_CBC, AES_IV)
        dec = unpad(cipher.decrypt(enc_bytes), AES.block_size)
        return dec.decode('utf-8')
    except Exception:
        return enc_text.strip()

def _fetch_decrypt_link_s1(link_path):
    url = f"{BASE_URL}{link_path.lstrip('/')}"
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        if r.status_code == 200:
            dec = _decrypt_s1(r.text)
            if dec:
                try:
                    parsed = json.loads(dec)
                    if isinstance(parsed, str):
                        parsed = json.loads(parsed)
                    return parsed
                except json.JSONDecodeError:
                    return [l.strip() for l in dec.split('\n') if l.strip()]
    except Exception:
        pass
    return []

def fetch_source1():
    """Fetch & decrypt events from Source 1 (events.txt)."""
    print("📡 Source-1: events.txt ডাউনলোড হচ্ছে...")
    try:
        r = requests.get(TARGET_URL, headers=HEADERS, timeout=20)
        r.raise_for_status()
    except Exception as e:
        print(f"  ❌ Source-1 fetch error: {e}")
        return []

    dec = _decrypt_s1(r.text)
    if not dec:
        print("  ❌ Source-1 decrypt failed")
        return []

    try:
        raw_list = json.loads(dec)
    except Exception:
        print("  ❌ Source-1 JSON parse failed")
        return []

    events = []
    total = len(raw_list)
    for idx, item in enumerate(raw_list, 1):
        ev_data = item.get("event", item)
        if isinstance(ev_data, str):
            try:
                ev_data = json.loads(ev_data)
            except Exception:
                continue

        # Resolve stream links
        link_path = ev_data.get("links", "")
        stream_links = []
        if link_path and ("pro/" in link_path or ".txt" in link_path):
            print(f"  [{idx}/{total}] লিঙ্ক ডিকোড ➔ {ev_data.get('teamAName','?')} vs {ev_data.get('teamBName','?')}")
            raw_links = _fetch_decrypt_link_s1(link_path)
            stream_links = raw_links if isinstance(raw_links, list) else []

        ev_data.pop("links", None)
        ev_data["stream_links"] = stream_links
        ev_data["_source"] = "source1"
        events.append(ev_data)

    print(f"  ✅ Source-1: {len(events)} events")
    return events


# =====================================================================
# SOURCE 2 HELPERS  (Doc-2 / SportzX / Firebase approach)
# =====================================================================
import re

def _gen_aes_key_iv_s2(s):
    CHARSET = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+!@#$%&="
    def u32(x): return x & 0xFFFFFFFF
    data = s.encode('utf-8')
    n = len(data)
    u = 0x811c9dc5
    for b in data: u = u32((u ^ b) * 0x1000193)
    key = bytearray(16)
    for i in range(16):
        b = data[i % n]
        u = u32(u * 0x1f + (i ^ b))
        key[i] = CHARSET[u % len(CHARSET)]
    u = 0x811c832a
    for b in data: u = u32((u ^ b) * 0x1000193)
    iv = bytearray(16)
    idx2, acc = 0, 0
    while idx2 != 0x30:
        b = data[idx2 % n]
        u = u32(u * 0x1d + (acc ^ b))
        iv[idx2 // 3] = CHARSET[u % len(CHARSET)]
        idx2 += 3
        acc = u32(acc + 7)
    return bytes(key), bytes(iv)

def _decrypt_s2(b64_data):
    try:
        ct = base64.b64decode(b64_data)
        key, iv = _gen_aes_key_iv_s2(APP_PASSWORD)
        cipher = AES.new(key, AES.MODE_CBC, iv)
        pt = cipher.decrypt(ct)
        pad_val = pt[-1]
        if 1 <= pad_val <= 16:
            pt = pt[:-pad_val]
        return pt.decode('utf-8', errors='replace')
    except Exception:
        return ""

def _get_api_url_s2():
    try:
        sess = requests.Session()
        sess.headers.update({"User-Agent": "Dalvik/2.1.0 (Linux; Android 13)", "Accept-Encoding": "gzip"})
        r = sess.post(
            f"https://firebaseinstallations.googleapis.com/v1/projects/{PROJECT_NUMBER}/installations",
            json={"fid": FIREBASE_FID, "appId": FIREBASE_APP_ID,
                  "authVersion": "FIS_v2", "sdkVersion": "a:18.0.0"},
            headers={"x-goog-api-key": FIREBASE_API_KEY}
        )
        auth_token = r.json()["authToken"]["token"]
        r2 = sess.post(
            f"https://firebaseremoteconfig.googleapis.com/v1/projects/{PROJECT_NUMBER}/namespaces/firebase:fetch",
            json={"appVersion": "2.5", "appInstanceId": FIREBASE_FID,
                  "appId": FIREBASE_APP_ID, "packageName": PACKAGE_NAME},
            headers={"X-Goog-Api-Key": FIREBASE_API_KEY,
                     "X-Goog-Firebase-Installations-Auth": auth_token}
        )
        return r2.json().get("entries", {}).get("api_url")
    except Exception:
        return None

def _fetch_parse_s2(url):
    try:
        sess = requests.Session()
        sess.headers.update({"User-Agent": "Dalvik/2.1.0 (Linux; Android 13)", "Accept-Encoding": "gzip"})
        r = sess.get(url, timeout=20)
        dec = _decrypt_s2(r.json().get("data", ""))
        return json.loads(dec) if dec else []
    except Exception:
        return []

def _decode_api_key_s2(api_val):
    if not api_val or len(api_val) < 20:
        return api_val
    try:
        decoded = base64.b64decode(api_val).decode('utf-8')
        if ":" in decoded and len(decoded) > 30:
            api_val = decoded
    except Exception:
        pass
    api_val = re.sub(r'[\u0010-\u001f]', lambda m: hex(ord(m.group()))[-1], api_val)
    correction_map = {
        'J':'a','$':'5','l':'2','Q':'b','W':'e','w':'4',')':'2','Z':'a',
        'x':'5','[':'d','U':'d','u':'2','S':'a','A':'a','D':'d','s':'0',
        'X':'a','y':'6','V':'d','v':'3','t':'1','z':'7',
    }
    for wrong, right in correction_map.items():
        api_val = api_val.replace(wrong, right)
    if ":" in api_val:
        prefix, suffix = api_val.split(":", 1)
        if len(suffix) > 24 and suffix[24] == '9':
            suffix = suffix[:24] + '0' + suffix[25:]
        api_val = prefix + ":" + suffix
    return api_val

def _clean_channel_s2(ch):
    title = ch.get("title", "")
    title = re.sub(r'S.?portz[xX]', 'SportzUP', title)
    title = re.sub(r'S.?P[xX]', 'SUP', title)
    ch["title"] = title
    api_val = ch.get("api", "")
    if api_val:
        ch["api"] = _decode_api_key_s2(api_val)
    return ch

def fetch_source2():
    """Fetch & decrypt events from Source 2 (SportzX/Firebase)."""
    print("📡 Source-2: Firebase API URL নেওয়া হচ্ছে...")
    api_url = _get_api_url_s2()
    if not api_url:
        print("  ❌ Source-2 API URL পাওয়া যায়নি")
        return []

    print(f"  🔗 API URL: {api_url}")
    base_api = api_url.rstrip('/')
    events = _fetch_parse_s2(f"{base_api}/events.json")
    if not isinstance(events, list) or not events:
        print("  ❌ Source-2 events পাওয়া যায়নি")
        return []

    total = len(events)
    for ev in events:
        ev.pop("formats", None)
        eid = str(ev.get("id", ""))
        if not eid:
            continue
        channels = _fetch_parse_s2(f"{base_api}/channels/{eid}.json")
        if not isinstance(channels, list):
            channels = []
        ev["channels_data"] = [_clean_channel_s2(ch) for ch in channels]
        ev["_source"] = "source2"

    print(f"  ✅ Source-2: {len(events)} events")
    return events


# =====================================================================
# NORMALIZER  →  combined format
# =====================================================================
def _parse_dt(date_str, time_str):
    """Parse 'DD/MM/YYYY' + 'HH:MM:SS' → datetime or None."""
    for fmt in ("%d/%m/%Y %H:%M:%S", "%Y/%m/%d %H:%M:%S %z"):
        try:
            return datetime.strptime(f"{date_str} {time_str}".strip(), fmt)
        except Exception:
            pass
    return None

def normalize_s1(ev):
    """Convert Source-1 event to combined format."""
    info = ev.get("eventInfo", {})
    start_raw = info.get("startTime", "")          # "2026/05/24 10:00:00 +0000"
    end_raw   = info.get("endTime",   "")

    # parse date/time from startTime
    date_str = time_str = end_date_str = end_time_str = ""
    try:
        dt = datetime.strptime(start_raw, "%Y/%m/%d %H:%M:%S +0000")
        date_str = dt.strftime("%d/%m/%Y")
        time_str = dt.strftime("%H:%M:%S")
    except Exception:
        pass
    try:
        dt2 = datetime.strptime(end_raw, "%Y/%m/%d %H:%M:%S +0000")
        end_date_str = dt2.strftime("%d/%m/%Y")
        end_time_str = dt2.strftime("%H:%M:%S")
    except Exception:
        pass

    # stream_links: list of dicts with {name, link, api}
    raw_links = ev.get("stream_links", [])
    stream_links = []
    if isinstance(raw_links, list):
        for item in raw_links:
            if isinstance(item, dict):
                stream_links.append({
                    "name":     item.get("name", item.get("title", "")),
                    "link":     item.get("link", ""),
                    "api":      item.get("api", ""),
                    "tokenApi": item.get("tokenApi", ""),
                    "scheme":   item.get("scheme", 0),
                })
            elif isinstance(item, str):
                stream_links.append({"name": "Link", "link": item, "api": "", "tokenApi": "", "scheme": 0})

    return {
        "visible":    info.get("publish", "1") == "1",
        "priority":   -1,
        "category":   ev.get("cat", ""),
        "eventName":  info.get("eventName", ev.get("title", "")),
        "eventLogo":  info.get("eventBanner", ""),
        "teamAName":  info.get("teamA", ""),
        "teamBName":  info.get("teamB", ""),
        "teamAFlag":  info.get("teamAFlag", ""),
        "teamBFlag":  info.get("teamBFlag", ""),
        "date":       date_str,
        "time":       time_str,
        "end_date":   end_date_str,
        "end_time":   end_time_str,
        "adsLimit":   ev.get("adsLimit", "0"),
        "stream_links": stream_links,
        "_source":    "source1",
        "_raw_id":    str(ev.get("id", "")),
    }

def normalize_s2(ev):
    """Convert Source-2 (SportzX) event to combined format."""
    info    = ev.get("eventInfo", {})
    start_raw = info.get("startTime", "")
    end_raw   = info.get("endTime",   "")

    date_str = time_str = end_date_str = end_time_str = ""
    try:
        dt = datetime.strptime(start_raw, "%Y/%m/%d %H:%M:%S +0000")
        date_str = dt.strftime("%d/%m/%Y")
        time_str = dt.strftime("%H:%M:%S")
    except Exception:
        pass
    try:
        dt2 = datetime.strptime(end_raw, "%Y/%m/%d %H:%M:%S +0000")
        end_date_str = dt2.strftime("%d/%m/%Y")
        end_time_str = dt2.strftime("%H:%M:%S")
    except Exception:
        pass

    # channels_data → stream_links
    channels = ev.get("channels_data", [])
    stream_links = []
    for ch in channels:
        stream_links.append({
            "name":     ch.get("title", ""),
            "link":     ch.get("link", ""),
            "api":      ch.get("api", ""),
            "tokenApi": "",
            "scheme":   int(ch.get("type", 0)),
        })

    return {
        "visible":    ev.get("publish", "1") == "1",
        "priority":   -1,
        "category":   ev.get("cat", ""),
        "eventName":  info.get("eventName", ev.get("title", "")),
        "eventLogo":  info.get("eventBanner", ""),
        "teamAName":  info.get("teamA", ""),
        "teamBName":  info.get("teamB", ""),
        "teamAFlag":  info.get("teamAFlag", ""),
        "teamBFlag":  info.get("teamBFlag", ""),
        "date":       date_str,
        "time":       time_str,
        "end_date":   end_date_str,
        "end_time":   end_time_str,
        "adsLimit":   ev.get("adsLimit", "0"),
        "stream_links": stream_links,
        "_source":    "source2",
        "_raw_id":    str(ev.get("id", "")),
    }


# =====================================================================
# DUPLICATE DETECTION
# =====================================================================
def _make_key(ev):
    """
    Duplicate key: normalize eventName + teamA + teamB + date.
    Both conditions must match (event name+date AND team names).
    """
    def norm(s):
        return re.sub(r'\s+', '', str(s).lower().strip())

    name  = norm(ev.get("eventName", ""))
    teamA = norm(ev.get("teamAName", ""))
    teamB = norm(ev.get("teamBName", ""))
    date  = norm(ev.get("date", ""))
    return f"{name}|{teamA}|{teamB}|{date}"

def merge_events(s1_events, s2_events):
    """
    Merge two lists. On duplicate (same key), prefer the event with MORE
    stream_links; if equal, prefer source2 (usually has DRM api keys).
    """
    seen = {}   # key → index in merged list
    merged = []

    def add_or_replace(ev):
        k = _make_key(ev)
        if k not in seen:
            seen[k] = len(merged)
            merged.append(ev)
        else:
            existing = merged[seen[k]]
            new_links = len(ev.get("stream_links", []))
            old_links = len(existing.get("stream_links", []))

            # Merge stream_links from both (deduplicate by name)
            combined_links = {l["name"]: l for l in existing.get("stream_links", [])}
            for l in ev.get("stream_links", []):
                if l["name"] not in combined_links:
                    combined_links[l["name"]] = l
                else:
                    # if new has api and old doesn't, prefer new
                    if l.get("api") and not combined_links[l["name"]].get("api"):
                        combined_links[l["name"]] = l

            base = existing if existing.get("_source") == "source2" else ev
            base = dict(base)
            base["stream_links"] = list(combined_links.values())
            merged[seen[k]] = base
            print(f"  🔄 Duplicate merged: {ev.get('eventName')} ({ev.get('date')}) — links: {old_links}+{new_links}→{len(base['stream_links'])}")

    # Source1 first
    for ev in s1_events:
        add_or_replace(ev)

    # Source2 second (may override/merge)
    for ev in s2_events:
        add_or_replace(ev)

    # Remove internal keys before upload
    for ev in merged:
        ev.pop("_source", None)
        ev.pop("_raw_id", None)

    return merged


# =====================================================================
# UPLOAD
# =====================================================================
def upload(data):
    if not RECEIVER_URL or not HOSTING_AUTH_TOKEN:
        print("❌ RECEIVER_URL বা HOSTING_AUTH_TOKEN সেট নেই!")
        return False
    print(f"\n🌐 {len(data)} events পাঠানো হচ্ছে → {RECEIVER_URL}")
    try:
        r = requests.post(
            RECEIVER_URL,
            json=data,
            headers={"Content-Type": "application/json",
                     "X-Auth-Token": HOSTING_AUTH_TOKEN},
            timeout=20
        )
        if r.status_code == 200:
            print("🚀 সফলভাবে হোস্টিং সার্ভারে আপলোড হয়েছে!")
            return True
        else:
            print(f"❌ আপলোড ব্যর্থ — HTTP {r.status_code}: {r.text[:200]}")
            return False
    except Exception as e:
        print(f"❌ আপলোড error: {e}")
        return False


# =====================================================================
# MAIN
# =====================================================================
def run():
    print("=" * 55)
    print("  SportsMerger — দুই সোর্স থেকে একটি ফাইল")
    print("=" * 55)

    s1_raw = fetch_source1()
    s2_raw = fetch_source2()

    print(f"\n🔀 Merging: Source1={len(s1_raw)}, Source2={len(s2_raw)}")
    s1_norm = [normalize_s1(e) for e in s1_raw]
    s2_norm = [normalize_s2(e) for e in s2_raw]

    final = merge_events(s1_norm, s2_norm)
    print(f"✅ Final merged events: {len(final)}")

    upload(final)


if __name__ == "__main__":
    run()
