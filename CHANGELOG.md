# Changelog

## [0.4.0](https://github.com/leolionart/media-library-manager/compare/v0.3.0...v0.4.0) (2026-04-10)


### Features

* add bulk_delete.py script for automated removal of library issues ([f4f42d0](https://github.com/leolionart/media-library-manager/commit/f4f42d0f393ed20215fd4f4dc67b575eb790f866))
* full rclone support with dynamic remotes, mount/unmount and optimized metadata dashboard ([7ca80ec](https://github.com/leolionart/media-library-manager/commit/7ca80ecbadc95530529d56361ba22fb809c3e9e4))
* make scan flows cache-first with metadata auto-refresh ([0ef38a8](https://github.com/leolionart/media-library-manager/commit/0ef38a802a85f1cffd5d90faf0dfe6f9ac3f6768))
* parameterize host volumes in docker-compose for Synology compatibility ([90a1320](https://github.com/leolionart/media-library-manager/commit/90a132037eef7d2d938546568348afb6529ee779))


### Bug Fixes

* add privileged and fuse device to compose.yaml for rclone mount support ([1a9d73c](https://github.com/leolionart/media-library-manager/commit/1a9d73c4a128753e37259dfa64475a6d721737bf))
* define DEFAULT_RCLONE_TIMEOUT in storage.rclone_cli to fix ImportError ([b604a5e](https://github.com/leolionart/media-library-manager/commit/b604a5ef0d3cf3ebbfd151974fe1843a085cbbe6))
* display correct IP address and MAC address for LAN discovery devices ([f8385c3](https://github.com/leolionart/media-library-manager/commit/f8385c3c800c2c2f78d6e1340839a494cbf3d278))
* install rclone and fuse3 in Dockerfile to support Rclone operations and mount ([9ac58f4](https://github.com/leolionart/media-library-manager/commit/9ac58f4c7925d3549d50efa525b407535017e720))
* use listremotes --long and manual parsing instead of unsupported --json flag ([456026e](https://github.com/leolionart/media-library-manager/commit/456026e5fa066f24c5299d7d8900ba386fadf289))
* use network_mode host for LAN Discovery and keep clean docker-compose structure ([faf168d](https://github.com/leolionart/media-library-manager/commit/faf168ddcc0d7c37379735a443e71604391065e2))

## [0.3.0](https://github.com/leolionart/media-library-manager/compare/v0.2.0...v0.3.0) (2026-04-09)


### Features

* include missing provider items in path repair scan ([767616e](https://github.com/leolionart/media-library-manager/commit/767616eeb037b5341afa8137376b66f92774381e))
* strip priority and score labels from UI for cleaner experience ([d6e4dbb](https://github.com/leolionart/media-library-manager/commit/d6e4dbb4b661604bd203ef828b44405fabaf4ea6))
* unify cleanup metrics in Overview dashboard ([292f56b](https://github.com/leolionart/media-library-manager/commit/292f56bbef217e19758462fc1d794a38b220a97f))
* use cached folder index for library cleanup and background file deletion ([a70e183](https://github.com/leolionart/media-library-manager/commit/a70e183228f6b95eeca7a1342d8db1d10e35bc26))


### Bug Fixes

* accept both snake_case and camelCase for add_import_exclusion in path-repair delete ([51084c9](https://github.com/leolionart/media-library-manager/commit/51084c9fa668389cf265cc144144b9bf98e81acf))
* correctly handle rclone not-found errors in existence probe and clear session cache before scans ([413e267](https://github.com/leolionart/media-library-manager/commit/413e267a7edef7ad27dca384ed0f276ca74ba836))
* ensure boolean query parameters are lowercased for Sonarr/Radarr API compatibility ([1771f79](https://github.com/leolionart/media-library-manager/commit/1771f7972b86ac20d0e85427639845df5c0d9a6f))
* ensure cleanup report stays accurate by pruning folder index and verifying local file existence ([37084b4](https://github.com/leolionart/media-library-manager/commit/37084b46660161bb5370bbc0043fb52e5150d35a))
* implement manual import exclusion for Sonarr/Radarr to bypass unreliable DELETE parameters ([8bdd790](https://github.com/leolionart/media-library-manager/commit/8bdd790d3bbb10c29b1f68a946c6f0802ed5fbeb))
* rclone file delete not found by probing directly and handling colons in paths ([2c171a8](https://github.com/leolionart/media-library-manager/commit/2c171a8512ecdc1c86c9813c69c7f6fae81b4d98))
* resolve ghost duplicates by adding real-time existence verification and optimized rclone caching ([b940773](https://github.com/leolionart/media-library-manager/commit/b9407732064c3d1b59565b9db2a37bdd1e37cb71))
* sonarr series deletion and blocking by formatting API parameters correctly and passing exclusion flag in backend ([f9492eb](https://github.com/leolionart/media-library-manager/commit/f9492eb9dc439a13a554fbedaff8b7ab239a58ee))
* use correct parameter name addImportListExclusion for Sonarr API v3 ([91e1494](https://github.com/leolionart/media-library-manager/commit/91e14945ee9fd7602be9d50abadb7b1922f9d757))

## [0.2.0](https://github.com/leolionart/media-library-manager/compare/v0.1.0...v0.2.0) (2026-04-04)


### Features

* improve smb operations backend and refresh ui foundation ([f0746ae](https://github.com/leolionart/media-library-manager/commit/f0746aedd5c921cbd8f9a489be650c4f1a3cb9bb))


### Documentation

* rewrite project documentation for current architecture ([1125a7d](https://github.com/leolionart/media-library-manager/commit/1125a7d752436c5dde858fed1c720c88ed836214))
