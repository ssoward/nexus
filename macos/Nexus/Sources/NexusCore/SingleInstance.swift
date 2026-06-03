import Foundation

/// Process-wide single-instance guard backed by an advisory file lock (flock).
/// Works regardless of launch method (`open` of the .app vs. launchd exec'ing the
/// inner binary directly), unlike bundle-identifier checks which can differ between them.
public enum SingleInstance {
    /// Attempts to become the sole instance by taking a non-blocking exclusive lock.
    /// Returns true if acquired (this is the only instance). On success the file
    /// descriptor is intentionally kept open for the process lifetime to hold the lock.
    /// If the lock file can't be opened at all, returns true (never block startup).
    public static func acquire(lockPath: String) -> Bool {
        let fd = open(lockPath, O_CREAT | O_RDWR, 0o600)
        if fd < 0 { return true }
        if flock(fd, LOCK_EX | LOCK_NB) != 0 {
            close(fd)        // another instance holds it
            return false
        }
        // Deliberately leak `fd`: the lock is released when the process exits.
        return true
    }
}
