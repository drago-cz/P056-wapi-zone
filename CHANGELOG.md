<!-- CHANGELOG.md -->

# Changelog

All notable changes to this project will be documented in this file.

## [0.2.0] - 2025-08-18
### Added
- Now it is possible to set in `TXT_RDATA_STRIP` characters that will be ignored in TXT records

### Changed
- Fixed `list_domains` to process canceled domain orders without expiration date
- Fixed bug with multiple TXT records in `sync_zone_records`

## [0.1.1] - 2025-05-09

### Added
- Introduced `parse_zone_file` to simplify parsing `.zone` files. The function supports both inline TTLs and `$ORIGIN/$TTL` directives with relative names.
  
### Changed
- Updated `list_dns_domains` to handle `domain` data in both `dict` and `list` formats and improved error handling for DNS fetching.
- Enhanced `generate_zone_files` to adapt to multiple DNS domain data formats and streamlined the zone file generation process.
- Refactored `compare_zone_ns` for cleaner logic by leveraging the `parse_zone_file` helper function.
- Simplified `sync_zone_records` by replacing manual zone record mapping logic with the use of `parse_zone_file`.

### Removed
- Deprecated manual parsing logic for `.zone` files in `compare_zone_ns` and `sync_zone_records`.

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