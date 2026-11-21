# CPU-only CUDA dependency preparation

**Compilation completed; GPU execution has not been tested.** One isolated build of unchanged llama.cpp source, intended for a future local single-GPU service. No model inference, repair score or new106-test score is claimed.

## Actual result

- Source archive: official commit4783b1145c7073bb809f4c282ff4853cbfe42954,39103960bytes, SHA2569588476bd9a7d5e62e19f83fea9eeb04287b2ce458c03e8a6107bfe70bce770e.
- All 4496 source-file hashes match before/after both attempts. The archive identity is distinct from a Git checkout; configured build number12576/commit label is not an independent verification.
- 41 fixed Conda packages,210803832 compressed bytes. Every archive's size/SHA256 was verified before offline install, and again when copied into private local ext4. CMake3.31.8, GCC/G++13.4.0, Ninja1.12.1, system CUDA12.9.86.
- Initial local configure exited0 in18.123s; the1325.688s target build failed at the final342/342 server link because libgomp.so.1 was absent from the link dependency search. A separate correction added `-Wl,-rpath-link,<toolchain-prefix>/lib` for the already installed OpenMP runtime. Correction configure/build exited0 in2.051s/2.05s; compiled CUDA library hash is unchanged. No unresolved-symbol bypass or upstream source edit. All stages used four logical CPUs/nice19. Source, toolchain, build and temporary files were on private local ext4.
- The compiled CUDA library exports its backend registry. CPU-only cuobjdump reports150 ELF entries forsm_86; readelf records dependencies/RPATH. The built server was never executed. These checks do not establish dynamic loading, model compatibility, offload or acceleration.
- Server SHA256`e63f0e6144a3d8813b0e004183270684d54f3de7a2ec204f5de6b8abb253bbd4`; CUDA library SHA256`52d2257263d798c0ea8a97a4279fef05f3b5abd41344245e27ea1bc4e820991f`. All produced file hashes are in[local/report.json](local/report.json). Binaries, toolchain packages and the full upstream source are not published.

## Failed attempt and monitoring limits

The first attempt kept source/toolchain/build on shared NFS. Compiler ABI configuration exceeded its300s limit, actual302.006s, return-15; no CUDA compilation occurred. The controller then verified unchanged source and exited2. Its logs and source hashes remain in[build-run-1/](build-run-1/report.json). The local attempt retained the exact source archive/toolchain package set and compiler options, and added120s source-hash phase caps. Cache state and filesystem changed together; this is not an isolated storage benchmark or speedup estimate.

Ninja puts compiler jobs into separate process groups. The original controller's group-only RSS samples exclude those jobs and **are not whole-build memory measurements**. Continuous supplemental tree monitoring began343.86s into the build, with the same16GiB sampled-tree-RSS/16GiB available-memory guards and the original2400s build deadline. Earlier coverage was group-only apart from one diagnostic tree snapshot. After monitor start, sampled tree peak was1857073152bytes; full-build peak is unknown. Shared pages are double counted by summed RSS. No supplemental tree guard fired, no cleanup signal was required, and no owned build descendants remained when the monitor finished. The forced-kill branch was not exercised.

The failed local final-link log remains in[local/build.log](local/build.log), with its original failed summary in[local/summary.json](local/summary.json). The correction uses the same compiled objects; its separate[protocol](link-correction/protocol.json),[commands](link-correction/started.json),[configuration](link-correction/configuration.json) and[link log](link-correction/build.log) are retained. Its resource checks cover the owned process tree from launch; no forced-kill branch was exercised. The two-second link stage is not the time for a full clean build.

## Scope

Explicit CUDA architecture86 and GGML_NATIVE=OFF avoid native-GPU selection during configuration. CUDA_VISIBLE_DEVICES is empty. NCCL, UI/prebuilt UI and OpenSSL are off; this prepares a local HTTP single-GPU dependency, not an HTTPS or multi-GPU deployment. No P100/sm60 compatibility or relocatability claim; private scratch/toolchain paths are still needed. The original CPU bundle is preserved.

[Summary](report.json), [initial protocol](protocol.json), [local protocol](local-protocol.json), [source provenance](source-preflight.json), [41-package lock](toolchain-lock.json), [actual configuration](local/configuration.json), [configure log](local/configure.log), [full build log](local/build.log), [tree accounting](local/tree-monitor-report.json), [ELF inspection](inspection/report.json). Artifact hashes/normalization rules are in[artifacts.json](artifacts.json). Only allowlisted metadata/logs are public; private paths are normalized. The MIT upstream notice accompanies them.

The existing106 core checks were not rerun; no neural trial occurred. Three upstream draft PRs were checked separately and remain open/unmerged without reviews at2026-11-21T04:51:00Z. Those states are not new contribution or merge results. Next work is an independently declared model/HTTP validation on an admitted idle86-capability GPU; no such allocation happened here.
