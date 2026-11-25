// Native host fixture for the real NOVA recorder. This does not execute RTL,
// HTIF, RISC-V code, or a CPU simulator. Fault hooks are linked only in tests.
#include "nova_htif_exit.h"

#include <algorithm>
#include <cerrno>
#include <climits>
#include <cstdarg>
#include <cstdio>
#include <cstdlib>
#include <cstring>

#include <fcntl.h>
#include <signal.h>
#include <sys/resource.h>
#include <sys/stat.h>
#include <unistd.h>

namespace {
const char *fault = "none";
int witness = -1;
int witness_parent = -1;
char witness_leaf[4096];
unsigned int writes = 0;
unsigned int diagnostic_writes = 0;
unsigned int stats = 0;
bool cleanup_started = false;
bool is_fault(const char *name) { return std::strcmp(fault, name) == 0; }

void fixture_check(bool condition) {
  if (!condition) std::_Exit(98);
}
}  // namespace

extern "C" {
int __real_openat(int directory, const char *path, int flags, ...);
ssize_t __real_write(int descriptor, const void *buffer, size_t size);
int __real_fsync(int descriptor);
int __real_fstat(int descriptor, struct stat *info);
int __real_fstatat(int directory, const char *path, struct stat *info, int flags);
int __real_ftruncate(int descriptor, off_t size);
int __real_fchmod(int descriptor, mode_t mode);
int __real_close(int descriptor);

int __wrap_openat(int directory, const char *path, int flags, ...) {
  int result;
  if ((flags & O_CREAT) != 0) {
    va_list args;
    va_start(args, flags);
    const int mode = va_arg(args, int);
    va_end(args);
    result = __real_openat(directory, path, flags, mode);
  } else {
    result = __real_openat(directory, path, flags);
  }
  if (result >= 0 && (flags & O_CREAT) != 0 && (flags & O_EXCL) != 0) {
    witness = result;
    witness_parent = directory;
    std::snprintf(witness_leaf, sizeof(witness_leaf), "%s", path);
    if (is_fault("early-hardlink")) {
      fixture_check(::linkat(directory, path, directory, "native-extra-link", 0) == 0);
    }
  }
  return result;
}

ssize_t __wrap_write(int descriptor, const void *buffer, size_t size) {
  if (descriptor == STDERR_FILENO) {
    ++diagnostic_writes;
    if (is_fault("stderr-eintr-always") ||
        (is_fault("stderr-eintr") && diagnostic_writes == 1)) {
      errno = EINTR;
      return -1;
    }
    if (is_fault("stderr-short-write")) size = std::min<size_t>(size, 7);
  }
  if (descriptor == witness) {
    ++writes;
    if (is_fault("write-error") ||
        (is_fault("partial-write-error") && writes > 1)) {
      errno = EIO;
      return -1;
    }
    if (is_fault("write-zero")) return 0;
    if (is_fault("write-eintr") && writes == 1) {
      errno = EINTR;
      return -1;
    }
    if (is_fault("short-write")) size = std::min<size_t>(size, 7);
    if (is_fault("partial-write-error")) size = std::min<size_t>(size, 17);
  }
  return __real_write(descriptor, buffer, size);
}

int __wrap_fsync(int descriptor) {
  if (descriptor == witness && (is_fault("fsync-error") ||
                                is_fault("replace-after-cleanup-stat") ||
                                is_fault("replace-during-truncate"))) {
    cleanup_started = true;
    errno = EIO;
    return -1;
  }
  const int result = __real_fsync(descriptor);
  if (descriptor != witness || result != 0) return result;
  if (is_fault("late-hardlink")) {
    fixture_check(::linkat(witness_parent, witness_leaf, witness_parent,
                           "native-extra-link", 0) == 0);
  } else if (is_fault("replace-leaf")) {
    fixture_check(::unlinkat(witness_parent, witness_leaf, 0) == 0);
    const int foreign = __real_openat(witness_parent, witness_leaf,
                                      O_WRONLY | O_CREAT | O_EXCL, 0600);
    fixture_check(foreign >= 0);
    constexpr char replacement[] = "foreign replacement\n";
    fixture_check(__real_write(foreign, replacement, sizeof(replacement) - 1) ==
                  static_cast<ssize_t>(sizeof(replacement) - 1));
    fixture_check(__real_close(foreign) == 0);
  } else if (is_fault("late-mode-change")) {
    fixture_check(__real_fchmod(witness, 0644) == 0);
  } else if (is_fault("replace-parent-with-symlink")) {
    char parent[4096];
    char moved[4103];
    std::snprintf(parent, sizeof(parent), "%s", std::getenv("NOVA_HTIF_WITNESS_PATH"));
    char *separator = std::strrchr(parent, '/');
    fixture_check(separator != nullptr && separator != parent);
    *separator = '\0';
    std::snprintf(moved, sizeof(moved), "%s.moved", parent);
    fixture_check(::rename(parent, moved) == 0);
    fixture_check(::symlink(moved, parent) == 0);
  }
  return result;
}

int __wrap_fstat(int descriptor, struct stat *info) {
  if (descriptor == witness && ++stats > 1 && is_fault("fstat-error")) {
    errno = EIO;
    return -1;
  }
  return __real_fstat(descriptor, info);
}

int __wrap_fstatat(int directory, const char *path, struct stat *info, int flags) {
  const int result = __real_fstatat(directory, path, info, flags);
  if (result == 0 && cleanup_started && is_fault("replace-after-cleanup-stat") &&
      directory == witness_parent && std::strcmp(path, witness_leaf) == 0) {
    // Reproduce a replacement after a cleanup identity check, immediately
    // before a subsequent pathname unlink would delete the foreign inode.
    fixture_check(::renameat(directory, "foreign.txt", directory, path) == 0);
  }
  return result;
}

int __wrap_ftruncate(int descriptor, off_t size) {
  if (descriptor == witness && is_fault("replace-during-truncate")) {
    // Keep an alias of the owned inode so the test can observe its invalidation
    // while a foreign inode is installed at the original witness pathname.
    fixture_check(::renameat(witness_parent, witness_leaf, witness_parent,
                              "native-displaced-witness") == 0);
    fixture_check(::renameat(witness_parent, "foreign.txt", witness_parent,
                              witness_leaf) == 0);
  }
  return __real_ftruncate(descriptor, size);
}

int __wrap_fchmod(int descriptor, mode_t mode) {
  if (descriptor == witness && is_fault("fchmod-error")) {
    errno = EPERM;
    return -1;
  }
  return __real_fchmod(descriptor, mode);
}

int __wrap_close(int descriptor) {
  const bool is_witness = descriptor == witness;
  if (is_witness) witness = -1;
  const int result = __real_close(descriptor);
  if (is_witness && (is_fault("close-error") || is_fault("close-eintr"))) {
    errno = is_fault("close-eintr") ? EINTR : EIO;
    return -1;
  }
  return result;
}
}  // extern "C"

int main(int argc, char **argv) {
  if (argc != 3) return 97;
  const char *mode = argv[1];
  fault = argv[2];
  if (is_fault("kernel-write-error")) {
    // This fixture-only limit causes a real write(2) EFBIG after one byte.
    fixture_check(::signal(SIGXFSZ, SIG_IGN) != SIG_ERR);
    const struct rlimit limit {1, 1};
    fixture_check(::setrlimit(RLIMIT_FSIZE, &limit) == 0);
  }
  if (is_fault("restrictive-umask")) (void)::umask(0777);
  bool present = true;
  bool signal_exit = false;
  int raw = 1;
  if (std::strcmp(mode, "negative-control") == 0) raw = 15;
  else if (std::strcmp(mode, "absent") == 0) { present = false; raw = 123; }
  else if (std::strcmp(mode, "signal") == 0) { present = false; signal_exit = true; }
  else if (std::strcmp(mode, "target-and-signal") == 0) signal_exit = true;
  else if (std::strcmp(mode, "raw-zero") == 0) raw = 0;
  else if (std::strcmp(mode, "raw-even") == 0) raw = 14;
  else if (std::strcmp(mode, "raw-negative") == 0) raw = -1;
  else if (std::strcmp(mode, "raw-max") == 0) raw = INT_MAX;
  else if (std::strcmp(mode, "raw-min") == 0) raw = INT_MIN;
  else if (std::strcmp(mode, "positive") != 0 &&
           std::strcmp(mode, "duplicate") != 0 &&
           std::strcmp(mode, "second-instance") != 0) return 96;
  int first_instance = 0;
  int second_instance = 0;
  nova_htif_observe_stop(&first_instance, present, raw, signal_exit);
  if (std::strcmp(mode, "duplicate") == 0) {
    nova_htif_observe_stop(&first_instance, true, 1, false);
  } else if (std::strcmp(mode, "second-instance") == 0) {
    nova_htif_observe_stop(&second_instance, true, 1, false);
  }
  return 0;
}
