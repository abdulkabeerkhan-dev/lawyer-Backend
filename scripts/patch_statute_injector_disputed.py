"""
scripts/patch_statute_injector_disputed.py
Reorders the disputed/extraction_disputed check before the unsourced check in legal_ai/statutes/statute_injector.py
"""

with open("legal_ai/statutes/statute_injector.py", "r", encoding="utf-8") as f:
    text = f.read()

target = """            # Check unsourced tier / quoting blocked gating (Order 1.4 Item 1)
            elif tier == "unsourced" or in_force == "unknown" or (rec and rec.get("quoting_allowed") is False):
                lines.append("********************************************************************************")
                lines.append(f"CRITICAL REFUSAL: {display_name} HAS NO SOURCED OFFICIAL PDF IN REPOSITORY (TIER: UNSOURCED).")
                lines.append("The engine strictly blocks quoting or applying unverified/unsourced statutory text.")
                lines.append("You MUST output '[Statutory text unverified / unsourced: quoting strictly blocked]' under Section 2 instead.")
                lines.append("********************************************************************************")
                raw_text = ""

            # Check disputed tier warning gating (Item 8 & Item 10)
            elif tier == "disputed":
                lines.append("********************************************************************************")
                lines.append(f"CRITICAL WARNING: {display_name} IS TAGGED AS DISPUTED IN OFFICIAL STORE.")
                lines.append("Reason: Text not yet checked against page images by a human.")
                lines.append("Do NOT print any '> [!' banner yourself. System banners are attached automatically after verification.")
                lines.append("Human advocate verification against official Gazette page images is required before relying on this text.")
                lines.append("********************************************************************************")"""

replacement = """            # Check disputed tier warning gating (Item 8 & Item 10)
            elif tier in ("disputed", "extraction_disputed"):
                lines.append("********************************************************************************")
                lines.append(f"CRITICAL WARNING: {display_name} IS TAGGED AS DISPUTED IN OFFICIAL STORE.")
                lines.append("Reason: Text not yet checked against page images by a human.")
                lines.append("Do NOT print any '> [!' banner yourself. System banners are attached automatically after verification.")
                lines.append("Human advocate verification against official Gazette page images is required before relying on this text.")
                lines.append("********************************************************************************")

            # Check unsourced tier / quoting blocked gating (Order 1.4 Item 1)
            elif tier == "unsourced" or in_force == "unknown" or (rec and rec.get("quoting_allowed") is False):
                lines.append("********************************************************************************")
                lines.append(f"CRITICAL REFUSAL: {display_name} HAS NO SOURCED OFFICIAL PDF IN REPOSITORY (TIER: UNSOURCED).")
                lines.append("The engine strictly blocks quoting or applying unverified/unsourced statutory text.")
                lines.append("You MUST output '[Statutory text unverified / unsourced: quoting strictly blocked]' under Section 2 instead.")
                lines.append("********************************************************************************")
                raw_text = "" """

# Normalize CRLF
text_norm = text.replace("\r\n", "\n")
target_norm = target.replace("\r\n", "\n")
replacement_norm = replacement.replace("\r\n", "\n")

if target_norm in text_norm:
    new_text = text_norm.replace(target_norm, replacement_norm, 1)
    with open("legal_ai/statutes/statute_injector.py", "w", encoding="utf-8") as f:
        f.write(new_text)
    print("SUCCESS: Reordered disputed tier check in statute_injector.py")
else:
    print("ERROR: Target block not found in statute_injector.py")
