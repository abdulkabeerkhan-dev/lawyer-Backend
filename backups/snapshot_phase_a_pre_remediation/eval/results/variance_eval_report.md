# Empirical Multi-Run Variance Evaluation Report (3 Runs)

- **Git Commit**: `51def047e252ee5006aa8ac2e1ccf1edb3d61582`
- **Generator Model**: `claude-haiku-4-5-20251001`
- **LLM Judge Model**: `claude-haiku-4-5-20251001`
- **Evaluated**: 7 Dev Cases across 3 independent runs (21 total executions)

## 1. Variance Summary Across 3 Runs (Mean & Range)

| Metric | Run 1 | Run 2 | Run 3 | Mean | Range (Min - Max) |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Overall Pass Rate** | 42.9% | 28.6% | 28.6% | **33.3%** | 28.6% - 42.9% |
| **Key Authority Recall** | 92.9% | 92.9% | 78.6% | **88.1%** | 78.6% - 92.9% |
| **Claim Support Rate** | 78.1% | 72.4% | 73.3% | **74.6%** | 72.4% - 78.1% |
| **Citation Precision** | 100.0% | 100.0% | 100.0% | **100.0%** | 100.0% - 100.0% |
| **Forum & Limitation Accuracy** | 100.0% | 100.0% | 100.0% | **100.0%** | 100.0% - 100.0% |
| **Currency Label Coverage** | 100.0% | 100.0% | 100.0% | **100.0%** | 100.0% - 100.0% |
| **Scope Violations Count** | 2 | 2 | 5 | **3.0** | 2.0000 - 5.0000 |
| **Cases With No Usable Memo** | 0 | 0 | 0 | **0.0** | 0.0000 - 0.0000 |
| **Average Latency (s)** | 157.96 | 148.25 | 144.45 | **150.22** | 144.4500 - 157.9600 |

## 2. Per-Case Consistency Across Runs

| Case ID | Legal Area | Pass Consistency | Run 1 Pass | Run 2 Pass | Run 3 Pass | Notes / Failure Reasons |
| :--- | :--- | :---: | :---: | :---: | :---: | :--- |
| **GS-001** | Civil execution & recovery | **0/3** | FAIL | FAIL | FAIL | Claim support rate 50.0% below 80%; Scope violations: ["Labelling Lahore High Court decisions 'Supreme Court'."] |
| **GS-002** | Family & succession | **0/3** | FAIL | FAIL | FAIL | Scope violations: ["Calling a headnote-only record 'the latest appellate authority' or telling the lawyer to 'rely confidently' on it."]; Claim support rate 60.0% below 80% |
| **GS-003** | Banking & finance | **1/3** | PASS | FAIL | FAIL | Deterministic violations: ['ultra vires']; Scope violations: ["Calling a 50% direction 'ultra vires' or 'unlawful' unless a retrieved source says so."] |
| **GS-004** | Civil procedure | **3/3** | PASS | PASS | PASS | None |
| **GS-005** | Agency & power of attorney | **0/3** | FAIL | FAIL | FAIL | Key authority recall 0.0% below 50%; Scope violations: ["Listing PLD 2003 SC 31 as 'reviewed' when it is only cited within another judgment."]; Claim support rate 50.0% below 80% |
| **GS-006** | Arbitration | **3/3** | PASS | PASS | PASS | None |
| **GS-007** | Constitutional & writs | **0/3** | FAIL | FAIL | FAIL | Scope violations: ['Presenting the 2025 majority as the unqualified present law of Art. 200.']; Claim support rate 33.3% below 80%; Claim support rate 66.7% below 80% |
