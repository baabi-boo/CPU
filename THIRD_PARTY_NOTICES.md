# Third-party provenance and licensing

NOVA-M1 is an independent research project built on Chipyard. Reused source,
configuration infrastructure, documentation, and dependencies remain attributed
to their respective authors. Integration work is not authorship of the inherited
CPU, accelerator, or tooling designs.

## Imported Chipyard baseline

- Source: [UC Berkeley Chipyard](https://github.com/ucb-bar/chipyard).
- Imported revision: `a7946ede9bd625204435715dc40c750e2f8a251f`.
- [README.chipyard.md](README.chipyard.md) preserves the original README,
  acknowledgements, and publication bibliography byte-for-byte.
- [CONTRIBUTING.chipyard.md](docs/nova/upstream/CONTRIBUTING.chipyard.md)
  preserves the original upstream contribution guide byte-for-byte.
- The existing [LICENSE](LICENSE) and [LICENSE.SiFive](LICENSE.SiFive) are
  preserved unchanged. Retain the applicable source headers and notices.

The [upstream lock](nova/upstream-lock.json) records Git blob hashes for these
preserved files, all nine imported `conda-reqs` definitions and locks (including
`circt.json`), and the exact commits of all 57 imported dependency gitlinks.
The NOVA validator checks those records; it does not perform a complete licensing
or intellectual-property clearance of the resulting system.
Setup-generated changes to these toolchain inputs require the same reviewed
dependency migration as an intentional pin update; they are not exempt merely
because the upstream setup script generated them.

## Licensing boundaries

The root `LICENSE` contains the inherited Regents' BSD 3-Clause notice.
`LICENSE.SiFive` contains the Apache License 2.0 text and SiFive notice. Their
presence does not make the root license a blanket license for every dependency.
Use each file's and dependency's own applicable notices and license terms.

Unless explicitly identified otherwise, original NOVA-authored contributions
follow the repository's BSD 3-Clause contribution policy. Copyright remains with
the respective contributors; preserving the Regents' notice does not attribute
new NOVA work to the Regents. This policy does not relicense inherited material
or override a third-party file's terms.

Representative imported components include:

| Component | Repository path | Attribution boundary |
| --- | --- | --- |
| Rocket Chip | `generators/rocket-chip` | Existing CPU/SoC generator, not original NOVA CPU RTL |
| BOOM | `generators/boom` | Existing out-of-order core generator |
| Gemmini | `generators/gemmini` | Existing accelerator generator; NOVA integration remains unqualified |
| Constellation | `generators/constellation` | Existing interconnect generator |
| Radiance | `generators/radiance` | Imported dependency reference, not a qualified NOVA GPU |
| FireSim and FireMarshal | `sims/firesim`, `software/firemarshal` | Separate simulation and workload projects |
| Toolchains and tests | `toolchains`, `tools`, `software` | Inspect each included project's notices and distribution terms |

See [.gitmodules](.gitmodules) for dependency source locations and the lock for
revision identity. Uninitialized gitlinks are not embedded copies or evidence
that a component has been built, tested, or integrated into NOVA.

## Addition and distribution checklist

Before importing or distributing a new component, record its source, revision,
license/notices, modifications, and intended use. Preserve required notices and
review redistribution obligations for the actual packaged artifacts. Generated
RTL, firmware images, benchmark inputs, PDKs, memory macros, physical-interface
IP, and vendor tooling require their own provenance review; a source-code license
is not proof of rights to all manufacturing or software deliverables.

NOVA-M1 is not affiliated with or endorsed by Apple, UC Berkeley, SiFive, or other
upstream contributors. “M-series-inspired” describes a system-integration research
goal, not Apple design ownership, compatibility, or performance equivalence.

For dependency changes and evidence records, follow
[CONTRIBUTING](CONTRIBUTING.md) and [REPRODUCIBILITY](docs/nova/REPRODUCIBILITY.md).
