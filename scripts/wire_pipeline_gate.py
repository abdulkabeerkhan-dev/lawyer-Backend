import os

repo_dir = r"I:\c\Users\kabeer\Documents\lawyer-Backend-master\lawyer-Backend-master"
main_path = os.path.join(repo_dir, "main.py")
with open(main_path, "rb") as f:
    main_content = f.read()

target_ex = b"        except Exception as e:\r\n\r\n            print(f\"\xe2\x9a\xa0\xef\xb8\x8f [JOB {job_id}] legal_ai pipeline error: {e}. Falling back to legacy pipeline...\", file=sys.stderr, flush=True)"
replacement_ex = (
    b"        except MemorandumVerificationBlockedError as ve:\r\n"
    b"            print(f\"[JOB {job_id}] MEMORANDUM BLOCKED BY VERIFIER: {ve}\", file=sys.stderr, flush=True)\r\n"
    b"            if job_id in jobs_store:\r\n"
    b"                jobs_store[job_id].update({\r\n"
    b"                    'status': 'error',\r\n"
    b"                    'stage': 'verification_blocked',\r\n"
    b"                    'error': 'MEMORANDUM_VERIFICATION_FAILED',\r\n"
    b"                    'result': None,\r\n"
    b"                    'verification_report': ve.verification_report,\r\n"
    b"                    'completed_at': datetime.now(timezone.utc),\r\n"
    b"                })\r\n"
    b"            return\r\n"
    b"        except Exception as e:\r\n\r\n"
    b"            print(f\"\xe2\x9a\xa0\xef\xb8\x8f [JOB {job_id}] legal_ai pipeline error: {e}. Falling back to legacy pipeline...\", file=sys.stderr, flush=True)"
)
if target_ex in main_content:
    main_content = main_content.replace(target_ex, replacement_ex, 1)
    with open(main_path, "wb") as f:
        f.write(main_content)
    print("Wired exception guard in main.py process_query_job")
else:
    print("target_ex already replaced or not found")
