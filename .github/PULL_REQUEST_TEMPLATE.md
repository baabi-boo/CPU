## Change and scope

<!-- Explain the problem, bounded change, affected configuration/interfaces, and exclusions. -->

## Traceability and design

<!-- Requirement/test IDs, roadmap gate, related issues, ADR when needed, and upstream reuse versus original work. -->

## Validation evidence

<!-- Exact revision/configuration, commands, results, logs/artifact hashes, and failure-detection tests.
     Mark blocked/not-run checks explicitly. Separate repository, RTL, simulation, FPGA, and silicon evidence. -->

| Check | Result and evidence |
| --- | --- |
| `make -f nova.mk check` | |
| Relevant HDL / target-software tests | |
| Known limitations / unrun tests | |

## Risk, resources, and rollback

<!-- Compatibility, dependency changes, runtime/memory/disk budget, external approvals, and rollback plan. -->

## Contributor checklist

- [ ] This change targets `main` through a bounded, reviewable topic branch.
- [ ] Requirements, design documents, tests, and status records agree with the actual evidence.
- [ ] Repository checks passed, or their failures/blockers are explicitly recorded above.
- [ ] Relevant hardware/software tests and negative cases are included; unrun tests are not presented as passes.
- [ ] Dependency pins and license/notices are preserved, or a reviewed migration and provenance update is supplied.
- [ ] No secrets, private workloads, restricted PDK/IP, or unredacted sensitive logs are included.
- [ ] No unverified Apple compatibility/parity, energy-efficiency, coherent-memory, or tapeout claim is introduced.
- [ ] Any paid service, new runner, device access, or expensive experiment has explicit authorization.

See [CONTRIBUTING.md](../CONTRIBUTING.md), [SECURITY.md](../SECURITY.md), and
the [verification plan](../docs/nova/VERIFICATION.md). Written policy does not
itself enable repository protections or approve a hardware gate.
