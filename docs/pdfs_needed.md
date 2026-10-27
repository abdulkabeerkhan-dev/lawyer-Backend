# Missing Official Gazette PDFs Needed for Ingestion

The following statutory enactments are referenced in the legal intelligence pipeline and test suites, but lack authenticated official Gazette PDFs in `data/official_pdfs/`.

Per Order 2.0 instructions, no files are to be downloaded automatically. The human reviewer will obtain authenticated Gazette prints from the Directorate of Printing, Government of Pakistan, or official National Assembly/Senate gazette publications, place them in `data/official_pdfs/`, and compute their SHA-256 hashes.

## Required Official PDFs Inventory

| Act / Ordinance / Order | Short Code | Expected File Name | Target Destination | Sourced Authority / Citation |
|---|---|---|---|---|
| **Constitution of the Islamic Republic of Pakistan, 1973** | `CONSTITUTION_1973` | `constitution_1973.pdf` | `data/official_pdfs/` | As amended up to 26th Amendment |
| **Negotiable Instruments Act, 1881** | `NI_ACT_1881` | `negotiable_instruments_act_1881.pdf` | `data/official_pdfs/` | Act XXVI of 1881 |
| **Qanun-e-Shahadat Order, 1984** | `QSO_1984` | `qanun_e_shahadat_1984.pdf` | `data/official_pdfs/` | P.O. No. X of 1984 |
| **Income Tax Ordinance, 2001** | `ITO_2001` | `income_tax_ordinance_2001.pdf` | `data/official_pdfs/` | Ordinance XLIX of 2001 |
| **Specific Relief Act, 1877** | `SRA_1877` | `specific_relief_act_1877.pdf` | `data/official_pdfs/` | Act I of 1877 |
| **Companies Act, 2017** | `COMPANIES_ACT_2017` | `companies_act_2017.pdf` | `data/official_pdfs/` | Act XIX of 2017 |
| **Constitution (Twenty-sixth Amendment) Act, 2026** | `ACT_XLVI_2026` | `act_xlvi_of_2026.pdf` | `data/official_pdfs/` | Act XLVI of 2026 (Gazette of Pakistan) |
| **Prevention of Electronic Crimes Act, 2016** | `PECA_2016` | `peca_2016.pdf` | `data/official_pdfs/` | Act XL of 2016 |
| **Anti-Money Laundering Act, 2010** | `AMLA_2010` | `anti_money_laundering_act_2010.pdf` | `data/official_pdfs/` | Act VII of 2010 |
| **Arbitration Act, 1940** | `ARBITRATION_1940` | `arbitration_act_1940.pdf` | `data/official_pdfs/` | Act X of 1940 |
| **Muslim Family Laws Ordinance, 1961** | `MFLO_1961` | `muslim_family_laws_ordinance_1961.pdf` | `data/official_pdfs/` | Ordinance VIII of 1961 |
| **West Pakistan Land Revenue Act, 1967** | `LAND_REVENUE_1967` | `land_revenue_act_1967.pdf` | `data/official_pdfs/` | W.P. Act XVII of 1967 |
| **Control of Narcotic Substances Act, 1997** | `CNSA_1997` | `control_of_narcotic_substances_act_1997.pdf` | `data/official_pdfs/` | Act XXV of 1997 |

## Verification Protocol Upon Receipt
When each official PDF is supplied:
1. Verify Gazette provenance (Printing Corporation of Pakistan / official Government gazette seal).
2. Compute file hash: `Get-FileHash data\official_pdfs\<filename>.pdf -Algorithm SHA256`.
3. Run the dual-extractor pipeline (`scripts/extract_statutes_v2.py`).
4. Re-run verification suite and verify agreement across extractors.
