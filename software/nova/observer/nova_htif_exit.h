// NOVA native HTIF terminal-state observer. This is host-side evidence tooling.
#ifndef NOVA_HTIF_EXIT_H
#define NOVA_HTIF_EXIT_H

// Called once from the pinned htif_t::stop() after stopped becomes true. The
// instance is opaque and is never dereferenced or serialized. A second call in
// the same process is fatal, including a call from a different HTIF instance.
//
// Every call requires a fresh absolute NOVA_HTIF_WITNESS_PATH and lowercase
// hex64 NOVA_HTIF_RUN_ID / NOVA_HTIF_BINDING_SHA256 values. Failure exits the host
// with status 125; no success or target-failure assessment may admit that status.
// Recording a snapshot alone never qualifies a CPU, RTL build, or G1 milestone.
void nova_htif_observe_stop(const void *instance, bool present,
                            int raw_exit_code, bool signal_exit);

#endif  // NOVA_HTIF_EXIT_H
