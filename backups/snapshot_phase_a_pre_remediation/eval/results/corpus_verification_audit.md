# Pakistani Superior Court Corpus Ingestion Verification Audit

- **Audited Records**: 8,000
- **Elapsed Time**: 46.13 seconds
- **Valid Records**: 3,148 (39.4%)
- **Retrievable Records**: 3,148 (39.4%)
- **Headnote-Only (Preserved & Flagged)**: 2,779 (34.7%)
- **Records Lacking Provenance**: 8,000 (100.0%)

## Mismatch Breakdown by Category

| Mismatch Category | Count | Percentage | Description |
| :--- | :--- | :--- | :--- |
| **Court Hierarchy / Name** | 2,087 | 26.09% | Claimed court contradicts document header |
| **Case Title / Parties** | 133 | 1.66% | Party tokens not found in document header |
| **Citation / Reporter** | 3,996 | 49.95% | Journal code or page number not found in header |
| **Decision Year** | 77 | 0.96% | 4-digit decision year not found in header |
| **Missing / Empty Text** | 0 | 0.00% | Text is empty, null, or 'not available' |
| **Editorial / Synthetic Marker** | 0 | 0.00% | Full text begins with unreviewed editorial summary |

## Sample Mismatches for Review (Do Not Auto-Fix)

### Category: COURT (50 samples recorded)

- **Case ID**: `2006_YLR_3082` | **Citation**: `2006 YLR 3082`
  - **Title**: 1061	2006 YLR 3082	IDARA-E-TULOO-E-ISLAM through Chairman VS GOVERNMENT OF SINDH through Chief Secretary, Sindh - Honorable Justice RAHMAT HUSSAIN JAFFERI - Samiuddin Sami , Habib Ahmed	KARACHI-HIGH-COURT-SINDH
  - **Claimed Court**: Supreme Court of Pakistan
  - **Reasons**: Claimed court 'supreme court of pakistan' contradicts document header (Supreme Court not found)., Citation '2006 YLR 3082' (journal 'ylr' or page '3082') not found in header.

- **Case ID**: `2006_YLR_3085` | **Citation**: `2006 YLR 3085`
  - **Title**: 1062	2006 YLR 3085	Syed AHMAD SHAH HASHMI VS State - Honorable Justice Ijaz Ahmad Chaudhry - Zafar Iqbal Chohan , Ms. Raeesa Sarwar	LAHORE-HIGH-COURT-LAHORE
  - **Claimed Court**: Supreme Court of Pakistan
  - **Reasons**: Claimed court 'supreme court of pakistan' contradicts document header (Supreme Court not found)., Citation '2006 YLR 3085' (journal 'ylr' or page '3085') not found in header.

- **Case ID**: `2006_YLR_3087` | **Citation**: `2006 YLR 3087`
  - **Title**: 1063	2006 YLR 3087	KAREEM BUX VS State - Honorable Justice Khiliji Arif Hussain - Muhammad Ayaz Soomro , Muhammad Ismail Bhutto	KARACHI-HIGH-COURT-SINDH
  - **Claimed Court**: High Court of Sindh
  - **Reasons**: Claimed court 'high court of sindh' contradicts document header (High Court not found)., Citation '2006 YLR 3087' (journal 'ylr' or page '3087') not found in header.

- **Case ID**: `2006_YLR_3088` | **Citation**: `2006 YLR 3088`
  - **Title**: 1064	2006 YLR 3088	MANU alias MANTHAR VS State - Honorable Justice Mrs. Qaisar Iqbal - Khadim Hussain D.Solangi , Rasheed A. Qureshi	KARACHI-HIGH-COURT-SINDH
  - **Claimed Court**: High Court of Sindh
  - **Reasons**: Claimed court 'high court of sindh' contradicts document header (High Court not found)., Citation '2006 YLR 3088' (journal 'ylr' or page '3088') not found in header.

- **Case ID**: `2006_YLR_3089` | **Citation**: `2006 YLR 3089`
  - **Title**: 1065	2006 YLR 3089	SAIFULLAH VS State - Honorable Justice Ijaz Ahmad Chaudhry - Kh. Basit Waheed and Rai Haider Ali Khan Kharal , Muhammad Azam, Mian Abdul Qayyum Anjum and Abdul Majeed Chishti	LAHORE-HIGH-COURT-LAHORE
  - **Claimed Court**: Supreme Court of Pakistan
  - **Reasons**: Claimed court 'supreme court of pakistan' contradicts document header (Supreme Court not found)., Citation '2006 YLR 3089' (journal 'ylr' or page '3089') not found in header.

- **Case ID**: `2006_YLR_3094` | **Citation**: `2006 YLR 3094`
  - **Title**: 1066	2006 YLR 3094	ABDUL MAJEED VS State - Honorable Justice Khiliji Arif Hussain - Muhammad Ayaz Soomro , Muhammad Ismail Bhutto	KARACHI-HIGH-COURT-SINDH
  - **Claimed Court**: High Court of Sindh
  - **Reasons**: Claimed court 'high court of sindh' contradicts document header (High Court not found)., Citation '2006 YLR 3094' (journal 'ylr' or page '3094') not found in header.

- **Case ID**: `2006_YLR_3098` | **Citation**: `2006 YLR 3098`
  - **Title**: 1069	2006 YLR 3098	FAROOQ-E-AZAM VS CUSTOMS AND INTELLIGENCE DEPARTMENT - Honorable Justice Syed Zawwar Hussain Jafri - Sohail Muzaffar , Muhammad Shafi Muhammadi	KARACHI-HIGH-COURT-SINDH
  - **Claimed Court**: High Court of Sindh
  - **Reasons**: Claimed court 'high court of sindh' contradicts document header (High Court not found)., Citation '2006 YLR 3098' (journal 'ylr' or page '3098') not found in header.

- **Case ID**: `2006_YLR_3113` | **Citation**: `2006 YLR 3113`
  - **Title**: 1072	2006 YLR 3113	GHULAM AKBER VS State - Honorable Justice Mrs. Yasmin Abbasey - Aamir Mansoob Qureshi , Shahida Jatoi	KARACHI-HIGH-COURT-SINDH
  - **Claimed Court**: High Court of Sindh
  - **Reasons**: Claimed court 'high court of sindh' contradicts document header (High Court not found)., Citation '2006 YLR 3113' (journal 'ylr' or page '3113') not found in header.

- **Case ID**: `2006_YLR_3114` | **Citation**: `2006 YLR 3114`
  - **Title**: 1073	2006 YLR 3114	LIAQAT ALI VS State - Honorable Justice Asif Saeed Khan Khosa - Ijaz Ahmad Khan , Faisal Naseem Chaudhry	LAHORE-HIGH-COURT-LAHORE
  - **Claimed Court**: Supreme Court of Pakistan
  - **Reasons**: Claimed court 'supreme court of pakistan' contradicts document header (Supreme Court not found)., Citation '2006 YLR 3114' (journal 'ylr' or page '3114') not found in header.

- **Case ID**: `2006_YLR_3140` | **Citation**: `2006 YLR 3140`
  - **Title**: 1087	2006 YLR 3140	AKHTIAR ALI VS State - Honorable Justice Azizullah M. Memon - Ali Nawaz Ghanghro , Asif Ali Abdul Razak Soomro	KARACHI-HIGH-COURT-SINDH
  - **Claimed Court**: Supreme Court of Pakistan
  - **Reasons**: Claimed court 'supreme court of pakistan' contradicts document header (Supreme Court not found)., Citation '2006 YLR 3140' (journal 'ylr' or page '3140') not found in header.

### Category: CITATION (50 samples recorded)

- **Case ID**: `2006_YLR_3082` | **Citation**: `2006 YLR 3082`
  - **Title**: 1061	2006 YLR 3082	IDARA-E-TULOO-E-ISLAM through Chairman VS GOVERNMENT OF SINDH through Chief Secretary, Sindh - Honorable Justice RAHMAT HUSSAIN JAFFERI - Samiuddin Sami , Habib Ahmed	KARACHI-HIGH-COURT-SINDH
  - **Claimed Court**: Supreme Court of Pakistan
  - **Reasons**: Claimed court 'supreme court of pakistan' contradicts document header (Supreme Court not found)., Citation '2006 YLR 3082' (journal 'ylr' or page '3082') not found in header.

- **Case ID**: `2006_YLR_3085` | **Citation**: `2006 YLR 3085`
  - **Title**: 1062	2006 YLR 3085	Syed AHMAD SHAH HASHMI VS State - Honorable Justice Ijaz Ahmad Chaudhry - Zafar Iqbal Chohan , Ms. Raeesa Sarwar	LAHORE-HIGH-COURT-LAHORE
  - **Claimed Court**: Supreme Court of Pakistan
  - **Reasons**: Claimed court 'supreme court of pakistan' contradicts document header (Supreme Court not found)., Citation '2006 YLR 3085' (journal 'ylr' or page '3085') not found in header.

- **Case ID**: `2006_YLR_3087` | **Citation**: `2006 YLR 3087`
  - **Title**: 1063	2006 YLR 3087	KAREEM BUX VS State - Honorable Justice Khiliji Arif Hussain - Muhammad Ayaz Soomro , Muhammad Ismail Bhutto	KARACHI-HIGH-COURT-SINDH
  - **Claimed Court**: High Court of Sindh
  - **Reasons**: Claimed court 'high court of sindh' contradicts document header (High Court not found)., Citation '2006 YLR 3087' (journal 'ylr' or page '3087') not found in header.

- **Case ID**: `2006_YLR_3088` | **Citation**: `2006 YLR 3088`
  - **Title**: 1064	2006 YLR 3088	MANU alias MANTHAR VS State - Honorable Justice Mrs. Qaisar Iqbal - Khadim Hussain D.Solangi , Rasheed A. Qureshi	KARACHI-HIGH-COURT-SINDH
  - **Claimed Court**: High Court of Sindh
  - **Reasons**: Claimed court 'high court of sindh' contradicts document header (High Court not found)., Citation '2006 YLR 3088' (journal 'ylr' or page '3088') not found in header.

- **Case ID**: `2006_YLR_3089` | **Citation**: `2006 YLR 3089`
  - **Title**: 1065	2006 YLR 3089	SAIFULLAH VS State - Honorable Justice Ijaz Ahmad Chaudhry - Kh. Basit Waheed and Rai Haider Ali Khan Kharal , Muhammad Azam, Mian Abdul Qayyum Anjum and Abdul Majeed Chishti	LAHORE-HIGH-COURT-LAHORE
  - **Claimed Court**: Supreme Court of Pakistan
  - **Reasons**: Claimed court 'supreme court of pakistan' contradicts document header (Supreme Court not found)., Citation '2006 YLR 3089' (journal 'ylr' or page '3089') not found in header.

- **Case ID**: `2006_YLR_3094` | **Citation**: `2006 YLR 3094`
  - **Title**: 1066	2006 YLR 3094	ABDUL MAJEED VS State - Honorable Justice Khiliji Arif Hussain - Muhammad Ayaz Soomro , Muhammad Ismail Bhutto	KARACHI-HIGH-COURT-SINDH
  - **Claimed Court**: High Court of Sindh
  - **Reasons**: Claimed court 'high court of sindh' contradicts document header (High Court not found)., Citation '2006 YLR 3094' (journal 'ylr' or page '3094') not found in header.

- **Case ID**: `2006_YLR_3095` | **Citation**: `2006 YLR 3095`
  - **Title**: 1067	2006 YLR 3095	MUHAMMAD RAMZAN VS State - Honorable Justice ASIF SAEED KHAN KHOSA - Ahmad Baksh Bharwana , Muhammad Afzal Butt	LAHORE-HIGH-COURT-LAHORE
  - **Claimed Court**: Supreme Court of Pakistan
  - **Reasons**: Citation '2006 YLR 3095' (journal 'ylr' or page '3095') not found in header.

- **Case ID**: `2006_YLR_3097` | **Citation**: `2006 YLR 3097`
  - **Title**: 1068	2006 YLR 3097	MUHAMMAD HASHIM VS PRESIDING OFFICER, SPECIAL BANKING COURT, SINDH - Honorable Justice Mushir Alam and Azizullah M. Memon - Syed Muhammad Kazim , Nemo	KARACHI-HIGH-COURT-SINDH
  - **Claimed Court**: Supreme Court of Pakistan
  - **Reasons**: Citation '2006 YLR 3097' (journal 'ylr' or page '3097') not found in header.

- **Case ID**: `2006_YLR_3098` | **Citation**: `2006 YLR 3098`
  - **Title**: 1069	2006 YLR 3098	FAROOQ-E-AZAM VS CUSTOMS AND INTELLIGENCE DEPARTMENT - Honorable Justice Syed Zawwar Hussain Jafri - Sohail Muzaffar , Muhammad Shafi Muhammadi	KARACHI-HIGH-COURT-SINDH
  - **Claimed Court**: High Court of Sindh
  - **Reasons**: Claimed court 'high court of sindh' contradicts document header (High Court not found)., Citation '2006 YLR 3098' (journal 'ylr' or page '3098') not found in header.

- **Case ID**: `2006_YLR_3106` | **Citation**: `2006 YLR 3106`
  - **Title**: 1070	2006 YLR 3106	ABDUL KHALIQ VS ABDUL MALIK - Honorable Justice Raja Fayyaz Ahmed, C.J. and Akhtar Zaman Malghani - Muhammad Zafar and Baz Muhammad Kakar , Ehsan-ul-Haq and Naeem Akhtar	QUETTA-HIGH-COURT-BALOCHISTAN
  - **Claimed Court**: Supreme Court of Pakistan
  - **Reasons**: Citation '2006 YLR 3106' (journal 'ylr' or page '3106') not found in header.

### Category: TITLE (50 samples recorded)

- **Case ID**: `2004_YLR_457` | **Citation**: `2004 YLR 457`
  - **Title**: 127	2004 YLR 457	KHALID MEHMOOD VS NAJEEB KHAN - Honorable Justice Muhammad Yunus Surakhvi, C.J. and Chaudhary Muhammad Taj - Abdul Majid Mallick and Raja Muhammad Siddique Khan	SUPREME-COURT-AZAD-KASHMIR
  - **Claimed Court**: Supreme Court of Pakistan
  - **Reasons**: Case title party token(s) from 'KHALID MEHMOOD VS NAJEEB KHAN' not found in source document header., Citation '2004 YLR 457' (journal 'ylr' or page '457') not found in header.

- **Case ID**: `2004_YLR_487` | **Citation**: `2004 YLR 487`
  - **Title**: 135	2004 YLR 487	QADIR BAKHSH VS DIN MUHAMMAD - Honorable Justice Farrukh Latif - Abdul Rafique Sheikh	LAHORE-HIGH-COURT-LAHORE
  - **Claimed Court**: Lahore High Court
  - **Reasons**: Case title party token(s) from 'QADIR BAKHSH VS DIN MUHAMMAD' not found in source document header., Citation '2004 YLR 487' (journal 'ylr' or page '487') not found in header.

- **Case ID**: `2004_YLR_493` | **Citation**: `2004 YLR 493`
  - **Title**: 137	2004 YLR 493	MUKHTAR AHMAD VS FATIMA BIBI - Honorable Justice M. Javed Buttar - Qazi Zahid Hussain , Shuja-ud-Din Hashmi and Mian Muhammad Aslam	LAHORE-HIGH-COURT-LAHORE
  - **Claimed Court**: Lahore High Court
  - **Reasons**: Case title party token(s) from 'MUKHTAR AHMAD VS FATIMA BIBI' not found in source document header., Citation '2004 YLR 493' (journal 'ylr' or page '493') not found in header.

- **Case ID**: `2004_YLR_775` | **Citation**: `2004 YLR 775`
  - **Title**: 205	2004 YLR 775	Haji MUHAMMAD IJAZ VS GOVERNMENT OF PAKISTAN - Honorable Justice Maulvi Anwarul Haq - Razzaq A. Mirza , Nemo AND Waqar-ul-Haq Sheikh	LAHORE-HIGH-COURT-LAHORE
  - **Claimed Court**: Lahore High Court
  - **Reasons**: Case title party token(s) from 'Haji MUHAMMAD IJAZ VS GOVERNMENT OF PAKISTAN' not found in source document header., Citation '2004 YLR 775' (journal 'ylr' or page '775') not found in header.

- **Case ID**: `2004_YLR_782` | **Citation**: `2004 YLR 782`
  - **Title**: 207	2004 YLR 782	MUHAMMAD YOUNUS VS THE STATE - Honorable Justice Raja Muhammad Sabir - Maqbool Ahmed Bhatti , Tasawar Hussain Qureshi , Ghulam Asghar	LAHORE-HIGH-COURT-LAHORE
  - **Claimed Court**: Lahore High Court
  - **Reasons**: Case title party token(s) from 'MUHAMMAD YOUNUS VS THE STATE' not found in source document header., Citation '2004 YLR 782' (journal 'ylr' or page '782') not found in header.

- **Case ID**: `2004_YLR_1941` | **Citation**: `2004 YLR 1941`
  - **Title**: 533	2004 YLR 1941	SARDAR BIBI VS ABDUL AZIZ and 15 others - Honorable Justice Muhammad Muzammal Khan - Arshad Mehmood , Miam Muhammad Athar	LAHORE-HIGH-COURT-LAHORE
  - **Claimed Court**: Supreme Court of Pakistan
  - **Reasons**: Case title party token(s) from 'SARDAR BIBI VS ABDUL AZIZ and 15 others' not found in source document header., Claimed court 'supreme court of pakistan' contradicts document header (Supreme Court not found)., Citation '2004 YLR 1941' (journal 'ylr' or page '1941') not found in header., Year '2004' not found in document header.

- **Case ID**: `2004_YLR_2184` | **Citation**: `2004 YLR 2184`
  - **Title**: 606	2004 YLR 2184	Mst. NASREEN AKHTAR VS THE STATE - Honorable Justice Muhammad Akram Baitu - Tahir Mahmood , A.A,.-G	LAHORE-HIGH-COURT-LAHORE
  - **Claimed Court**: High Court of Sindh
  - **Reasons**: Case title party token(s) from 'Mst. NASREEN AKHTAR VS THE STATE' not found in source document header., Citation '2004 YLR 2184' (journal 'ylr' or page '2184') not found in header., Year '2004' not found in document header.

- **Case ID**: `2004_YLR_2393` | **Citation**: `2004 YLR 2393`
  - **Title**: 676	2004 YLR 2393	Mst. SHAMSHAD AKHTAR VS THE STATE - Honorable Justice Ch. Iftikhar Hussain - Syed Ijaz Qutab , Malik Muhammad Akbar Awan	LAHORE-HIGH-COURT-LAHORE
  - **Claimed Court**: Supreme Court of Pakistan
  - **Reasons**: Case title party token(s) from 'Mst. SHAMSHAD AKHTAR VS THE STATE' not found in source document header., Claimed court 'supreme court of pakistan' contradicts document header (Supreme Court not found)., Citation '2004 YLR 2393' (journal 'ylr' or page '2393') not found in header., Year '2004' not found in document header.

- **Case ID**: `2002_YLR_1473` | **Citation**: `2002 YLR 1473`
  - **Title**: LIMITED VS KARACHI PORT TRUST - Honorable Justice Muhammad Moosa K. Leghari - Agha Faqir Muhammad , Salman Hamid	KARACHI-HIGH-COURT-SINDH
  - **Claimed Court**: Supreme Court of Pakistan
  - **Reasons**: Case title party token(s) from 'KARACHI-HIGH-COURT-SINDH' not found in source document header., Citation '2002 YLR 1473' (journal 'ylr' or page '1473') not found in header.

- **Case ID**: `2002_YLR_3410` | **Citation**: `2002 YLR 3410`
  - **Title**: 869	2002 YLR 3410	Mst. AMINA BIBI VS MUSHTAQ AHMAD - Honorable Justice Pervaiz Ahmad - Rafiq Javed Butt , Ch. Arshad Mehmood	LAHORE-HIGH-COURT-LAHORE
  - **Claimed Court**: Supreme Court of Pakistan
  - **Reasons**: Case title party token(s) from 'Mst. AMINA BIBI VS MUSHTAQ AHMAD' not found in source document header., Claimed court 'supreme court of pakistan' contradicts document header (Supreme Court not found)., Citation '2002 YLR 3410' (journal 'ylr' or page '3410') not found in header., Year '2002' not found in document header.

### Category: YEAR (50 samples recorded)

- **Case ID**: `2004_YLR_1941` | **Citation**: `2004 YLR 1941`
  - **Title**: 533	2004 YLR 1941	SARDAR BIBI VS ABDUL AZIZ and 15 others - Honorable Justice Muhammad Muzammal Khan - Arshad Mehmood , Miam Muhammad Athar	LAHORE-HIGH-COURT-LAHORE
  - **Claimed Court**: Supreme Court of Pakistan
  - **Reasons**: Case title party token(s) from 'SARDAR BIBI VS ABDUL AZIZ and 15 others' not found in source document header., Claimed court 'supreme court of pakistan' contradicts document header (Supreme Court not found)., Citation '2004 YLR 1941' (journal 'ylr' or page '1941') not found in header., Year '2004' not found in document header.

- **Case ID**: `2004_YLR_2184` | **Citation**: `2004 YLR 2184`
  - **Title**: 606	2004 YLR 2184	Mst. NASREEN AKHTAR VS THE STATE - Honorable Justice Muhammad Akram Baitu - Tahir Mahmood , A.A,.-G	LAHORE-HIGH-COURT-LAHORE
  - **Claimed Court**: High Court of Sindh
  - **Reasons**: Case title party token(s) from 'Mst. NASREEN AKHTAR VS THE STATE' not found in source document header., Citation '2004 YLR 2184' (journal 'ylr' or page '2184') not found in header., Year '2004' not found in document header.

- **Case ID**: `2004_YLR_2393` | **Citation**: `2004 YLR 2393`
  - **Title**: 676	2004 YLR 2393	Mst. SHAMSHAD AKHTAR VS THE STATE - Honorable Justice Ch. Iftikhar Hussain - Syed Ijaz Qutab , Malik Muhammad Akbar Awan	LAHORE-HIGH-COURT-LAHORE
  - **Claimed Court**: Supreme Court of Pakistan
  - **Reasons**: Case title party token(s) from 'Mst. SHAMSHAD AKHTAR VS THE STATE' not found in source document header., Claimed court 'supreme court of pakistan' contradicts document header (Supreme Court not found)., Citation '2004 YLR 2393' (journal 'ylr' or page '2393') not found in header., Year '2004' not found in document header.

- **Case ID**: `2002_YLR_3410` | **Citation**: `2002 YLR 3410`
  - **Title**: 869	2002 YLR 3410	Mst. AMINA BIBI VS MUSHTAQ AHMAD - Honorable Justice Pervaiz Ahmad - Rafiq Javed Butt , Ch. Arshad Mehmood	LAHORE-HIGH-COURT-LAHORE
  - **Claimed Court**: Supreme Court of Pakistan
  - **Reasons**: Case title party token(s) from 'Mst. AMINA BIBI VS MUSHTAQ AHMAD' not found in source document header., Claimed court 'supreme court of pakistan' contradicts document header (Supreme Court not found)., Citation '2002 YLR 3410' (journal 'ylr' or page '3410') not found in header., Year '2002' not found in document header.

- **Case ID**: `2002_YLR_3412` | **Citation**: `2002 YLR 3412`
  - **Title**: 870	2002 YLR 3412	MUHAMMAD SHARIF VS Mst. SHARIFAN BIBI - Honorable Justice Sakhi Hussain Bokhari - Ch. Anwaar-ul-Haq Pannun	LAHORE-HIGH-COURT-LAHORE
  - **Claimed Court**: Supreme Court of Pakistan
  - **Reasons**: Case title party token(s) from 'MUHAMMAD SHARIF VS Mst. SHARIFAN BIBI' not found in source document header., Claimed court 'supreme court of pakistan' contradicts document header (Supreme Court not found)., Citation '2002 YLR 3412' (journal 'ylr' or page '3412') not found in header., Year '2002' not found in document header.

- **Case ID**: `2002_YLR_3427` | **Citation**: `2002 YLR 3427`
  - **Title**: 876	2002 YLR 3427	IMTIAZ ALI VS MUHARRAM - Honorable Justice S. Ali Aslam Jafri - Ali Nawaz Ghanghro , Roshan Ali Solangi , Sher Muhammad Shar	KARACHI-HIGH-COURT-SINDH
  - **Claimed Court**: Supreme Court of Pakistan
  - **Reasons**: Case title party token(s) from 'IMTIAZ ALI VS MUHARRAM' not found in source document header., Citation '2002 YLR 3427' (journal 'ylr' or page '3427') not found in header., Year '2002' not found in document header.

- **Case ID**: `2001_YLR_77` | **Citation**: `2001 YLR 77`
  - **Title**: 16	2001 YLR 77	LIFE PAPER STORE VS BANK OF PUNJAB - 	LAHORE-HIGH-COURT-LAHORE
  - **Claimed Court**: Supreme Court of Pakistan
  - **Reasons**: Case title party token(s) from 'LIFE PAPER STORE VS BANK OF PUNJAB - ' not found in source document header., Claimed court 'supreme court of pakistan' contradicts document header (Supreme Court not found)., Citation '2001 YLR 77' (journal 'ylr' or page '77') not found in header., Year '2001' not found in document header.

- **Case ID**: `2001_YLR_91` | **Citation**: `2001 YLR 91`
  - **Title**: 20	2001 YLR 91	LATIF ULLAH VS STATE - 	LAHORE-HIGH-COURT-LAHORE
  - **Claimed Court**: Supreme Court of Pakistan
  - **Reasons**: Case title party token(s) from 'LATIF ULLAH VS STATE - ' not found in source document header., Claimed court 'supreme court of pakistan' contradicts document header (Supreme Court not found)., Citation '2001 YLR 91' (journal 'ylr' or page '91') not found in header., Year '2001' not found in document header.

- **Case ID**: `2001_YLR_169` | **Citation**: `2001 YLR 169`
  - **Title**: 34	2001 YLR 169	V. H. PAGE VS RUTHANN BIG - 	KARACHI-HIGH-COURT-SINDH
  - **Claimed Court**: High Court of Sindh
  - **Reasons**: Case title party token(s) from 'V. H. PAGE VS RUTHANN BIG - ' not found in source document header., Citation '2001 YLR 169' (journal 'ylr' or page '169') not found in header., Year '2001' not found in document header.

- **Case ID**: `2001_YLR_356` | **Citation**: `2001 YLR 356`
  - **Title**: 102	2001 YLR 356	PERVEEN BIBI VS STATE - 	LAHORE-HIGH-COURT-LAHORE
  - **Claimed Court**: Lahore High Court
  - **Reasons**: Case title party token(s) from 'PERVEEN BIBI VS STATE - ' not found in source document header., Citation '2001 YLR 356' (journal 'ylr' or page '356') not found in header., Year '2001' not found in document header.

