import os
import re
import html
import socket
import ssl
import time
import json
import requests
import base64
import websocket
import shutil
from datetime import datetime
from urllib.parse import quote, unquote
from concurrent.futures import ThreadPoolExecutor

# ------------------ Настройки ------------------
BASE_DIR = "checked"
FOLDER_RU = os.path.join(BASE_DIR, "RU_Best")
FOLDER_WORLD = os.path.join(BASE_DIR, "World_Mix")

# Создаем папки если нет
os.makedirs(FOLDER_RU, exist_ok=True)
os.makedirs(FOLDER_WORLD, exist_ok=True)

TIMEOUT = 2           # Таймаут (сек)
THREADS = 50          # Потоков
CACHE_HOURS = 12      # Кэш
CHUNK_LIMIT = 500     # Ключей в файле

HISTORY_FILE = os.path.join(BASE_DIR, "history.json")
MY_CHANNEL = "@vlesstrojan" 

URLS = [
    "https://raw.githubusercontent.com/kort0881/vpn-vless-configs-russia/main/githubmirror/new/all_new.txt",
    "https://raw.githubusercontent.com/zieng2/wl/main/vless.txt",
    "https://raw.githubusercontent.com/LowiKLive/BypassWhitelistRu/refs/heads/main/WhiteList-Bypass_Ru.txt",
    "https://raw.githubusercontent.com/zieng2/wl/main/vless_universal.txt",
    "https://raw.githubusercontent.com/vsevjik/OBSpiskov/refs/heads/main/wwh",
    "https://jsnegsukavsos.hb.ru-msk.vkcloud-storage.ru/love",
    "https://etoneya.a9fm.site/1",
    "https://s3c3.001.gpucloud.ru/vahe4xkwi/cjdr"
]

# ------------------ Функции ------------------

def is_elite_ru(key, latency):
    """ЭЛИТА для РФ: < 400мс + Reality/SS-2022"""
    if latency > 400: return False
    key = key.lower()
    if "security=reality" in key and "pbk=" in key: return True
    if key.startswith("ss://") and "2022" in key: return True
    return False

def is_good_ru(key, latency):
    """Просто ХОРОШИЕ для РФ: < 1000мс + WS/TLS"""
    if latency > 1000: return False
    key = key.lower()
    if "security=reality" in key: return True
    if key.startswith("ss://"): return True
    if ("type=ws" in key or "net=ws" in key) and ":443" in key and ("sni=" in key or "host=" in key): return True
    return False

def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f: return json.load(f)
        except: pass
    return {}

def save_history(history):
    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f: json.dump(history, f, ensure_ascii=False, indent=2)
    except: pass

def fetch_and_load_keys(urls):
    all_keys = set()
    print(f"Загрузка источников...")
    for url in urls:
        try:
            headers = {'User-Agent': 'Mozilla/5.0'}
            resp = requests.get(url, headers=headers, timeout=10)
            if resp.status_code != 200: continue
            content = resp.text.strip()
            if "://" not in content:
                try:
                    decoded = base64.b64decode(content + "==").decode('utf-8', errors='ignore')
                    lines = decoded.splitlines()
                except: lines = content.splitlines()
            else: lines = content.splitlines()
            for line in lines:
                line = line.strip()
                if line.startswith(("vless://", "vmess://", "trojan://", "ss://")): all_keys.add(line)
        except: pass
    return list(all_keys)

def check_single_key(key):
    try:
        if "@" in key and ":" in key:
            part = key.split("@")[1].split("?")[0].split("#")[0]
            host, port = part.split(":")[0], int(part.split(":")[1])
        else: return None
        is_tls = 'security=tls' in key or 'security=reality' in key or 'trojan://' in key or 'vmess://' in key
        is_ws = 'type=ws' in key or 'net=ws' in key
        path = "/"
        match = re.search(r'path=([^&]+)', key)
        if match: path = unquote(match.group(1))
        start = time.time()
        if is_ws:
            protocol = "wss" if is_tls else "ws"
            ws_url = f"{protocol}://{host}:{port}{path}"
            ws = websocket.create_connection(ws_url, timeout=TIMEOUT, sslopt={"cert_reqs": ssl.CERT_NONE})
            ws.close()
        elif is_tls:
            context = ssl.create_default_context()
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
            with socket.create_connection((host, port), timeout=TIMEOUT) as sock:
                with context.wrap_socket(sock, server_hostname=host): pass
        else:
            with socket.create_connection((host, port), timeout=TIMEOUT): pass
        return int((time.time() - start) * 1000)
    except: return None

def save_chunked(keys_list, folder, base_name, limit=CHUNK_LIMIT):
    """Сохраняет в папку folder с именем base_name_partX.txt"""
    if not keys_list: return
    
    # Очистка старых файлов с таким именем в этой папке
    for f in os.listdir(folder):
        if f.startswith(base_name) and f.endswith(".txt"):
            try: os.remove(os.path.join(folder, f))
            except: pass

    total = len(keys_list)
    chunks = [keys_list[i:i + limit] for i in range(0, total, limit)]
    
    for i, chunk in enumerate(chunks, 1):
        if len(chunks) == 1: fname = f"{base_name}.txt"
        else: fname = f"{base_name}_part{i}.txt"
        full_path = os.path.join(folder, fname)
        with open(full_path, "w", encoding="utf-8") as f:
            f.write("\n".join(chunk))
        print(f"Saved {full_path} ({len(chunk)})")

# ------------------ Main Logic ------------------
if __name__ == "__main__":
    print(f"=== CHECKER v4 (For kort0881/vpn-checker-backend) ===")
    
    history = load_history()
    keys_raw = fetch_and_load_keys(URLS)
    print(f"Всего ключей: {len(keys_raw)}")
    
    to_check = []
    results = []
    current_time = time.time()
    
    # Кэш
    for k in keys_raw:
        k = html.unescape(k).strip()
        if not k: continue
        k_id = k.split("#")[0]
        cached = history.get(k_id)
        if cached and (current_time - cached['time'] < CACHE_HOURS * 3600) and cached['alive']:
            latency = cached['latency']
            tag = f"cached_{latency}ms_{MY_CHANNEL}"
            base = k.split("#")[0]
            if base: results.append((latency, f"{base}#{tag}"))
        else:
            to_check.append(k)

    print(f"Из кэша: {len(results)} | На проверку: {len(to_check)}")

    # Проверка
    new_history_updates = {}
    if to_check:
        with ThreadPoolExecutor(max_workers=THREADS) as executor:
            future_to_key = {executor.submit(check_single_key, k): k for k in to_check}
            for i, future in enumerate(future_to_key):
                key = future_to_key[future]
                latency = future.result()
                k_id = key.split("#")[0]
                new_history_updates[k_id] = {'alive': latency is not None, 'latency': latency, 'time': current_time}
                if latency is not None:
                    qual = "fast" if latency < 500 else "normal"
                    tag = f"{qual}_{latency}ms_{MY_CHANNEL}"
                    base = key.split("#")[0]
                    if base: results.append((latency, f"{base}#{tag}"))
                if i % 200 == 0: print(f"Checked {i}...")

    # История
    history.update(new_history_updates)
    clean_hist = {k:v for k,v in history.items() if current_time - v['time'] < 259200}
    save_history(clean_hist)

    # === СОРТИРОВКА И РАСКЛАДКА ===
    results.sort(key=lambda x: x[0]) 
    
    ru_elite = []
    ru_normal = []
    world_fast = []
    world_slow = []
    
    for latency, key_str in results:
        if is_good_ru(key_str, latency):
            if is_elite_ru(key_str, latency):
                ru_elite.append(key_str)
            else:
                ru_normal.append(key_str)
        else:
            if latency < 800:
                world_fast.append(key_str)
            else:
                world_slow.append(key_str)

    print(f"RU Elite: {len(ru_elite)} | RU Normal: {len(ru_normal)}")
    print(f"World Fast: {len(world_fast)} | World Slow: {len(world_slow)}")

    # ЗАПИСЬ
    save_chunked(ru_elite, FOLDER_RU, "ru_elite")
    save_chunked(ru_normal, FOLDER_RU, "ru_normal")
    save_chunked(world_fast, FOLDER_WORLD, "world_fast")
    save_chunked(world_slow, FOLDER_WORLD, "world_slow")

    # === ГЕНЕРАЦИЯ СПИСКА ПОДПИСОК ===
    GITHUB_USER_REPO = "kort0881/vpn-checker-backend"
    BRANCH = "main" 
    
    BASE_URL = f"https://raw.githubusercontent.com/{GITHUB_USER_REPO}/{BRANCH}/{BASE_DIR}"
    
    subs_lines = []
    subs_lines.append("=== 🇷🇺 RUSSIA SUBSCRIPTIONS ===")
    subs_lines.append(f"⭐️ Elite (Reality/SS Fast): {BASE_URL}/RU_Best/ru_elite.txt")
    # Добавляем части, если они были созданы
    if len(ru_elite) > CHUNK_LIMIT:
         subs_lines.append(f"   Elite Part 2: {BASE_URL}/RU_Best/ru_elite_part2.txt")

    subs_lines.append(f"✅ Normal (Reserve): {BASE_URL}/RU_Best/ru_normal.txt")
    
    subs_lines.append("\n=== 🌍 WORLD SUBSCRIPTIONS ===")
    subs_lines.append(f"⚡️ Fast Mix: {BASE_URL}/World_Mix/world_fast.txt")
    subs_lines.append(f"🐢 Slow/Reserve: {BASE_URL}/World_Mix/world_slow.txt")
    
    SUBS_FILE = os.path.join(BASE_DIR, "subscriptions_list.txt")
    with open(SUBS_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(subs_lines))

    print("=== FINISHED ===")
    print(f"Links generated in: {SUBS_FILE}")













