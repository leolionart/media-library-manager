# Changelog

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
