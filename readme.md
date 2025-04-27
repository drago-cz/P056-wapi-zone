<!-- README.md -->

# WAPI Zone

A Python script to backup, compare and synchronize DNS zone records via the WEDOS WAPI.

It was originally written for personal DNS-record backups, but it shines when migrating hundreds of domains to WEDOS in bulk. Simply place your BIND-style zone files into the `zone/` directory and run the sync command to upload all records at once. This script automates:

- 📥 Downloading all DNS records via WAPI and exporting them as BIND-style zone files  
- 🔍 Tracking changes when records are added, modified or removed  
- 🔄 Bulk-upload all local zone files to WEDOS in one command—drop your `.zone` files into `zone/` and run synchronization (record-deletion is implemented but disabled by default).

## Features

- ⚙️ **Connection Test**: Verify your WAPI credentials with a simple ping.  
- 📜 **List Domains**: Fetch all registered domains in your WEDOS account.  
- 🌐 **List DNS Zones**: Show which domains have DNS zones enabled.  
- 📂 **Generate Zone Files**: Export each DNS zone into standard BIND-style zone files under `zone/`.  
- 🔍 **Compare Zones**: Compare local zone files versus live records in WAPI and export a CSV report.  
- 🔄 **Sync Zones**: Bulk-upload all local zone files to WEDOS in one command—drop your `.zone` files into `zone/` and run synchronization (record-deletion is implemented but disabled by default).

## Prerequisites

1. **WEDOS WAPI** must be activated in your WEDOS administration panel.  
   Official manual: https://kb.wedos.cz/en/wapi-manual/  
2. **Python 3.6+**  
3. **requests** library (`pip install requests`)

## Installation

```bash
git clone https://github.com/drago-cz/P056-wapi-zone.git
cd P056-wapi-zone
# (optional) create a venv:
python3 -m venv venv && source venv/bin/activate
pip install requests
```

## Configuration

Create a `config.json` file next to the script with your WAPI credentials:

```json
{
  "user": "admin@domain.tld",
  "password": "secretpassword"
}
```

## Usage

Make the script executable and run it:

```bash
chmod +x wapi-zone.py
./wapi-zone.py
```

Then choose from the menu:

```
1) Do a WAPI connection test (ping)
2) List of domains
3) DNS list for domains
4) Generate zone files
5) Compare all DNS records from zone/ directory vs WAPI
6) Add/Repair records from zone files in zone/ directory to WAPI
0) Exit
```

- Zone files are written to the `zone/` directory.  
- Comparison reports are saved as `zone_ns_comparison.csv` in the working directory.

### Beta Warning

This script is in **beta**. Use at your own risk—there may be bugs or untested edge cases.  
The record-deletion functionality is **implemented** but **commented out** by default.

## License

Distributed under the [MIT License](LICENSE).

## Acknowledgements

Special thanks to **ChatGPT o4-mini-high** for helping me debug key functions and draft this documentation!
