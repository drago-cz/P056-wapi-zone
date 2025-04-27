<!-- CHANGELOG.md -->

# Changelog

All notable changes to this project will be documented in this file.

## [0.1.0] – 2025-04-27

### Added

- Initial **beta** release of the WAPI Zone backup & sync script.  
- `call_wapi` helper to authenticate and send commands to WEDOS WAPI.  
- CLI menu with options to:
  - Test connection (ping)  
  - List domains (`domains-list`)  
  - List DNS zones (`dns-domains-list`)  
  - Generate BIND-style zone files (`dns-rows-list`)  
  - Compare local zone files vs live WAPI records and export CSV.  
  - Sync local zone files to WAPI (add/update records).  
- Zone files are stored under `zone/`.  
- CSV comparison report saved as `zone_ns_comparison.csv`.  
- Configuration via a simple `config.json` file.  
- Record-deletion commands are present in code but disabled by default.