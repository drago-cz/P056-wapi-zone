#!/usr/bin/env python3
import json
import hashlib
import requests
import sys
import urllib.parse
from pathlib import Path
from datetime import datetime, timezone

# ---------- Nastavení ----------
CONFIG_PATH = Path(__file__).parent / "config.json"
API_URL = "https://api.wedos.com/wapi/json"

# ---------- Načtení konfigurace ----------
def load_config():
    if not CONFIG_PATH.exists():
        print(f"Konfigurační soubor nenalezen: {CONFIG_PATH}")
        print(f"Vytvořte soubor {CONFIG_PATH} s uživatelským jménem a heslem.")
        print("Příklad:")
        print("""
        {
            "user": "admin@domain.tld",
            "password": "secretpassword"
        }
        """)
        sys.exit(1)
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

# ---------- Volání WAPI ----------
def call_wapi(user: str, password: str, command: str, data: dict = None,
              clTRID: str = "cli-001", test: bool = False):
    if data is None:
        data = {}

    # Generování auth
    hour = datetime.now(timezone.utc).astimezone().strftime("%H")
    hashed_pw = hashlib.sha1(password.encode("utf-8")).hexdigest()
    auth = hashlib.sha1((user + hashed_pw + hour).encode("utf-8")).hexdigest()

    # Sestavení request payload
    req = {
        "user": user,
        "auth": auth,
        "command": command,
        "clTRID": clTRID
    }
    if data:
        req["data"] = data
    if test:
        req["test"] = 1

    # Zabalit do obálky a URL-encode
    wrapper = {"request": req}
    json_str = json.dumps(wrapper, separators=(",", ":"))
    raw_body = "request=" + urllib.parse.quote(json_str)

    try:
        resp = requests.post(
            API_URL,
            data=raw_body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=10
        )
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        return {"error": str(e)}

# ---------- Akce v menu ----------
def test_connection(cfg):
    print("\n=== Test připojení k WAPI (ping) ===")
    result = call_wapi(cfg["user"], cfg["password"], "ping", clTRID="test-ping")
    print(json.dumps(result, indent=2, ensure_ascii=False))

def list_domains(cfg):
    print("\n=== Seznam domén ===")
    result = call_wapi(cfg["user"], cfg["password"], "domains-list", clTRID="list-domains")
    resp = result.get("response", {})
    print("\n-- RAW RESPONSE --")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    if resp.get("code") in (1000, "1000"):
        domain_dict = resp.get("data", {}).get("domain", {})
        if not domain_dict:
            print("Žádné domény nebyly nalezeny.")
            return
        header = f"{'Name':<30} {'Status':<10} {'Expiration':<12}"
        sep    = f"{'-'*30} {'-'*10} {'-'*12}"
        print("\n" + header)
        print(sep)
        for rec in domain_dict.values():
            print(f"{rec.get('name',''):<30} {rec.get('status',''):<10} {rec.get('expiration',''):<12}")
    else:
        print("Chyba při načítání domén:")

def list_dns_domains(cfg):
    print("\n=== Seznam DNS domén ===")
    result = call_wapi(cfg["user"], cfg["password"], "dns-domains-list", clTRID="list-dns-domains")
    resp = result.get("response", {})
    print("\n-- RAW RESPONSE --")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    if resp.get("code") in (1000, "1000"):
        dns_dict = resp.get("data", {}).get("domain", {})
        if not dns_dict:
            print("Žádné DNS domény nebyly nalezeny.")
            return
        header = f"{'Name':<30} {'Status':<10} {'Type':<10}"
        sep    = f"{'-'*30} {'-'*10} {'-'*10}"
        print("\n" + header)
        print(sep)
        for rec in dns_dict.values():
            print(f"{rec.get('name',''):<30} {rec.get('status',''):<10} {rec.get('type',''):<10}")
    else:
        print("Chyba při načítání DNS domén:")

def generate_zone_files(cfg):
    print("\n=== Generování zónových souborů ===")
    # 1) Získat seznam DNS domén
    result = call_wapi(cfg["user"], cfg["password"], "dns-domains-list", clTRID="gen-zone-dns-domains")
    resp = result.get("response", {})
    if resp.get("code") not in (1000, "1000"):
        print("Chyba při načítání DNS domén:")
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return
    dns_dict = resp.get("data", {}).get("domain", {})
    if not dns_dict:
        print("Žádné DNS domény nebyly nalezeny.")
        return

    zone_dir = Path("zone")
    zone_dir.mkdir(exist_ok=True)

    for rec in dns_dict.values():
        domain_name = rec.get("name")
        if not domain_name:
            continue
        # 2) Načíst záznamy pro danou doménu
        row_result = call_wapi(
            cfg["user"], cfg["password"],
            "dns-rows-list",
            data={"domain": domain_name},
            clTRID=f"rows-{domain_name}"
        )
        row_resp = row_result.get("response", {})
        if row_resp.get("code") not in (1000, "1000"):
            print(f"Chyba u dns-rows-list pro {domain_name}:")
            print(json.dumps(row_result, indent=2, ensure_ascii=False))
            continue

        row_data = row_resp.get("data", {}).get("row", {})
        # Podpora obou případů: dict i list
        if isinstance(row_data, dict):
            rows = row_data.values()
        elif isinstance(row_data, list):
            rows = row_data
        else:
            print(f"Neočekávaný formát dat pro {domain_name}: {type(row_data)}")
            continue

        if not rows:
            print(f"Žádné záznamy pro DNS-doménu {domain_name}.")
            continue

        # 3) Vygenerovat soubor
        zone_path = zone_dir / f"{domain_name}.zone"
        with open(zone_path, "w", encoding="utf-8") as f:
            f.write(f"$ORIGIN {domain_name}.\n")
            f.write("$TTL 3600\n\n")
            for row in rows:
                name   = row.get("name") or "@"
                ttl    = row.get("ttl") or ""
                rdtype = row.get("rdtype") or ""
                rdata  = row.get("rdata") or ""
                f.write(f"{name}\t{ttl}\tIN\t{rdtype}\t{rdata}\n")
        print(f"Vygenerován soubor: {zone_path}")


# ---------- Menu ----------
def show_menu():
    print("""
Vyber možnost:
  1) Otestovat připojení k WAPI
  2) Zobrazit seznam všech domén
  3) Zobrazit seznam DNS domén
  4) Generovat zónové soubory pro všechny DNS domény
  0) Konec
""")

def main():
    cfg = load_config()
    while True:
        show_menu()
        choice = input(">> ").strip()
        if choice == "1":
            test_connection(cfg)
        elif choice == "2":
            list_domains(cfg)
        elif choice == "3":
            list_dns_domains(cfg)
        elif choice == "4":
            generate_zone_files(cfg)
        elif choice == "0":
            print("Konec.")
            break
        else:
            print("Neplatná volba, zkuste znovu.")

if __name__ == "__main__":
    main()
