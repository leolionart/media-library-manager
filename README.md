# Media Library Manager

`media-library-manager` is a local dashboard and CLI for consolidating movie and TV libraries spread across multiple folders, disks, and mounted LAN shares.

It is built for the gap between download managers like Radarr/Sonarr and manual storage cleanup:

- Scan multiple roots at once.
- Detect exact duplicates with SHA-256.
- Detect same movie or episode stored in different places.
- Build a safe `move/delete/review` plan.
- Keep `dry-run` as the default so nothing is modified until you execute.
- Browse mounted LAN shares directly from the dashboard.
- Discover other devices on the LAN through Bonjour/ARP, not just shares already mounted on this Mac.
- Sync moved paths back into Radarr and Sonarr so they stop tracking the old folder.

## Run

```bash
cd "/Volumes/DATA/Coding Projects/media-library-manager"
./run-dashboard.sh
```

Default URL:

```text
http://localhost:9999
```

## Dashboard Modules

- `Overview`: root count, mounted shares, latest scan/plan/apply state.
- `Library Roots`: add scan roots and define canonical movie/series/review targets.
- `Integrations`: configure Radarr and Sonarr URL, API key, managed root folder, and sync policy.
- `LAN Browser`: discover LAN devices, open SMB/NFS/AFP URLs, browse mounted shares, and copy folders into the root form.
- `Duplicate Report`: inspect exact duplicate groups and same-title collisions.
- `Action Plan`: build the cleanup plan and execute it.
- `Activity Log`: review config changes and job history.

## Radarr / Sonarr Workflow

The integration is filesystem-first:

1. The dashboard moves files itself.
2. After `Execute Plan`, it can call Radarr/Sonarr APIs to update the tracked `path` and `rootFolderPath`.
3. It then triggers refresh/rescan commands so those systems pick up the new location.

This avoids the common failure mode where Radarr/Sonarr still point at the old root and later create duplicates by downloading into the previous folder again.

## Integration Setup

Open `Integrations` and fill in:

- `Base URL`
  Example: `http://192.168.1.20:7878` for Radarr, `http://192.168.1.20:8989` for Sonarr
- `API Key`
  Use the API key from each application
- `Managed Root Folder`
  Optional override. Leave blank if you want the app to use the canonical Movie Root or Series Root from `Library Roots`.

Options:

- `Auto-sync after execute apply`
- `Trigger refresh/rescan after update`
- `Create root folder if missing`

Use `Test Connections` to verify both integrations.

## LAN Discovery Notes

- `Refresh LAN` can discover devices elsewhere in the network through Bonjour/mDNS and the local ARP table.
- Those devices may appear before they are mounted locally.
- To browse actual folders from the dashboard, the share still needs to be mounted so macOS exposes it as a readable path under `/Volumes/...` or another mount point.
- The discovery panel can still give you direct URLs like `smb://nas.local` to open in Finder.

## Notes

- The path sync uses `moveFiles=false` when updating Radarr/Sonarr items because files were already moved by this tool.
- Review the action plan before executing it.

## Verification

Local verification used during development:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
python3 -m py_compile src/media_library_manager/*.py src/media_library_manager/providers/*.py
```
