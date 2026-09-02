import re
import unicodedata

class PakistaniLegalTextCleaner:
    def __init__(self):
        # 1. Official Court Stamps, Seals & Registry Signatures
        self.stamp_patterns = [
            r'(?i)certi[a-z0-9\s\.\-_]*copy.*?(islamabad|lahore|karachi|peshawar|quetta|court)?',
            r'(?i)court\s+associate[\s\w\.\-]*(islamabad|lahore|karachi|peshawar|quetta)?',
            r'(?i)assistant\s+registrar[\s\w\.\-]*',
            r'(?i)reader\s+to\s+(the\s+)?hon[\'’]?ble\s+judge[\s\w\.\-]*',
            r'(?i)superintendent[\s\w\.\-]*copying\s+branch',
            r'(?i)private\s+secretary[\s\w\.\-]*',
            r'(?i)bench\s+reader[\s\w\.\-]*',
            r'(?i)examined\s+by[\s\w\.\-]*',
            r'(?i)compared\s+by[\s\w\.\-]*',
            r'(?i)certified\s+to\s+be\s+true\s+copy',
        ]

        # 2. Page Margins, Watermarks & Reporting Banners
        self.banner_patterns = [
            r'(?i)(not\s+approved\s+for\s+reporting|approved\s+for\s+reporting)',
            r'(?i)page\s+\d+\s+(of|\/)\s+\d+',
            r'(?i)digitized\s+by\s+.*',
            r'(?i)downloaded\s+from\s+.*',
            r'(?i)pakistan\s*[-_]?\s*law\s*[-_]?\s*site',
            r'(?i)pls\s+citation\s+.*',
            r'(?i)tajamul\s*\/[\s\w\*\.\|]*',
            r'(?i)aftab\s+p\.s\s*\/[\s\w\*\.\|]*',
            r'(?i)\(s\.b\.?\)\s*hon[\'’]?ble\s+mr\.\s+justice.*',
        ]

        # 3. Known OCR misreads of Pakistani legal terms & spaced abbreviations
        self.typo_corrections = [
            (r'(?i)\bSupreme\s+Cour[!\?1l]\b', 'Supreme Court'),
            (r'(?i)\bHigh\s+Cour[!\?1l]\b', 'High Court'),
            (r'(?i)\bP\s+L\s+D\b', 'PLD'),
            (r'(?i)\bS\s+C\s+M\s+R\b', 'SCMR'),
            (r'(?i)\bM\s+L\s+D\b', 'MLD'),
            (r'(?i)\bC\s+L\s+C\b', 'CLC'),
            (r'(?i)\bP\s+C\s+R\s+L\s+J\b', 'PCrLJ'),
            (r'(?i)\bCr\.?\s*P\.?\s*C\b', 'Cr.P.C'),
            (r'(?i)\bC\.?\s*P\.?\s*C\b', 'C.P.C'),
            (r'(?i)\bP\.?\s*P\.?\s*C\b', 'P.P.C'),
            (r'(?i)\bQ\.?\s*S\.?\s*O\b', 'Q.S.O'),
            (r'(?i)\bS\.?\s*R\.?\s*A\b', 'S.R.A'),
        ]

    def clean(self, raw_text: str) -> str:
        if not raw_text:
            return ""

        # Normalize Unicode characters (accents, curly quotes, odd spaces)
        text = unicodedata.normalize("NFKD", raw_text)
        text = text.replace('\r\n', '\n').replace('\r', '\n')

        # Strip Urdu script blocks and non-Latin garbled OCR Mojibake
        text = re.sub(r'[\u0600-\u06FF\u0750-\u077F\uFB50-\uFDFF\uFE70-\uFEFF]+', ' ', text)

        # 1. Remove stamps, registry markers, and banners
        for pat in self.stamp_patterns + self.banner_patterns:
            text = re.sub(pat, ' ', text)

        # 2. Fix OCR hyphenated line wraps (e.g. "con-\n sideration" -> "consideration")
        text = re.sub(r'(\w+)-\s*\n\s*(\w+)', r'\1\2', text)

        # 3. Fix fragmented single-line wraps inside continuous paragraphs
        lines = text.split('\n')
        merged_lines = []
        buffer = ""

        for line in lines:
            line_str = line.strip()
            if not line_str:
                if buffer:
                    merged_lines.append(buffer)
                    buffer = ""
                continue

            # Skip party address list dumps (e.g. "12. 13. 14. Raja Sajid S/o... ID Card No...")
            if re.search(r'(?i)\b(S\/o|D\/o|W\/o|R\/o|ID Card No\.?|P\.O\b|Tehsil|District)\b', line_str) and len(re.findall(r'\b\d+\.\b', line_str)) >= 2:
                continue

            # Strip noisy edge artifacts (e.g. '| [Saye J', '[Annexure]', random symbols)
            line_str = re.sub(r'^[\|\[\]\(\)\-\—\_\:\;\.\,\s]+', '', line_str)
            line_str = re.sub(r'[\|\[\]\(\)\-\—\_\:\;\.\,\s]+$', '', line_str)

            # Drop lines that are pure symbol noise or scanner edge artifacts
            alphanumeric = re.findall(r'[a-zA-Z0-9]', line_str)
            words = line_str.split()

            # Rule: Skip if line has too few alphanumeric chars or too many broken 1-2 char fragments
            if len(words) > 3:
                short_broken = [w for w in words if len(w) <= 2 and not w.isalnum()]
                if len(short_broken) / len(words) > 0.4:
                    continue
            if len(alphanumeric) < 3 and len(line_str) > 3:
                continue

            # Buffer continuation logic
            if buffer:
                if buffer[-1] in '.?!:':
                    merged_lines.append(buffer)
                    buffer = line_str
                else:
                    buffer += " " + line_str
            else:
                buffer = line_str

        if buffer:
            merged_lines.append(buffer)

        cleaned_text = '\n\n'.join(merged_lines)

        # 4. Apply specific legal keyword corrections
        for pattern, replacement in self.typo_corrections:
            cleaned_text = re.sub(pattern, replacement, cleaned_text)

        # 5. Clean excessive spaces
        cleaned_text = re.sub(r'[ \t]+', ' ', cleaned_text)
        cleaned_text = re.sub(r'\n{3,}', '\n\n', cleaned_text)

        return cleaned_text.strip()


legal_cleaner = PakistaniLegalTextCleaner()
