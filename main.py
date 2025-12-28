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
from datetime import datetime
from urllib.parse import quote, unquote
from concurrent.futures import ThreadPoolExecutor

# ------------------ Настройки ------------------
NEW_KEYS_FOLDER = "checked"
os.makedirs(NEW_KEYS_FOLDER, exist_ok=True)

TIMEOUT = 2           # Таймаут (сек)
THREADS = 50          # Потоков
CACHE_HOURS = 12      # Время жизни кэша (часы)
CHUNK_LIMIT = 500     # Ключей в одном файле

# Базовые имена файлов (к ним добавится _part1.txt и т.д.)
FILE_RU = os.path.join(NEW_KEYS_FOLDER, "russia_bypass.txt")
FILE_ALL = os.path.join(NEW_KEYS_FOLDER, "all_world.txt")

HISTORY_FILE = os.path.join(NEW_KEYS_FOLDER, "history.json")
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

def is_good_for_russia(key):
    """Фильтр для РФ: Reality, WS, SS, Trojan-443"""
    key = key.lower()
    if "security=reality" in key and "pbk=" in key: return True
    if "type=ws" in key or "net=ws" in key: return True
    if key.startswith("ss://"): return True
    if key.startswith("trojan://") and ":443" in key: return True
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
            # Попытка декодировать Base64, если это не список ссылок
            if "://" not in content:
                try:
                    decoded = base64.b64decode(content + "==").decode('utf-8', errors='ignore')
                    lines = decoded.splitlines()
                except: lines = content.splitlines()
            else:
                lines = content.splitlines()

            for line in lines:
                line = line.strip()
                if line.startswith(("vless://", "vmess://", "trojan://", "ss://")):
                    all_keys.add(line)
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
        
        # 1. WebSocket Check
        if is_ws:
            protocol = "wss" if is_tls else "ws"
            ws_url = f"{protocol}://{host}:{port}{path}"
            ws = websocket.create_connection(ws_url, timeout=TIMEOUT, sslopt={"cert_reqs": ssl.CERT_NONE})
            ws.close()
        # 2. TLS Check
        elif is_tls:
            context = ssl.create_default_context()
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
            with socket.create_connection((host, port), timeout=TIMEOUT) as sock:
                with context.wrap_socket(sock, server_hostname=host): pass
        # 3. TCP Check
        else:
            with socket.create_connection((host, port), timeout=TIMEOUT): pass
            
        return int((time.time() - start) * 1000)
    except:
        return None

def save_chunked(keys_list, base_filename, limit=CHUNK_LIMIT):
    """Сохраняет список в файлы part1, part2..."""
    total = len(keys_list)
    if total == 0: return

    # Если меньше лимита - один файл (без _part1)
    if total <= limit:
        with open(base_filename, "w", encoding="utf-8") as f:
            f.write("\n".join(keys_list))
        print(f"Saved {base_filename} ({total})")
        return

    # Если больше - разбиваем
    name_part, ext = os.path.splitext(base_filename)
    chunks = [keys_list[i:i + limit] for i in range(0, total, limit)]
    
    for i, chunk in enumerate(chunks, 1):
        chunk_name = f"{name_part}_part{i}{ext}"
        with open(chunk_name, "w", encoding="utf-8") as f:
            f.write("\n".join(chunk))
        print(f"Saved {chunk_name} ({len(chunk)})")

# ------------------ Main Logic ------------------
if __name__ == "__main__":
    print(f"=== CHECKER START (Threads: {THREADS}) ===")
    
    # 1. Загрузка
    history = load_history()
    keys_raw = fetch_and_load_keys(URLS)
    print(f"Всего ключей: {len(keys_raw)}")
    
    to_check = []
    results = []
    current_time = time.time()
    
    # 2. Проверка кэша
    for k in keys_raw:
        k = html.unescape(k).strip()
        if not k: continue
        
        k_id = k.split("#")[0]
        cached = history.get(k_id)
        
        # Если в кэше и свежий
        if cached and (current_time - cached['time'] < CACHE_HOURS * 3600) and cached['alive']:
            latency = cached['latency']
            tag = f"cached_{latency}ms_{MY_CHANNEL}"
            base = k.split("#")[0]
            if not base: continue
            results.append((latency, f"{base}#{tag}"))
        else:
            to_check.append(k)

    print(f"Из кэша: {len(results)}")
    print(f"На проверку: {len(to_check)}")

    # 3. Многопоточная проверка
    new_history_updates = {}
    if to_check:
        with ThreadPoolExecutor(max_workers=THREADS) as executor:
            future_to_key = {executor.submit(check_single_key, k): k for k in to_check}
            
            for i, future in enumerate(future_to_key):
                key = future_to_key[future]
                latency = future.result()
                
                k_id = key.split("#")[0]
                new_history_updates[k_id] = {
                    'alive': latency is not None,
                    'latency': latency,
                    'time': current_time
                }

                if latency is not None:
                    qual = "fast" if latency < 500 else "normal"
                    tag = f"{qual}_{latency}ms_{MY_CHANNEL}"
                    base = key.split("#")[0]
                    if base:
                        results.append((latency, f"{base}#{tag}"))
                
                if i % 200 == 0: print(f"Checked {i}...")

    # 4. Обновление истории
    history.update(new_history_updates)
    # Удаляем старые записи (>3 дней)
    clean_hist = {k:v for k,v in history.items() if current_time - v['time'] < 259200}
    save_history(clean_hist)

    # 5. Сортировка и Сохранение
    results.sort(key=lambda x: x[0]) # По пингу
    
    ru_keys = []
    other_keys = []
    
    for _, key_str in results:
        if is_good_for_russia(key_str):
            ru_keys.append(key_str)
        else:
            other_keys.append(key_str)

    print(f"Valid RU: {len(ru_keys)} | Valid World: {len(other_keys)}")

    # ОЧИСТКА ПАПКИ (Удаляем старые txt)
    for f in os.listdir(NEW_KEYS_FOLDER):
        if f.endswith(".txt"):
            try: os.remove(os.path.join(NEW_KEYS_FOLDER, f))
            except: pass

    # ЗАПИСЬ
    save_chunked(ru_keys, FILE_RU, limit=CHUNK_LIMIT)
    save_chunked(other_keys, FILE_ALL, limit=CHUNK_LIMIT)

    print("=== FINISHED ===")












