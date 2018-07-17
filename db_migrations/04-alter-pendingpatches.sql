-- NOTE: Apply this change only when no patches are pending.
DROP TABLE pendingpatches;
CREATE TABLE pendingpatches(
  id INTEGER PRIMARY KEY,
  pendingjob_id INTEGER,
  timestamp INTEGER,
  FOREIGN KEY(pendingjob_id) REFERENCES pendingjobs(id)
);
