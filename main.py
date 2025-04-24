#!/usr/bin/env python3
import json
import hashlib
import requests
import sys
import urllib.parse
import csv
from pathlib import Path
from datetime import datetime, timezone

# ---------- Nastavení ----------
CONFIG_PATH = Path(__file__).parent / "config.json"
API_URL     = "https://api.wedos.com/wapi/json"
ZONE_DIR    = Path(__file__).parent / "zone"

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
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))

# ---------- Volání WAPI ----------
def call_wapi(user: str, password: str, command: str, data: dict = None,
              clTRID: str = "cli-001", test: bool = False):
    if data is None:
        data = {}
    hour     = datetime.now(timezone.utc).astimezone().strftime("%H")
    hashed_pw = hashlib.sha1(password.encode("utf-8")).hexdigest()
    auth     = hashlib.sha1((user + hashed_pw + hour).encode("utf-8")).hexdigest()
    req = {
        "user":    user,
        "auth":    auth,
        "command": command,
        "clTRID":  clTRID
    }
    if data: req["data"] = data
    if test: req["test"] = 1
    wrapper  = {"request": req}
    json_str = json.dumps(wrapper, separators=(",", ":"))
    raw_body = "request=" + urllib.parse.quote(json_str)
    try:
        r = requests.post(API_URL,
                          data=raw_body,
                          headers={"Content-Type": "application/x-www-form-urlencoded"},
                          timeout=10)
        r.raise_for_status()
        return r.json()
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
    ZONE_DIR.mkdir(exist_ok=True)
    for rec in dns_dict.values():
        domain_name = rec.get("name")
        if not domain_name: continue
        row_result = call_wapi(cfg["user"], cfg["password"], "dns-rows-list",
                               data={"domain": domain_name},
                               clTRID=f"rows-{domain_name}")
        row_resp = row_result.get("response", {})
        if row_resp.get("code") not in (1000, "1000"):
            print(f"Chyba u dns-rows-list pro {domain_name}:")
            print(json.dumps(row_result, indent=2, ensure_ascii=False))
            continue
        row_data = row_resp.get("data", {}).get("row", {})
        rows = row_data.values() if isinstance(row_data, dict) else row_data
        if not rows:
            print(f"Žádné záznamy pro DNS-doménu {domain_name}.")
            continue
        zone_path = ZONE_DIR / f"{domain_name}.zone"
        with open(zone_path, "w", encoding="utf-8") as f:
            f.write(f"$ORIGIN {domain_name}.\n$TTL 3600\n\n")
            for row in rows:
                name   = row.get("name") or "@"
                ttl    = row.get("ttl") or ""
                rdtype = row.get("rdtype") or ""
                rdata  = row.get("rdata") or ""
                f.write(f"{name}\t{ttl}\tIN\t{rdtype}\t{rdata}\n")
        print(f"Vygenerován soubor: {zone_path}")

def compare_zone_ns(cfg):
    print("\n=== Porovnání všech DNS záznamů z zone/ vs WAPI ===")
    if not ZONE_DIR.exists():
        print(f"Složka {ZONE_DIR} neexistuje.")
        return

    results = []
    for path in sorted(ZONE_DIR.iterdir()):
        if path.suffix != ".zone":
            print(f"Ignorován soubor: {path.name}")
            continue

        domain = path.stem

        # 1) Načti všechny záznamy z lokálního zone souboru
        zone_records = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("$") or line.startswith(";"):
                continue
            parts = line.split()
            # očekáváme: name, ttl, class(IN), type, rdata...
            if len(parts) >= 5 and parts[2].upper() == "IN":
                name  = parts[0]
                ttl   = parts[1]
                rtype = parts[3]
                rdata = " ".join(parts[4:]).rstrip(".")
                zone_records.append((name, ttl, rtype, rdata))
        print(f"Soubor {path.name} – načteno záznamů: {len(zone_records)}")

        # 2) Načti všechny záznamy z WAPI (dns-rows-list)
        wapi_resp = call_wapi(
            cfg["user"], cfg["password"],
            "dns-rows-list",
            data={"domain": domain},
            clTRID=f"cmp-{domain}"
        )
        resp = wapi_resp.get("response", {})
        if resp.get("code") not in (1000, "1000"):
            print(f"Chyba WAPI u {domain}: {resp.get('result')}")
            continue

        data_field = resp.get("data", {})
        # pokud je pod 'row', použij to; jinak data_field samo
        raw_rows = data_field.get("row", data_field)
        if isinstance(raw_rows, dict):
            rows = raw_rows.values()
        elif isinstance(raw_rows, list):
            rows = raw_rows
        else:
            rows = []

        wapi_records = []
        for r in rows:
            if not isinstance(r, dict):
                continue
            # normalize root name to '@'
            name  = r.get("name") or "@"
            ttl   = str(r.get("ttl", ""))
            rtype = r.get("rdtype", "")
            rdata = r.get("rdata", "").rstrip(".")
            wapi_records.append((name, ttl, rtype, rdata))
        print(f"WAPI {domain} – načteno záznamů: {len(wapi_records)}")

        # 3) Porovnej obě množiny
        set_zone = set(zone_records)
        set_wapi = set(wapi_records)
        all_recs = sorted(set_zone | set_wapi)
        for name, ttl, rtype, rdata in all_recs:
            if (name, ttl, rtype, rdata) in set_zone and (name, ttl, rtype, rdata) in set_wapi:
                status, note = "shodný", ""
            elif (name, ttl, rtype, rdata) in set_zone:
                status, note = "chybí", "chybí v WAPI"
            else:
                status, note = "rozdíl", "chybí v zone souboru"
            results.append({
                "domain": domain,
                "name":   name,
                "ttl":    ttl,
                "type":   rtype,
                "rdata":  rdata,
                "status": status,
                "note":   note
            })

    # 4) Výpis výsledné tabulky
    header = f"{'Domain':<25} {'Name':<15} {'TTL':<6} {'Type':<7} {'Rdata':<30} {'Status':<10} {'Poznámka'}"
    sep    = f"{'-'*25} {'-'*15} {'-'*6} {'-'*7} {'-'*30} {'-'*10} {'-'*20}"
    print("\n" + header)
    print(sep)
    for r in results:
        print(f"{r['domain']:<25} {r['name']:<15} {r['ttl']:<6} {r['type']:<7} {r['rdata']:<30} {r['status']:<10} {r['note']}")

    # 5) Uložení do CSV
    csv_path = Path("zone_ns_comparison.csv")
    with open(csv_path, "w", newline="", encoding="utf-8") as csvfile:
        fieldnames = ["domain","name","ttl","type","rdata","status","note"]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)
    print(f"\nCSV uloženo: {csv_path}")

def sync_zone_records(cfg):
    print("\n=== Přidej/Oprav záznamy ze zone/ do WAPI ===")
    # 1) Zkontroluj, že mám složku s .zone soubory
    if not ZONE_DIR.exists():
        print(f"Složka {ZONE_DIR} neexistuje.")
        return

    # 2) Nejprve zjisti, které domény už jsou v DNS (dns-domains-list)
    resp = call_wapi(cfg["user"], cfg["password"], "dns-domains-list", clTRID="sync-domains-list")
    dns_domains = set()
    if resp.get("response", {}).get("code") == "1000":
        for rec in resp["response"]["data"].values():
            dns_domains.add(rec["name"])

    # 3) Pro každou .zone soubor
    for path in sorted(ZONE_DIR.iterdir()):
        if path.suffix != ".zone":
            print(f"Ignorován soubor: {path.name}")
            continue

        domain = path.stem
        print(f"\n--- Zpracovávám doménu {domain} ---")

        # 4) Načti lokální záznamy
        zone_map = {}
        for line in path.read_text(encoding="utf-8").splitlines():
            parts = line.strip().split()
            if len(parts) >= 5 and parts[2].upper() == "IN":
                name, ttl, _, rtype = parts[0], parts[1], parts[2], parts[3]
                rdata = " ".join(parts[4:]).rstrip(".")
                key = (name or "@", rtype)
                zone_map[key] = (ttl, rdata)
        print(f" Lokálně: {len(zone_map)} záznamů")

        # 5) Pokud doména není v DNS, přidej ji
        if domain not in dns_domains:
            print(f" Přidávám doménu {domain}")
            call_wapi(cfg["user"], cfg["password"], "dns-domain-add",
                      data={"name": domain},
                      clTRID=f"add-domain-{domain}")

        # 6) Načti WAPI záznamy (dns-rows-list)
        row_resp = call_wapi(cfg["user"], cfg["password"],
                             "dns-rows-list",
                             data={"domain": domain},
                             clTRID=f"sync-rows-{domain}")
        rcode = row_resp.get("response", {}).get("code")
        if rcode not in ("1000", 1000):
            print(f" Chyba při načítání záznamů WAPI: {row_resp}")
            continue

        data_field = row_resp["response"]["data"]
        raw = data_field.get("row", data_field)
        if isinstance(raw, dict):
            rows = raw.values()
        elif isinstance(raw, list):
            rows = raw
        else:
            rows = []

        # 7) Sestav mapu WAPI: key=(name,type)->(row_id, ttl, rdata)
        wapi_map = {}
        for r in rows:
            name = r.get("name") or "@"
            rtype = r.get("rdtype", "")
            row_id = r.get("ID")
            ttl = str(r.get("ttl", ""))
            rdata = r.get("rdata", "").rstrip(".")
            wapi_map[(name, rtype)] = (row_id, ttl, rdata)
        print(f" WAPI: {len(wapi_map)} záznamů")

        # 8) Přidání nebo aktualizace lokálních záznamů
        for key, (z_ttl, z_rdata) in zone_map.items():
            name, rtype = key
            if key not in wapi_map:
                print(f" Přidávám záznam {name} {rtype}")
                call_wapi(cfg["user"], cfg["password"], "dns-row-add",
                          data={"domain": domain,
                                "name": name,
                                "ttl": z_ttl,
                                "type": rtype,
                                "rdata": z_rdata},
                          clTRID=f"add-row-{domain}-{name}")
            else:
                row_id, w_ttl, w_rdata = wapi_map[key]
                if z_ttl != w_ttl or z_rdata != w_rdata:
                    print(f" Aktualizuji záznam {name} {rtype}")
                    call_wapi(cfg["user"], cfg["password"], "dns-row-update",
                              data={"domain": domain,
                                    "row_id": row_id,
                                    "ttl": z_ttl,
                                    "rdata": z_rdata},
                              clTRID=f"upd-row-{domain}-{name}")

        # 9) Smazání nadbytečných záznamů ve WAPI
        for key, (row_id, _, _) in wapi_map.items():
            if key not in zone_map:
                name, rtype = key
                print(f" Mažu záznam {name} {rtype}")
                """
                call_wapi(cfg["user"], cfg["password"], "dns-row-delete",
                          data={"domain": domain, "row_id": row_id},
                          clTRID=f"del-row-{domain}-{name}")
                """
    print("\nSynchronizace dokončena.")


# ---------- Menu ----------
def show_menu():
    print("""
Vyber možnost:
  1) Otestovat připojení k WAPI
  2) Zobrazit seznam všech domén
  3) Zobrazit seznam DNS domén
  4) Generovat zónové soubory pro všechny DNS domény
  5) Porovnat NS zónové soubory (zone/) s WAPI
  6) Přidej/Oprav záznamy ze zone/
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
        elif choice == "5":
            compare_zone_ns(cfg)
        elif choice == "6":
            sync_zone_records(cfg)     
        elif choice == "0":
            print("Konec.")
            break
        else:
            print("Neplatná volba, zkuste znovu.")

if __name__ == "__main__":
    main()
