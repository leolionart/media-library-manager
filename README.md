# Media Library Manager

`media-library-manager` is a local dashboard and CLI for working with existing media folders across local disks, mounted shares, and SMB hosts.

The project is built around a simple operating model:

1. Connect the app to folders that already exist, including folders managed by Radarr and Sonarr.
2. Detect duplicate folders or duplicate files and suggest what can be removed.
3. Allow moving a folder from location A to location B with an explicit cut/paste style workflow.

The application is not meant to replace Radarr or Sonarr. It sits beside them and helps operate on the filesystem they already use.

## Product Scope

The dashboard works with storage that already exists:

- local folders visible to the runtime
- mounted network shares
- SMB hosts with different usernames and passwords
- folders already managed by Radarr
- folders already managed by Sonarr

Typical use cases:

- connect one or more storage roots so the app can scan them
- find duplicate movie or series folders spread across multiple disks
- find duplicate files inside those folders
- review deletion suggestions before removing anything
- move a movie or series folder from one storage location to another
- move a downloaded folder into the correct Radarr or Sonarr managed library path

## Dashboard Structure

The UI is intentionally split into two pages.

### 1. Operations

This page contains the operational tools:

- list connected folders as the main workspace
- use a per-folder action dropdown
- choose a source folder
- choose a destination folder
- cut and paste a folder from A to B
- delete a folder
- scan connected folders for duplicate files and folders
- review suggested deletions
- move a download folder into an existing Radarr or Sonarr managed path

This page should stay focused on day-to-day actions, not connection setup.

### 2. Settings

This page contains all application setup:

- save multiple SMB host profiles
- each profile can have its own host, username, and password
- add folders through a modal
- when adding a folder, select one of the saved SMB profiles and let the modal suggest the mounted runtime path automatically when possible
- add multiple folders when needed, because media may be spread across multiple disks
- in most cases, add a high-level root folder and let the app scan and operate inside that root
- configure Radarr connection
- configure Sonarr connection

Settings should remain the support layer. Operations should remain the working layer.

## Folder Connection Model

The expected workflow for folder setup is:

1. Save one or more SMB profiles.
2. Open the add-folder modal.
3. Discover a LAN SMB host or enter an IP manually.
4. Save or reuse an SMB profile.
5. Select that saved profile and let the modal match it to an existing mounted runtime path.
6. Confirm or adjust the suggested folder path.
7. Repeat if you need to work across multiple disks or multiple hosts.

The common case is still simple:

- add one large root folder per disk or share
- let the app scan that root
- work inside the connected roots from the Operations page

## Radarr / Sonarr Relationship

Radarr and Sonarr remain part of the project.

The app must be able to work with folders already managed by those systems:

- use Radarr and Sonarr as connection-backed library references
- keep their API settings in `Settings`
- allow operational actions in `Operations` to move folders into the correct managed location
- keep filesystem actions explicit so the user can review what is about to happen

Example:

- a movie folder exists in a download location
- the user selects that folder in `Operations`
- the user chooses `Move to Radarr...`
- the user selects the movie already managed by Radarr
- the app moves the folder contents into the existing Radarr path
- because the managed path itself did not change, the app refreshes or rescans Radarr instead of changing `movie.path`

The same pattern applies to Sonarr.

## Duplicate Detection

The project should detect duplicates at two levels:

- duplicate files
- duplicate folders

The output should be phrased as suggestions, not automatic destructive actions.

Expected behavior:

- scan all connected roots
- detect exact duplicate files where possible
- detect folders that appear to represent the same movie or series content
- present suggestions to delete or keep
- require explicit confirmation before destructive actions

## Deployment

The primary deployment target is a Linux server running Docker Compose.
The container is configured to join the host network and access common host mount roots directly.

1. Copy the environment template:

```bash
cp .env.example .env
mkdir -p data
```

2. Edit `.env` if you want to change the image tag or dashboard port:

```dotenv
MLM_IMAGE=ghcr.io/leolionart/media-library-manager:latest
MLM_PORT=9988
```

3. Start the stack:

```bash
docker compose up -d
```

4. Open:

```text
http://localhost:9988
```

`compose.yaml` uses:

- `./data` to `/app/data` for persisted dashboard state
- `network_mode: host` so the service can reach the LAN directly
- bind mounts for `/mnt`, `/media`, and `/srv` so host-mounted shares are visible inside the container

## Local Run Without Docker

```bash
./run-dashboard.sh
```

## Current Direction For SMB Support

SMB is a first-class setup concern in the product direction.

That means the dashboard should support:

- multiple SMB hosts
- different credentials per host
- selecting a saved SMB profile when adding a folder
- reusing those saved profiles across multiple connected roots

Infrastructure and deployment should not assume a single SMB target.

## Release Flow

The repository ships a Docker-only release flow:

- `CI` runs tests and validates the Docker build on pull requests and pushes to `main`.
- `release-please` opens or updates a release PR from conventional commits.
- when that release PR is merged to `main`, GitHub Actions creates the release and publishes:
  - `ghcr.io/leolionart/media-library-manager:latest`
  - `ghcr.io/leolionart/media-library-manager:<version>`
  - `ghcr.io/leolionart/media-library-manager:v<version>`

To keep releases automatic, use conventional commit prefixes such as `feat:`, `fix:`, or `chore:`.

## Verification

Local verification used during development:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
python3 -m py_compile src/media_library_manager/*.py src/media_library_manager/providers/*.py
```
