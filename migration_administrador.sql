BEGIN;

ALTER TABLE public.professor
    ADD COLUMN IF NOT EXISTS is_admin BOOLEAN NOT NULL DEFAULT FALSE;

UPDATE public.professor
SET is_admin = TRUE
WHERE LOWER(email) = LOWER('phfe1997@gmail.com');

COMMIT;
