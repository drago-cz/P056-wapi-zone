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


# Check if ZONE_DIR exists, create if it doesn't
if not ZONE_DIR.exists():
    ZONE_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Directory '{ZONE_DIR}' has been created. We will use it to store zone files.")

# ---------- Načtení konfigurace ----------
def load_config():
    if not CONFIG_PATH.exists():
        print(f"Configuration file {CONFIG_PATH} not found.")
        print(f"Create a {CONFIG_PATH} file with a username and password.")
        print("Example:")
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
              clTRID: str = "wapi-zone", test: bool = False):
    if data is None:
        data = {}
    hour        = datetime.now(timezone.utc).astimezone().strftime("%H")
    hashed_pw   = hashlib.sha1(password.encode("utf-8")).hexdigest()
    auth        = hashlib.sha1((user + hashed_pw + hour).encode("utf-8")).hexdigest()
    # základní JSON-objekt požadavku
    req = {
        "user":    user,
        "auth":    auth,
        "command": command,
        "clTRID":  clTRID
    }
    if data: req["data"] = data # Přidáme klíč "data", jen pokud je slovník data neprázdný
    if test: req["test"] = 1 # Přidáme klíč "test": 1, pokud byl test=True, čímž signalizujeme WAPI, že má příkaz jen zkontrolovat
    # API očekává, že celý obsah pošleme jako hodnotu klíče "request".
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

# ---------- Helper to parse zone files in both formats ----------
def parse_zone_file(path: Path):
    """
    Read a .zone file and return a list of tuples:
      (name, ttl, rtype, rdata)
    Supports both:
      - full-FQDN + inline TTL
      - $ORIGIN/$TTL directives + relative names (@, www, *)
    """
    origin = path.stem  # fallback if no $ORIGIN directive
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith(';'):
            continue

        # capture a $ORIGIN directive, if present
        if line.upper().startswith('$ORIGIN'):
            parts = line.split()
            if len(parts) >= 2:
                origin = parts[1].rstrip('.')
            continue

        # skip TTL directive lines
        if line.upper().startswith('$TTL'):
            continue

        parts = line.split()
        # expect: name, ttl, class(IN), type, rdata...
        if len(parts) < 5 or parts[2].upper() != 'IN':
            continue

        raw_name, ttl, _, rtype = parts[0], parts[1], parts[2], parts[3]
        rdata = " ".join(parts[4:]).rstrip('.')

        # normalize record name
        if raw_name == '@':
            name = '@'
        elif raw_name.endswith('.'):
            bare = raw_name.rstrip('.')
            if bare == origin:
                name = '@'
            elif bare.endswith('.' + origin):
                name = bare[:-(len(origin) + 1)]
            else:
                name = bare
        else:
            name = raw_name

        records.append((name, ttl, rtype, rdata))
    return records


# ---------- Akce v menu ----------
def test_connection(cfg):
    print("\n=== Do a WAPI connection test (ping) ===")
    result = call_wapi(cfg["user"], cfg["password"], "ping", clTRID="test-ping")
    print(json.dumps(result, indent=2, ensure_ascii=False))

def list_domains(cfg):
    print("\n=== List of domains ===")
    result = call_wapi(cfg["user"], cfg["password"], "domains-list", clTRID="list-domains")
    resp = result.get("response", {})
    print("\n-- RAW RESPONSE --")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    # Pokud je kód 1000 - OK, pak je vše v pořádku
    if resp.get("code") in (1000, "1000"):
        domain_dict = resp.get("data", {}).get("domain", {})
        if not domain_dict:
            print("No domains were found.")
            return
        header = f"{'Name':<30} {'Status':<10} {'Expiration':<12}"
        sep    = f"{'-'*30} {'-'*10} {'-'*12}"
        print("\n" + header)
        print(sep)
        for rec in domain_dict.values():
            print(f"{rec.get('name',''):<30} {rec.get('status',''):<10} {rec.get('expiration',''):<12}")
    else:
        print("An error occurred when loading the list of domains via WAPI:")

def list_dns_domains(cfg):
    print("\n=== DNS list for domains ===")
    result = call_wapi(cfg["user"], cfg["password"], "dns-domains-list", clTRID="list-dns-domains")
    resp = result.get("response", {})
    print("\n-- RAW RESPONSE --")
    print(json.dumps(result, indent=2, ensure_ascii=False))

    if resp.get("code") not in (1000, "1000"):
        print("Error loading DNS list for domains:")
        return

    # Handle both dict and list for the 'domain' field
    raw = resp.get("data", {}).get("domain", [])
    domains = raw.values() if isinstance(raw, dict) else raw

    if not domains:
        print("No DNS domains were found.")
        return

    header = f"{'Name':<30} {'Status':<10} {'Type':<10}"
    sep    = f"{'-'*30} {'-'*10} {'-'*10}"
    print("\n" + header)
    print(sep)
    for rec in domains:
        name   = rec.get("name","")
        status = rec.get("status","")
        dtype  = rec.get("type","")
        print(f"{name:<30} {status:<10} {dtype:<10}")


def generate_zone_files(cfg):
    print("\n=== Generate zone files ===")
    result = call_wapi(cfg["user"], cfg["password"], "dns-domains-list", clTRID="gen-zone-dns-domains")
    resp = result.get("response", {})
    if resp.get("code") not in (1000, "1000"):
        print("Error loading DNS list for domains:")
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return

    # Handle both dict and list responses
    raw = resp.get("data", {}).get("domain", [])
    domains = raw.values() if isinstance(raw, dict) else raw

    if not domains:
        print("No DNS domains were found.")
        return

    ZONE_DIR.mkdir(exist_ok=True)

    for rec in domains:
        domain_name = rec.get("name")
        if not domain_name:
            continue

        row_result = call_wapi(
            cfg["user"], cfg["password"],
            "dns-rows-list",
            data={"domain": domain_name},
            clTRID=f"rows-{domain_name}"
        )
        row_resp = row_result.get("response", {})
        if row_resp.get("code") not in (1000, "1000"):
            print(f"Error with dns-rows-list for domain {domain_name}:")
            print(json.dumps(row_result, indent=2, ensure_ascii=False))
            continue

        row_data = row_resp.get("data", {}).get("row", {})
        rows = row_data.values() if isinstance(row_data, dict) else row_data

        if not rows:
            print(f"No DNS records for the domain {domain_name}.")
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

        print(f"A zone file has been generated for the domain: {zone_path}")


def compare_zone_ns(cfg):
    print("\n=== Compare all DNS records from zone/ directory vs WAPI ===")
    if not ZONE_DIR.exists():
        print(f"The {ZONE_DIR} folder does not exist.")
        return

    results = []
    for path in sorted(ZONE_DIR.iterdir()):
        # ignorujeme soubory, které nejsou .zone
        if path.suffix != ".zone":
            print(f"The file was ignored: {path.name}")
            continue

        domain = path.stem

        # 1) Načti všechny záznamy z lokálního zone souboru
        zone_records = parse_zone_file(path)

        print(f"From zone file {path.name} – records retrieved: {len(zone_records)}")

        # 2) Načti všechny záznamy z WAPI (dns-rows-list)
        wapi_resp = call_wapi(
            cfg["user"], cfg["password"],
            "dns-rows-list",
            data={"domain": domain},
            clTRID=f"cmp-{domain}"
        )
        resp = wapi_resp.get("response", {})
        # Pokud není kód 1000 - OK, pak vrať chybu
        if resp.get("code") not in (1000, "1000"):
            print(f"WAPI returned an error for {domain}: {resp.get('result')}")
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
        print(f"From WAPI {domain} – records retrieved: {len(wapi_records)}")

        # 3) Porovnej obě množiny
        set_zone = set(zone_records)
        set_wapi = set(wapi_records)
        all_recs = sorted(set_zone | set_wapi)
        for name, ttl, rtype, rdata in all_recs:
            if (name, ttl, rtype, rdata) in set_zone and (name, ttl, rtype, rdata) in set_wapi:
                status, note = "matching", ""
            elif (name, ttl, rtype, rdata) in set_zone:
                status, note = "missing", "missing in WAPI"
            else:
                status, note = "difference", "missing in zone file"
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
    print(f"\nResult saved to CSV: {csv_path}")

def sync_zone_records(cfg):
    print("\n=== Add/Repair records from zone files in zone/ directory to WAPI ===")
    # 1) Zkontroluj, že mám složku s .zone soubory
    if not ZONE_DIR.exists():
        print(f"The {ZONE_DIR} folder does not exist.")
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
            print(f"The file was ignored: {path.name}")
            continue

        domain = path.stem
        print(f"\n--- I'm processing the domain {domain} ---")

        # 4) Načti lokální záznamy
        zone_map = {
            (name, rtype): (ttl, rdata)
            for name, ttl, rtype, rdata in parse_zone_file(path)
        }
        print(f" Locally: {len(zone_map)} records")

        # 5) Pokud doména není v DNS, přidej ji
        if domain not in dns_domains:
            print(f" Adding domain {domain}")
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
            print(f" Error loading records from WAPI: {row_resp}")
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
        print(f" WAPI: {len(wapi_map)} records")

        # 8) Přidání nebo aktualizace lokálních záznamů
        for key, (z_ttl, z_rdata) in zone_map.items():
            name, rtype = key
            if key not in wapi_map:
                print(f" Adding record {name} {rtype}")
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
                    print(f" Updating record {name} {rtype}")
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
                # prozatím vypnuto, pouze se vypisuje
                print(f" [disabled] Deleting record {name} {rtype}")
                """
                call_wapi(cfg["user"], cfg["password"], "dns-row-delete",
                          data={"domain": domain, "row_id": row_id},
                          clTRID=f"del-row-{domain}-{name}")
                """
    print("\nSynchronisation complete.")


# ---------- Menu ----------
def show_menu():
    print("""
Choose what you want to do:
  1) Do a WAPI connection test (ping)
  2) List of domains
  3) DNS list for domains
  4) Generate zone files
  5) Compare all DNS records from zone/ directory vs WAPI
  6) Add/Repair records from zone files in zone/ directory to WAPI
  0) Exit
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
            print("Ending script. Have a nice day.")
            break
        else:
            print("Invalid choice, try again.")

if __name__ == "__main__":
    main()
