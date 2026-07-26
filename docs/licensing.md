# Licensing

Multi-licensed by artifact type. Each area carries the license that fits it.

| Artifact | License | File |
|---|---|---|
| Hardware design (BOM, case, mechanicals) | CERN-OHL-W-2.0 | `LICENSE.hardware` |
| Kernel driver (`driver/`) | GPL-2.0-only | `driver/LICENSE` |
| Provisioning, calibration, community tools | Apache-2.0 | `LICENSE.software` |
| Documentation | CC-BY-SA-4.0 | `LICENSE.docs` |

The driver derives from the Linux kernel, NVIDIA tegracam, and RidgeRun (all GPL-2.0) and cannot be relicensed. It stays in its own subtree with its own `LICENSE` and attribution intact.

OSHWA self-certification can follow once the BOM and case files land.
