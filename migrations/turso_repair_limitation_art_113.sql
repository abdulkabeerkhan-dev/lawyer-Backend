-- Remove a corrupted First Schedule table merge from the non-verbatim Turso
-- statute record. Article 113 remains in the local structured table store as a
-- non-quotable summary until its bare-act wording is verified from an official
-- source.
UPDATE statute_provisions
SET verbatim_text = '',
    tier = 'ingested_unreviewed'
WHERE canonical_id = 'LIMITATION_1908_ART_113'
  AND instr(verbatim_text, 'Part VI') > 0
  AND instr(verbatim_text, 'Part VII') > 0
  AND instr(verbatim_text, 'Part VIII') > 0;
