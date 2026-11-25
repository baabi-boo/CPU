// NOVA host-only integration probe for the pinned Spike HTIF implementation.
// This fixture supplies memory; it never executes a RISC-V instruction or RTL.
// Link with the real pinned FESVR sources, optionally replacing only htif.cc with
// the hash-checked observer overlay. No HTIF/device/syscall implementation is
// substituted here. Each invocation must use a fresh process and witness path.
#include "htif.h"

#include <array>
#include <csignal>
#include <cstdio>
#include <cstring>
#include <stdexcept>
#include <string>
#include <vector>

namespace {
constexpr addr_t kTohost = 0x100;
constexpr addr_t kFromhost = 0x108;
constexpr addr_t kSyscall = 0x200;

class host_memory_htif final : public htif_t {
 public:
  explicit host_memory_htif(const std::string &mode)
      : htif_t(std::vector<std::string>{"none"}), mode_(mode) {}

  void start() override {
    std::map<std::string, uint64_t> symbols{
        {"tohost", kTohost}, {"fromhost", kFromhost}};
    load_symbols(symbols);
    if (mode_ == "direct0" || mode_ == "direct7") {
      put64(kTohost, mode_ == "direct0" ? 1 : 15);
    } else if (mode_ == "syscall0" || mode_ == "syscall7" ||
               mode_ == "syscall7-signal") {
      // The real syscall dispatcher reads eight reg_t words from this address.
      // RISC-V proxy syscall 93 invokes the real syscall_t::sys_exit(), which
      // calls the out-of-line htif_t::htif_exit().
      put64(kSyscall, 93);
      put64(kSyscall + 8, mode_ == "syscall0" ? 0 : 7);
      put64(kTohost, kSyscall);
    } else if (mode_ != "signal-only") {
      throw std::invalid_argument("unknown host-only probe mode");
    }
  }

  uint64_t peek64(addr_t address) const {
    target_endian<uint64_t> value;
    std::memcpy(&value, memory_.data() + address, sizeof(value));
    return from_target(value);
  }

  unsigned int idle_calls = 0;
  unsigned int tohost_reads = 0;
  unsigned int tohost_clears = 0;
  unsigned int reset_calls = 0;

 protected:
  void reset() override { ++reset_calls; }

  void read_chunk(addr_t address, size_t length, void *destination) override {
    bounds(address, length);
    if (address == kTohost) ++tohost_reads;
    std::memcpy(destination, memory_.data() + address, length);
  }

  void write_chunk(addr_t address, size_t length, const void *source) override {
    bounds(address, length);
    std::memcpy(memory_.data() + address, source, length);
    if (address == kTohost && peek64(kTohost) == 0) ++tohost_clears;
    // Dispatch writes the return block only after sys_exit has set the actual
    // private HTIF optional. Raise a real host signal at that boundary to test
    // that target presence and signal exit remain independent observations.
    if (mode_ == "syscall7-signal" && address == kSyscall &&
        peek64(kSyscall) == 0 && !mixed_signal_sent_) {
      mixed_signal_sent_ = true;
      if (std::raise(SIGTERM) != 0)
        throw std::runtime_error("could not raise fixture SIGTERM");
    }
  }

  size_t chunk_align() override { return 8; }
  size_t chunk_max_size() override { return 64; }

  void idle() override {
    ++idle_calls;
    if (mode_ != "signal-only" || idle_calls != 1)
      throw std::runtime_error("unexpected HTIF idle in bounded fixture");
    if (std::raise(SIGTERM) != 0)
      throw std::runtime_error("could not raise fixture SIGTERM");
  }

 private:
  void bounds(addr_t address, size_t length) const {
    if (address > memory_.size() || length > memory_.size() - address)
      throw std::out_of_range("host fixture memory bound exceeded");
  }

  void put64(addr_t address, uint64_t value) {
    memif().write_uint64(address, to_target(value));
  }

  std::array<unsigned char, 4096> memory_{};
  std::string mode_;
  bool mixed_signal_sent_ = false;
};
}  // namespace

int main(int argc, char **argv) {
  if (argc != 2) {
    std::fputs("usage: htif_host_probe MODE\n", stderr);
    return 99;
  }
  try {
    const std::string mode(argv[1]);
    host_memory_htif htif(mode);
    const int result = htif.run();
    const int expected = mode.find('7') == std::string::npos ? 0 : 7;
    const bool syscall = mode.rfind("syscall", 0) == 0;
    const uint64_t fromhost = htif.peek64(kFromhost);
    const bool okay = htif.done() && result == expected &&
                      htif.exit_code() == expected &&
                      htif.peek64(kTohost) == 0 &&
                      fromhost == (syscall ? 1U : 0U) &&
                      htif.tohost_reads == 1 && htif.reset_calls == 0 &&
                      htif.tohost_clears == (mode == "signal-only" ? 0U : 1U) &&
                      htif.idle_calls == (mode == "signal-only" ? 1U : 0U);
    std::printf("{\"scope\":\"native-host-only\",\"mode\":\"%s\","
                "\"run_return\":%d,\"done\":%s,\"exit_code\":%d,"
                "\"tohost_after\":%llu,\"fromhost_after\":%llu,"
                "\"idle_calls\":%u,\"tohost_reads\":%u,"
                "\"tohost_clears\":%u,\"reset_calls\":%u,"
                "\"fixture_checks_passed\":%s}\n",
                mode.c_str(), result, htif.done() ? "true" : "false",
                htif.exit_code(),
                static_cast<unsigned long long>(htif.peek64(kTohost)),
                static_cast<unsigned long long>(fromhost), htif.idle_calls,
                htif.tohost_reads, htif.tohost_clears, htif.reset_calls,
                okay ? "true" : "false");
    return okay ? result : 99;
  } catch (const std::exception &error) {
    std::fprintf(stderr, "host-only fixture error: %s\n", error.what());
    return 99;
  }
}
