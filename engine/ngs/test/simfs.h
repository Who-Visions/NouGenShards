/* SPDX-License-Identifier: Apache-2.0 */
/*
** simfs.h -- an in-memory filesystem behind the NGS platform interface, for the crash harness.
**
** Durability model (deliberately unkind):
**   * A file has volatile content (what the running process sees) and durable content (what a
**     power cut leaves). pwrite changes only the volatile side and marks 512-byte sectors dirty.
**     fsync copies volatile to durable. A crash keeps each dirty sector with probability keep_pct,
**     independently, so un-synced writes reach the disk in any order. A length change that was not
**     synced may or may not survive.
**   * A directory entry (create, rename, unlink) is durable only after fsync_dir of its directory.
**     A crash applies a random prefix of the pending directory operations.
**   * Directories themselves (mkdir) are durable immediately.
**
** Faults: arm a crash at the Nth state-changing call (open-with-create, pwrite, fsync, truncate,
** rename, unlink, mkdir, fsync_dir). After a crash every call returns NGS_IOERR (the process is
** dead). A plain failure returns NGS_IOERR for one call and lets the process go on.
*/
#ifndef SIMFS_H
#define SIMFS_H

#include "plat.h"

#include <stddef.h>
#include <stdint.h>

typedef struct sim sim;

#define SIM_BEFORE  0   /* the call has no effect, then the process dies */
#define SIM_PARTIAL 1   /* pwrite lands a random prefix; any other call behaves as SIM_BEFORE */
#define SIM_AFTER   2   /* the call takes full effect, then the process dies before returning */

/* kinds of numbered, state-changing calls */
#define SIMK_OPEN 1
#define SIMK_PWRITE 2
#define SIMK_FSYNC 3
#define SIMK_TRUNCATE 4
#define SIMK_RENAME 5
#define SIMK_UNLINK 6
#define SIMK_MKDIR 7
#define SIMK_FSYNCDIR 8
int      sim_op_kind(sim *s, uint64_t op);          /* kind of the Nth call of the last run, 0 if none */

sim     *sim_new(uint64_t seed);
void     sim_free(sim *s);
ngs_vfs *sim_vfs(sim *s);

void     sim_reset_ops(sim *s);
uint64_t sim_ops(sim *s);
void     sim_arm_crash(sim *s, uint64_t op, int variant);   /* op is 1-based; 0 disarms */
void     sim_arm_fail(sim *s, uint64_t op);
int      sim_crashed(sim *s);

/* power loss and reboot: the process is gone, the disk keeps what the model says it keeps */
void     sim_reboot(sim *s, uint64_t seed, int keep_pct, int ns_keep_pct);
/* clean shutdown: everything volatile becomes durable */
void     sim_clean_shutdown(sim *s);

/* corruption and inspection (clean_shutdown first so volatile == durable) */
int      sim_flip(sim *s, const char *path, size_t offset, uint8_t xor_mask);
long     sim_file_len(sim *s, const char *path);          /* -1 if missing */
int      sim_truncate_durable(sim *s, const char *path, size_t len);
size_t   sim_count_names(sim *s, const char *dir);        /* entries directly under dir */

#endif /* SIMFS_H */
