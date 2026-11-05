-- Execute in Supabase SQL editor or psql as the project owner. All fixtures roll back.
BEGIN;
DO $$
DECLARE
  first_user text := gen_random_uuid()::text;
  second_user text := gen_random_uuid()::text;
  first_room text := gen_random_uuid()::text;
  second_room text := gen_random_uuid()::text;
  visible_count integer;
BEGIN
  INSERT INTO public.rooms(id,name) VALUES(first_room,'__rls_fixture_one'),(second_room,'__rls_fixture_two');
  INSERT INTO public.room_members(room_id,user_id,role) VALUES(first_room,first_user,'admin'),(second_room,second_user,'reviewer');
  PERFORM set_config('request.jwt.claim.sub',first_user,true);
  SET LOCAL ROLE authenticated;
  SELECT count(*) INTO visible_count FROM public.rooms WHERE name LIKE '__rls_fixture%';
  ASSERT visible_count=1, 'RLS leaked a room';
  SELECT count(*) INTO visible_count FROM public.room_members WHERE user_id=second_user;
  ASSERT visible_count=0, 'RLS leaked membership';
  BEGIN
    PERFORM token_hash FROM public.devices;
    RAISE EXCEPTION 'Device token hashes are readable';
  EXCEPTION WHEN insufficient_privilege THEN NULL;
  END;
  BEGIN
    PERFORM transcript_raw FROM public.speech_segments;
    RAISE EXCEPTION 'Speech must be API-only';
  EXCEPTION WHEN insufficient_privilege THEN NULL;
  END;
  BEGIN
    INSERT INTO public.rooms(id,name) VALUES(gen_random_uuid()::text,'forbidden');
    RAISE EXCEPTION 'Browser writes should be denied';
  EXCEPTION WHEN insufficient_privilege THEN NULL;
  END;
  RESET ROLE;
END $$;
SELECT 'RLS isolation checks passed; fixtures rolled back' AS result;
ROLLBACK;
