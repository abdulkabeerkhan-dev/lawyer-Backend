"""
scripts/patch_pdf_dev_bypass.py
Adds dev bypass condition to _authorize_pdf_access in main.py
"""

with open("main.py", "r", encoding="utf-8") as f:
    text = f.read()

target = """    # Option 2: Clerk session authentication
    if not caller_identifier:
        if credentials and credentials.credentials:
            caller_identifier = await verify_clerk_session(credentials)
        else:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Access Denied: Missing authorization credentials or signed PDF token."
            )"""

replacement = """    # Option 2: Clerk session authentication
    if not caller_identifier:
        if credentials and credentials.credentials:
            caller_identifier = await verify_clerk_session(credentials)
        elif os.environ.get("ENVIRONMENT") != "production" or os.environ.get("ENABLE_DEV_AUTH_BYPASS", "").lower() == "true":
            caller_identifier = "dev_bypass_user"
        else:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Access Denied: Missing authorization credentials or signed PDF token."
            )"""

text_norm = text.replace("\r\n", "\n")
target_norm = target.replace("\r\n", "\n")
replacement_norm = replacement.replace("\r\n", "\n")

if target_norm in text_norm:
    new_text = text_norm.replace(target_norm, replacement_norm, 1)
    with open("main.py", "w", encoding="utf-8") as f:
        f.write(new_text)
    print("SUCCESS: Added dev auth bypass to _authorize_pdf_access in main.py")
else:
    print("WARNING: target not found in main.py")
