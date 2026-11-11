package chipyard

import org.chipsalliance.cde.config.Config

/** NOVA's single-hart reference profile, reusing the pinned Rocket configuration.
  * Source scaffold only: elaboration and execution require separate evidence.
  */
class NovaM1BaselineConfig extends Config(
  new RocketConfig)

/** NOVA's initial two-hart BOOM v3/Rocket integration profile.
  * This reuses existing cores; it is not a new CPU microarchitecture or a
  * measured performance/efficiency pair. No GPU or NPU is added here.
  * Source scaffold only: elaboration and execution require separate evidence.
  */
class NovaM1MinimalConfig extends Config(
  new LargeBoomAndRocketConfig)
