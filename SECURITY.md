# Security policy

NOVA-M1 is an early-stage research SoC project, not a security-qualified product.
No secure-boot, debug-isolation, DMA-isolation, side-channel resistance, or
production-silicon assurance is established by the current foundation. Do not
use an experimental configuration to protect sensitive data or safety-critical
systems. See [current status](docs/nova/STATUS.md) and the
[platform security boundaries](docs/nova/PLATFORM.md).

## Reporting a suspected vulnerability

Do not post exploitable details, credentials, private workloads, proprietary
artifacts, or personal data in a public issue or pull request.

If GitHub private vulnerability reporting is enabled for this repository, use
the repository's **Security → Report a vulnerability** interface. This document
does not claim that the feature is enabled. If it is unavailable, ask a maintainer
for a confidential reporting channel using a minimal public contact request
without vulnerability details. No dedicated security email or response-time
commitment is currently published.

Once a private channel is agreed, provide the affected revision and configuration,
dependency/tool versions, the threatened boundary, prerequisites, a minimal
reproducer, expected and observed behavior, and redacted evidence. Identify
whether the finding concerns repository tooling, simulated RTL, FPGA hardware,
or another target. Do not execute invasive tests on systems you do not own or
have permission to test.

## Scope and handling

- Report NOVA-specific integration problems here. For a dependency-only issue,
  follow that project's reporting policy and coordinate disclosure without
  publishing private details in this repository.
- Maintainers must record affected configurations, containment options, a fix,
  regression tests, remaining limitations, and an agreed disclosure decision.
- A fix or passing repository CI does not establish a secure processor. Security
  claims need threat models and target-specific verification evidence.
- Supported security-maintenance versions have not yet been declared. A research
  release is not a promise of a production support or patching lifetime.

Never attach full environment dumps, tokens, secret-bearing logs, private keys,
unredacted memory images, or restricted PDK/IP files to a report. Preserve useful
technical evidence while removing confidential content.
