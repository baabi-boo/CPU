// NOVA native HTIF terminal-state observer. No upstream source is modified here.
#include "nova_htif_exit.h"

#include <atomic>
#include <cerrno>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <limits>

#include <fcntl.h>
#include <signal.h>
#include <sys/stat.h>
#include <unistd.h>

namespace {
constexpr std::size_t kPathLimit = 4096;
constexpr std::size_t kWitnessLimit = 4096;
constexpr char kFatal[] =
    "NOVA HTIF observer fatal: witness recording failed\n";
std::atomic_flag called = ATOMIC_FLAG_INIT;

static_assert(std::numeric_limits<int>::min() == -2147483647 - 1 &&
                  std::numeric_limits<int>::max() == 2147483647,
              "The pinned HTIF observer requires signed 32-bit int");

struct Output {
  int parent = -1;
  int file = -1;
  const char *leaf = nullptr;
  struct stat identity {};
  bool identified = false;
};

bool same_file(const struct stat &left, const struct stat &right) {
  return left.st_dev == right.st_dev && left.st_ino == right.st_ino;
}

// Invalidate our own incomplete witness when possible. Never remove a replaced
// path or any pre-existing output. Host status 125 remains authoritative even
// when a failing filesystem prevents this best-effort cleanup.
void discard(Output *output) {
  if (output == nullptr) return;
  if (output->file >= 0) {
    const int truncated = ::ftruncate(output->file, 0);
    (void)truncated;  // Cleanup failure must not override the pending status 125.
  }
  if (output->parent >= 0 && output->identified) {
    struct stat current {};
    if (::fstatat(output->parent, output->leaf, &current,
                  AT_SYMLINK_NOFOLLOW) == 0 &&
        same_file(current, output->identity)) {
      (void)::unlinkat(output->parent, output->leaf, 0);
    }
  }
  if (output->file >= 0) (void)::close(output->file);
  if (output->parent >= 0) (void)::close(output->parent);
}

[[noreturn]] void fatal(Output *output = nullptr) {
  discard(output);
  // This path never returns to HTIF. Blocking SIGPIPE here permits the required
  // status 125 even if stderr's reader disappeared; no signal handler is added.
  sigset_t blocked;
  if (::sigemptyset(&blocked) == 0 && ::sigaddset(&blocked, SIGPIPE) == 0 &&
      ::sigprocmask(SIG_BLOCK, &blocked, nullptr) == 0) {
    std::size_t offset = 0;
    while (offset != sizeof(kFatal) - 1) {
      const ssize_t count =
          ::write(STDERR_FILENO, kFatal + offset, sizeof(kFatal) - 1 - offset);
      if (count > 0) {
        offset += static_cast<std::size_t>(count);
      } else if (count != -1 || errno != EINTR) {
        break;
      }
    }
  }
  std::_Exit(125);
}

bool hex64(const char *value) {
  if (value == nullptr || ::strnlen(value, 65) != 64) return false;
  for (std::size_t i = 0; i != 64; ++i) {
    if (!((value[i] >= '0' && value[i] <= '9') ||
          (value[i] >= 'a' && value[i] <= 'f'))) return false;
  }
  return true;
}

bool valid_path(const char *path) {
  if (path == nullptr || path[0] != '/') return false;
  const std::size_t size = ::strnlen(path, kPathLimit);
  if (size < 2 || size == kPathLimit || path[size - 1] == '/') return false;
  const char *component = path + 1;
  for (const char *cursor = component;; ++cursor) {
    if (*cursor != '/' && *cursor != '\0') continue;
    const std::size_t length = static_cast<std::size_t>(cursor - component);
    if (length == 0 || (length == 1 && component[0] == '.') ||
        (length == 2 && component[0] == '.' && component[1] == '.')) return false;
    if (*cursor == '\0') return true;
    component = cursor + 1;
  }
}

// Walk from / using directory descriptors. O_NOFOLLOW on the final leaf alone
// would still allow a symlink in a parent directory to redirect the witness.
int open_parent(const char *path, const char **leaf) {
  int directory = ::open("/", O_RDONLY | O_DIRECTORY | O_CLOEXEC | O_NOFOLLOW);
  if (directory < 0) return -1;
  const char *component = path + 1;
  while (const char *separator = std::strchr(component, '/')) {
    char name[kPathLimit];
    const std::size_t length = static_cast<std::size_t>(separator - component);
    std::memcpy(name, component, length);
    name[length] = '\0';
    const int next = ::openat(directory, name,
                              O_RDONLY | O_DIRECTORY | O_CLOEXEC | O_NOFOLLOW);
    const int closed = ::close(directory);
    if (next < 0 || closed != 0) {
      if (next >= 0) (void)::close(next);
      return -1;
    }
    directory = next;
    component = separator + 1;
  }
  *leaf = component;
  return directory;
}

bool regular_witness(const struct stat &info, off_t size) {
  return S_ISREG(info.st_mode) && info.st_nlink == 1 &&
         (info.st_mode & 07777) == 0600 && info.st_size == size;
}

bool unchanged_path(const char *path, const Output &output) {
  const char *leaf = nullptr;
  const int parent = open_parent(path, &leaf);
  if (parent < 0) return false;
  struct stat info {};
  const bool same = ::fstatat(parent, leaf, &info, AT_SYMLINK_NOFOLLOW) == 0 &&
                    same_file(info, output.identity) &&
                    regular_witness(info, output.identity.st_size);
  const int closed = ::close(parent);
  return same && closed == 0;
}
}  // namespace

void nova_htif_observe_stop(const void *instance, bool present,
                            int raw_exit_code, bool signal_exit) {
  (void)instance;
  if (called.test_and_set(std::memory_order_relaxed)) fatal();

  const char *path = std::getenv("NOVA_HTIF_WITNESS_PATH");
  const char *run_id = std::getenv("NOVA_HTIF_RUN_ID");
  const char *binding = std::getenv("NOVA_HTIF_BINDING_SHA256");
  // Validate every environment value before creating any output.
  if (!valid_path(path) || !hex64(run_id) || !hex64(binding)) fatal();

  char raw[32] = "null";
  char decoded[32] = "null";
  if (present) {
    // Defined arithmetic right shift, including malformed negative raw values.
    // Validation of a target-originated odd positive value belongs to the reader.
    const int target = raw_exit_code / 2 -
                       (raw_exit_code < 0 && raw_exit_code % 2 != 0 ? 1 : 0);
    (void)std::snprintf(raw, sizeof(raw), "%d", raw_exit_code);
    (void)std::snprintf(decoded, sizeof(decoded), "%d", target);
  }
  char record[512];
  const int count = std::snprintf(
      record, sizeof(record),
      "{\"schema_version\":1,\"kind\":\"nova-htif-exit\",\"run_id\":\"%s\","
      "\"binding_sha256\":\"%s\",\"target_exit_present\":%s,\"raw_exit_code\":%s,"
      "\"target_exit_code\":%s,\"signal_exit\":%s}\n",
      run_id, binding, present ? "true" : "false", raw, decoded,
      signal_exit ? "true" : "false");
  if (count <= 0 || static_cast<std::size_t>(count) >= sizeof(record) ||
      static_cast<std::size_t>(count) > kWitnessLimit) fatal();

  Output output;
  output.parent = open_parent(path, &output.leaf);
  if (output.parent < 0) fatal();
  output.file = ::openat(output.parent, output.leaf,
                         O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW | O_CLOEXEC,
                         0600);
  if (output.file < 0) fatal(&output);
  if (::fstat(output.file, &output.identity) != 0) fatal(&output);
  output.identified = true;
  if (!S_ISREG(output.identity.st_mode) || output.identity.st_nlink != 1 ||
      output.identity.st_size != 0 || ::fchmod(output.file, 0600) != 0) {
    fatal(&output);
  }

  std::size_t offset = 0;
  const std::size_t size = static_cast<std::size_t>(count);
  while (offset != size) {
    const ssize_t written = ::write(output.file, record + offset, size - offset);
    if (written > 0 && static_cast<std::size_t>(written) <= size - offset) {
      offset += static_cast<std::size_t>(written);
    } else if (written != -1 || errno != EINTR) {
      fatal(&output);
    }
  }
  if (::fsync(output.file) != 0) fatal(&output);
  struct stat final_info {};
  if (::fstat(output.file, &final_info) != 0 ||
      !same_file(output.identity, final_info) ||
      !regular_witness(final_info, static_cast<off_t>(size))) fatal(&output);
  output.identity = final_info;
  if (!unchanged_path(path, output)) fatal(&output);

  // Never retry close(): on Linux the descriptor is released even when close
  // reports EINTR/EIO, and retrying could close a reused descriptor.
  const int file = output.file;
  output.file = -1;
  if (::close(file) != 0) fatal(&output);
  const int parent = output.parent;
  output.parent = -1;
  if (::close(parent) != 0) fatal(&output);
}
