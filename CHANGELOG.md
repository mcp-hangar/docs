# Changelog

## [1.0.3](https://github.com/mcp-hangar/docs/compare/v1.0.2...v1.0.3) (2026-07-18)


### Changed

* **architecture:** add ADR-010 retiring the agent + Hangar Cloud tier ([#52](https://github.com/mcp-hangar/docs/issues/52)) ([858c173](https://github.com/mcp-hangar/docs/commit/858c173a94b22c2090cae286133eaed5284cf7a1))
* **reference:** add EU AI Act / SOC 2 compliance posture doc ([#55](https://github.com/mcp-hangar/docs/issues/55)) ([b5fd9d9](https://github.com/mcp-hangar/docs/commit/b5fd9d97292c47bfb92f863dfae1d398a9b6b7ff))
* **reference:** generate the released-artifacts matrix + immutable-tags status (Track 2) ([#56](https://github.com/mcp-hangar/docs/issues/56)) ([c52fd54](https://github.com/mcp-hangar/docs/commit/c52fd54755f11d626b73c741b7f55c8f105a4ffb))
* **reference:** update compatibility matrix to core 1.5.1 ([#53](https://github.com/mcp-hangar/docs/issues/53)) ([fb1cace](https://github.com/mcp-hangar/docs/commit/fb1cace69190714111ad701acc0e81ae8da6f3c2))
* **release:** correct the chart install status and record mutable chart tags ([#46](https://github.com/mcp-hangar/docs/issues/46)) ([2bd19ff](https://github.com/mcp-hangar/docs/commit/2bd19ff0febb119340ce97ab4e0e588a35183ac8))
* **repo:** retire hangar-agent / Hangar Cloud references ([#51](https://github.com/mcp-hangar/docs/issues/51)) ([91561fd](https://github.com/mcp-hangar/docs/commit/91561fd65297afc4f6d0ffa5ef6f059caaccaac5))

## [1.0.2](https://github.com/mcp-hangar/docs/compare/v1.0.1...v1.0.2) (2026-07-16)


### Changed

* **guides:** correct contributing and git-flow for the multi-repo topology ([#44](https://github.com/mcp-hangar/docs/issues/44)) ([ed5a858](https://github.com/mcp-hangar/docs/commit/ed5a8580adcde05a7e6f21a10ea23b753777da4b))
* **reference:** document event_store fail-fast and non-loopback auth requirement ([#42](https://github.com/mcp-hangar/docs/issues/42)) ([1fe2671](https://github.com/mcp-hangar/docs/commit/1fe267131ebcabdce5de18ba00877d448cf36be9))
* **release:** record the validated kubernetes range and the chart install status ([#45](https://github.com/mcp-hangar/docs/issues/45)) ([6bfb7aa](https://github.com/mcp-hangar/docs/commit/6bfb7aafbb5cdd0a77ec4ba83801a46652d6c18c))

## [1.0.1](https://github.com/mcp-hangar/docs/compare/v1.0.0...v1.0.1) (2026-07-15)


### Changed

* **reference:** document the config.yaml command-bus rate_limit block (1.5.0) ([#40](https://github.com/mcp-hangar/docs/issues/40)) ([49768f3](https://github.com/mcp-hangar/docs/commit/49768f3a505370678d927cb11bb1f4042abb31e9))

## 1.0.0 (2026-07-15)


### Added

* **content:** migrate public docs from mcp-hangar/docs/ ([0e4232f](https://github.com/mcp-hangar/docs/commit/0e4232f3906ba780baf4edb520b4e0459744529a)), closes [#2](https://github.com/mcp-hangar/docs/issues/2)


### Changed

* **architecture:** add ADR-008 -- task governance is relay-only ([#12](https://github.com/mcp-hangar/docs/issues/12)) ([9321f43](https://github.com/mcp-hangar/docs/commit/9321f439847b14a8eb52bb23f8a4e04768c85a6c))
* **architecture:** draft ADR-009 independent release topology ([#32](https://github.com/mcp-hangar/docs/issues/32)) ([cf5c4de](https://github.com/mcp-hangar/docs/commit/cf5c4ded9e0e9af430d904445f48872258b501a8))
* **content:** document mcp-hangar 1.3.0 ([710b29a](https://github.com/mcp-hangar/docs/commit/710b29a89672a8d9fd302afab70ffa3a9f594c44))
* **cookbook:** add 1.3 digest pinning upgrade recipe ([a3832ce](https://github.com/mcp-hangar/docs/commit/a3832cee41f6f8c2b54275bf2d0fc86dfdc42acf))
* **cookbook:** add interceptor discovery recipe ([73e8d08](https://github.com/mcp-hangar/docs/commit/73e8d086d07a0663ac4b80a19c5b16927b02af68))
* **guides:** add a progressive deployment playbook ([#23](https://github.com/mcp-hangar/docs/issues/23)) ([9f21a91](https://github.com/mcp-hangar/docs/commit/9f21a91d90cb4f1314a13e93d08a4b30193e3de5))
* **guides:** add external multi-tenant OIDC front door cookbook ([#26](https://github.com/mcp-hangar/docs/issues/26)) ([982bbe2](https://github.com/mcp-hangar/docs/commit/982bbe23a445e567a458c53c55eeccb9defeafa6))
* **guides:** add local dev and staging deployment profiles cookbook ([#25](https://github.com/mcp-hangar/docs/issues/25)) ([20f3cb0](https://github.com/mcp-hangar/docs/commit/20f3cb00de9650e38c90e2abaa33f7c640191a15))
* **guides:** add production read-only and controlled-write boundaries cookbook ([#24](https://github.com/mcp-hangar/docs/issues/24)) ([71c5248](https://github.com/mcp-hangar/docs/commit/71c5248d8743f44ed03bff31d77332469ee0b93a))
* **guides:** cookbook harden a public authenticated MCP gateway ([#29](https://github.com/mcp-hangar/docs/issues/29)) ([37b7172](https://github.com/mcp-hangar/docs/commit/37b7172ca523d3508d8560a2e11c0f99d6cc54a9)), closes [#21](https://github.com/mcp-hangar/docs/issues/21)
* **guides:** correct rate-limit scope in cookbook 06 ([#15](https://github.com/mcp-hangar/docs/issues/15)) ([c20f65a](https://github.com/mcp-hangar/docs/commit/c20f65ac2dbf6eebd9bea2cc0f90ee12675e6d4d))
* **guides:** document mcp-hangar 1.4.0 and add 1.4 cookbooks ([#8](https://github.com/mcp-hangar/docs/issues/8)) ([9cda48c](https://github.com/mcp-hangar/docs/commit/9cda48c1e9b4dfb96397f0e00518b54be0533513))
* **guides:** fix drifted cookbook recipes against 1.4.0 source ([#9](https://github.com/mcp-hangar/docs/issues/9)) ([9591ffc](https://github.com/mcp-hangar/docs/commit/9591ffce2b4acf464c562693b2bd6073e3b2b011))
* **guides:** fix duplicated recipe numbers in cookbook 21 and 22 ([#31](https://github.com/mcp-hangar/docs/issues/31)) ([a52521f](https://github.com/mcp-hangar/docs/commit/a52521f245e23be164ddce86972303bdb24df0d1)), closes [#30](https://github.com/mcp-hangar/docs/issues/30)
* **guides:** use mcp-hangar as the Kubernetes namespace in examples ([#36](https://github.com/mcp-hangar/docs/issues/36)) ([62d9806](https://github.com/mcp-hangar/docs/commit/62d9806efe7f82e22b1d81b01736cbf9a4155686))
* **release:** add 1.5.0 upgrade notes, CLI auth command, and compatibility matrix ([#39](https://github.com/mcp-hangar/docs/issues/39)) ([57bbe9b](https://github.com/mcp-hangar/docs/commit/57bbe9bbf6108249506ae1538639d7804bd0ff4e))
* **release:** add release compatibility and GHCR security policy ([#33](https://github.com/mcp-hangar/docs/issues/33)) ([08a41c9](https://github.com/mcp-hangar/docs/commit/08a41c993d2285cf5c61f445e1e91a65cd8d4fb1))
* **release:** add Releases & Artifacts install index ([#11](https://github.com/mcp-hangar/docs/issues/11)) ([6808a91](https://github.com/mcp-hangar/docs/commit/6808a91a25137f7d7a3ac11f51c50ff48ce58b2d))
* **release:** correct the core image as signed (it already is) ([#38](https://github.com/mcp-hangar/docs/issues/38)) ([3483627](https://github.com/mcp-hangar/docs/commit/34836277ef239e34c47bf5cef196e521938aa4bb))
* **release:** record cosign signing done; all artifacts signed ([#37](https://github.com/mcp-hangar/docs/issues/37)) ([27b75b7](https://github.com/mcp-hangar/docs/commit/27b75b7dceaa760cd774a6f58bc55b0cb67b143d))
* **release:** record verified Helm chart releases; all lanes published ([#35](https://github.com/mcp-hangar/docs/issues/35)) ([ef65e84](https://github.com/mcp-hangar/docs/commit/ef65e84ac16e80c2df7bf060e184cdfbe83cedf6))
* **release:** record verified operator and agent image releases ([#34](https://github.com/mcp-hangar/docs/issues/34)) ([18aba8c](https://github.com/mcp-hangar/docs/commit/18aba8c3108bdfacc662ea5681e69523b2e15c26))
* sync with mcp-hangar source, document 1.3.0, add drift validation ([#7](https://github.com/mcp-hangar/docs/issues/7)) ([45bef08](https://github.com/mcp-hangar/docs/commit/45bef08e07222c2b9062a3ee93810a9ea655772d))
