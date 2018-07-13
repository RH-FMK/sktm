ALTER TABLE pendingpatches RENAME TO pendingpatches_old;
CREATE TABLE pendingpatches(
  id INTEGER PRIMARY KEY,
  patch_id INTEGER UNIQUE,
  timestamp INTEGER,
  pendingjob_id INTEGER,
  FOREIGN KEY(patch_id) REFERENCES patch(id),
  FOREIGN KEY(pendingjob_id) REFERENCES pendingjobs(id)
);

INSERT INTO pendingpatches (patch_id, timestamp)
        SELECT id, timestamp FROM pendingpatches_old;

DROP TABLE pendingpatches_old;
