"""
Statutory Citation Validator & Ground-Truth Registry Layer
Phase 2 Component: Prevents fabricated/hybrid statutory citations and verifies
every cited provision against official bare-act lookup tables.
"""

import os
import re
import json
from typing import Dict, List, Optional, Tuple, Any

# Path to statutory lookup tables
TABLES_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "statute_tables"))

# Act alias mapping to canonical act_codes
ACT_ALIASES = {
    "prohibition (enforcement of hadd) order": "PROHIBITION_HADD_1979",
    "prohibition enforcement of hadd order": "PROHIBITION_HADD_1979",
    "prohibition hadd order": "PROHIBITION_HADD_1979",
    "prohibition order 1979": "PROHIBITION_HADD_1979",
    "prohibition order": "PROHIBITION_HADD_1979",
    "anti-money laundering act": "ANTI_MONEY_LAUNDERING_2010",
    "anti money laundering act": "ANTI_MONEY_LAUNDERING_2010",
    "anti-money laundering act 2010": "ANTI_MONEY_LAUNDERING_2010",
    "amla 2010": "ANTI_MONEY_LAUNDERING_2010",
    "amla": "ANTI_MONEY_LAUNDERING_2010",
    "prevention of trafficking in persons act": "HUMAN_TRAFFICKING_2018",
    "prevention of trafficking in persons act 2018": "HUMAN_TRAFFICKING_2018",
    "trafficking in persons act": "HUMAN_TRAFFICKING_2018",
    "anti trafficking act": "HUMAN_TRAFFICKING_2018",
    "protection of women (criminal laws amendment) act": "WOMEN_CRIMINAL_AMEND_2006",
    "protection of women criminal laws amendment act": "WOMEN_CRIMINAL_AMEND_2006",
    "protection of women act 2006": "WOMEN_CRIMINAL_AMEND_2006",
    "women protection act 2006": "WOMEN_CRIMINAL_AMEND_2006",
    "punjab protection of women against violence act": "PUNJAB_WOMEN_VIOLENCE_2016",
    "punjab protection of women against violence act 2016": "PUNJAB_WOMEN_VIOLENCE_2016",
    "punjab protection of women against violence": "PUNJAB_WOMEN_VIOLENCE_2016",
    "protection of women against violence act": "PUNJAB_WOMEN_VIOLENCE_2016",
    "west pakistan muslim personal law (shariat) application act": "SHARIAT_APPLICATION_1962",
    "west pakistan muslim personal law shariat application act": "SHARIAT_APPLICATION_1962",
    "muslim personal law (shariat) application act": "SHARIAT_APPLICATION_1962",
    "shariat application act 1962": "SHARIAT_APPLICATION_1962",
    "shariat application act": "SHARIAT_APPLICATION_1962",
    "pakistan (administration of evacuee property) act": "EVACUEE_PROPERTY_1957",
    "administration of evacuee property act": "EVACUEE_PROPERTY_1957",
    "evacuee property act 1957": "EVACUEE_PROPERTY_1957",
    "evacuee property act": "EVACUEE_PROPERTY_1957",
    "punjab protection of ownership of immovable property act": "PUNJAB_PROPERTY_PROTECTION_2021",
    "punjab protection of ownership of immovable property act 2021": "PUNJAB_PROPERTY_PROTECTION_2021",
    "protection of ownership of immovable property act": "PUNJAB_PROPERTY_PROTECTION_2021",
    "trusts act": "TRUSTS_1882",
    "trusts act 1882": "TRUSTS_1882",
    "the trusts act, 1882": "TRUSTS_1882",
    "easements act": "EASEMENTS_1882",
    "easements act 1882": "EASEMENTS_1882",
    "the easements act, 1882": "EASEMENTS_1882",
    "partition act": "PARTITION_1893",
    "partition act 1893": "PARTITION_1893",
    "the partition act, 1893": "PARTITION_1893",
    "cantonments rent restriction act": "CANTONMENT_RENT_1963",
    "cantonment rent restriction act": "CANTONMENT_RENT_1963",
    "cantonments rent restriction act 1963": "CANTONMENT_RENT_1963",
    "cantonment rent act": "CANTONMENT_RENT_1963",
    "sindh rented premises ordinance": "SRPO_1979",
    "sindh rented premises ordinance 1979": "SRPO_1979",
    "srpo 1979": "SRPO_1979",
    "srpo": "SRPO_1979",
    "sindh rent ordinance": "SRPO_1979",
    "industrial and commercial employment (standing orders) ordinance": "STANDING_ORDERS_1968",
    "industrial and commercial employment standing orders ordinance": "STANDING_ORDERS_1968",
    "standing orders ordinance 1968": "STANDING_ORDERS_1968",
    "standing orders ordinance": "STANDING_ORDERS_1968",
    "standing order 12": "STANDING_ORDERS_1968",
    "standing order 15": "STANDING_ORDERS_1968",
    "payment of wages act": "PAYMENT_WAGES_1936",
    "payment of wages act 1936": "PAYMENT_WAGES_1936",
    "electronic transactions ordinance": "ETO_2002",
    "electronic transactions ordinance 2002": "ETO_2002",
    "eto 2002": "ETO_2002",
    "eto": "ETO_2002",
    "elections act": "ELECTIONS_ACT_2017",
    "elections act 2017": "ELECTIONS_ACT_2017",
    "west pakistan civil courts ordinance": "CIVIL_COURTS_1962",
    "west pakistan civil courts ordinance 1962": "CIVIL_COURTS_1962",
    "civil courts ordinance": "CIVIL_COURTS_1962",
    "civil courts ordinance 1962": "CIVIL_COURTS_1962",
    "state bank of pakistan act": "SBP_1956",
    "state bank of pakistan act 1956": "SBP_1956",
    "state bank act": "SBP_1956",
    "sbp act": "SBP_1956",
    "securities and exchange commission of pakistan act": "SECP_1997",
    "securities and exchange commission of pakistan act 1997": "SECP_1997",
    "secp act": "SECP_1997",
    "secp act 1997": "SECP_1997",
    "patents ordinance": "PATENTS_2000",
    "patents ordinance 2000": "PATENTS_2000",
    "patent act": "PATENTS_2000",
    "oaths act": "OATHS_1873",
    "oaths act 1873": "OATHS_1873",
    "explosive substances act": "EXPLOSIVE_SUBSTANCES_1908",
    "explosive substances act 1908": "EXPLOSIVE_SUBSTANCES_1908",
    "explosives act": "EXPLOSIVE_SUBSTANCES_1908",
    "official secrets act": "OFFICIAL_SECRETS_1923",
    "official secrets act 1923": "OFFICIAL_SECRETS_1923",
    "maintenance of public order ordinance": "MPO_1960",
    "maintenance of public order ordinance 1960": "MPO_1960",
    "west pakistan maintenance of public order ordinance": "MPO_1960",
    "mpo 1960": "MPO_1960",
    "3 mpo": "MPO_1960",
    "mpo": "MPO_1960",
    "hindu marriage act": "HINDU_MARRIAGE_2017",
    "hindu marriage act 2017": "HINDU_MARRIAGE_2017",
    "christian marriage act": "CHRISTIAN_MARRIAGE_1872",
    "christian marriage act 1872": "CHRISTIAN_MARRIAGE_1872",
    "divorce act": "CHRISTIAN_MARRIAGE_1872",
    "divorce act 1869": "CHRISTIAN_MARRIAGE_1872",
    "federal excise act": "FEDERAL_EXCISE_2005",
    "federal excise act 2005": "FEDERAL_EXCISE_2005",
    "punjab sales tax on services act": "PUNJAB_SALES_TAX_SERVICES_2012",
    "punjab sales tax on services act 2012": "PUNJAB_SALES_TAX_SERVICES_2012",
    "pra act": "PUNJAB_SALES_TAX_SERVICES_2012",
    "sindh sales tax on services act": "SINDH_SALES_TAX_SERVICES_2011",
    "sindh sales tax on services act 2011": "SINDH_SALES_TAX_SERVICES_2011",
    "srb act": "SINDH_SALES_TAX_SERVICES_2011",
    # 26th Amendment
    "26th amendment": "CONST_26TH_AMEND_2024",
    "twenty-sixth amendment": "CONST_26TH_AMEND_2024",
    "constitution 26th amendment": "CONST_26TH_AMEND_2024",
    "constitution (26th amendment) act": "CONST_26TH_AMEND_2024",

    # Supreme Court Practice and Procedure Act 2023
    "supreme court practice and procedure act": "SC_PRACTICE_PROCEDURE_2023",
    "practice and procedure act": "SC_PRACTICE_PROCEDURE_2023",
    "sc practice and procedure": "SC_PRACTICE_PROCEDURE_2023",

    # Supreme Court Rules 1980
    "supreme court rules": "SC_RULES_1980",
    "supreme court rules 1980": "SC_RULES_1980",
    "sc rules 1980": "SC_RULES_1980",
    "sc rules": "SC_RULES_1980",

    # Zina Ordinance
    "offence of zina": "HUDOOD_ZINA_1979",
    "offence of zina ordinance": "HUDOOD_ZINA_1979",
    "zina ordinance": "HUDOOD_ZINA_1979",
    "zina hudood": "HUDOOD_ZINA_1979",
    "hudood zina": "HUDOOD_ZINA_1979",

    # Qazf Ordinance
    "offence of qazf": "HUDOOD_QAZF_1979",
    "offence of qazf ordinance": "HUDOOD_QAZF_1979",
    "qazf ordinance": "HUDOOD_QAZF_1979",
    "qazf hudood": "HUDOOD_QAZF_1979",
    "hudood qazf": "HUDOOD_QAZF_1979",

    # Anti-Rape Act 2021
    "anti-rape act": "ANTI_RAPE_2021",
    "anti rape act": "ANTI_RAPE_2021",
    "anti-rape act 2021": "ANTI_RAPE_2021",

    # Juvenile Justice System Act 2018
    "juvenile justice system act": "JUVENILE_JUSTICE_2018",
    "juvenile justice act": "JUVENILE_JUSTICE_2018",
    "jjsa 2018": "JUVENILE_JUSTICE_2018",
    "jjsa": "JUVENILE_JUSTICE_2018",

    # Arms Ordinance 1965
    "arms ordinance": "ARMS_1965",
    "arms ordinance 1965": "ARMS_1965",
    "west pakistan arms ordinance": "ARMS_1965",
    "west pakistan arms ordinance 1965": "ARMS_1965",

    # Police Order 2002
    "police order": "POLICE_ORDER_2002",
    "police order 2002": "POLICE_ORDER_2002",

    # General Clauses Act 1897
    "general clauses act": "GENERAL_CLAUSES_1897",
    "general clauses act 1897": "GENERAL_CLAUSES_1897",

    # Stamp Act 1899
    "stamp act": "STAMP_ACT_1899",
    "stamp act 1899": "STAMP_ACT_1899",

    # Banking Companies Ordinance 1962
    "banking companies ordinance": "BANKING_COMPANIES_1962",
    "banking companies ordinance 1962": "BANKING_COMPANIES_1962",
    "bco 1962": "BANKING_COMPANIES_1962",
    "bco": "BANKING_COMPANIES_1962",

    # Bankers' Books Evidence Act 1891
    "bankers books evidence act": "BANKERS_BOOKS_1891",
    "bankers' books evidence act": "BANKERS_BOOKS_1891",
    "bankers books act": "BANKERS_BOOKS_1891",

    # Benami Transactions Act 2017
    "benami transactions act": "BENAMI_2017",
    "benami transactions (prohibition) act": "BENAMI_2017",
    "benami act": "BENAMI_2017",
    "benami transactions prohibition act": "BENAMI_2017",
    "benami": "BENAMI_2017",

    # Trade Marks Ordinance 2001
    "trade marks ordinance": "TRADEMARKS_2001",
    "trademarks ordinance": "TRADEMARKS_2001",
    "trade marks ordinance 2001": "TRADEMARKS_2001",
    "trademarks act": "TRADEMARKS_2001",

    # Copyright Ordinance 1962
    "copyright ordinance": "COPYRIGHT_1962",
    "copyright ordinance 1962": "COPYRIGHT_1962",
    "copyright act": "COPYRIGHT_1962",

    # Illegal Dispossession Act 2005
    "illegal dispossession act": "ILLEGAL_DISPOSSESSION_2005",
    "illegal dispossession act 2005": "ILLEGAL_DISPOSSESSION_2005",
    "illegal dispossession": "ILLEGAL_DISPOSSESSION_2005",

    # Women's Property Rights Act
    "enforcement of women's property rights act": "WOMEN_PROPERTY_RIGHTS_2020",
    "enforcement of women property rights act": "WOMEN_PROPERTY_RIGHTS_2020",
    "womens property rights act": "WOMEN_PROPERTY_RIGHTS_2020",
    "women's property rights act": "WOMEN_PROPERTY_RIGHTS_2020",
    "women property rights act": "WOMEN_PROPERTY_RIGHTS_2020",
    "women's property rights": "WOMEN_PROPERTY_RIGHTS_2020",
    "women property rights": "WOMEN_PROPERTY_RIGHTS_2020",
    "punjab enforcement of women's property rights act": "WOMEN_PROPERTY_RIGHTS_2020",

    # Dowry Restriction Act 1976
    "dowry and bridal gifts (restriction) act": "DOWRY_RESTRICTION_1976",
    "dowry and bridal gifts restriction act": "DOWRY_RESTRICTION_1976",
    "dowry restriction act": "DOWRY_RESTRICTION_1976",

    # Islamabad Rent Restriction Ordinance 2001
    "islamabad rent restriction ordinance": "ISLAMABAD_RENT_2001",
    "islamabad rent ordinance": "ISLAMABAD_RENT_2001",
    "islamabad rent restriction ordinance 2001": "ISLAMABAD_RENT_2001",

    # High Court Rules and Orders
    "high court rules and orders": "HC_RULES_ORDERS",
    "high court rules": "HC_RULES_ORDERS",
    "hc rules": "HC_RULES_ORDERS",
    "hc rules and orders": "HC_RULES_ORDERS",
    "vol i": "HC_RULES_ORDERS",
    "vol iii": "HC_RULES_ORDERS",
    "vol v": "HC_RULES_ORDERS",

    # Defamation
    "defamation ordinance": "DEFAMATION_2002",
    "defamation ordinance 2002": "DEFAMATION_2002",
    "defamation act": "DEFAMATION_2002",
    "punjab defamation act": "DEFAMATION_2002",
    "punjab defamation act 2024": "DEFAMATION_2002",

    # Civil Servants & Service Tribunals
    "civil servants act": "CIVIL_SERVANTS_1973",
    "civil servants act 1973": "CIVIL_SERVANTS_1973",
    "service tribunals act": "CIVIL_SERVANTS_1973",
    "service tribunals act 1973": "CIVIL_SERVANTS_1973",
    "service tribunal": "CIVIL_SERVANTS_1973",

    # Mental Health
    "mental health ordinance": "MENTAL_HEALTH_2001",
    "mental health ordinance 2001": "MENTAL_HEALTH_2001",
    "mental health act": "MENTAL_HEALTH_2001",
    "punjab mental health act": "MENTAL_HEALTH_2001",

    # Punjab Consumer Protection
    "punjab consumer protection act": "PUNJAB_CONSUMER_2005",
    "consumer protection act": "PUNJAB_CONSUMER_2005",
    "consumer court": "PUNJAB_CONSUMER_2005",

    # Industrial Relations Act
    "industrial relations act": "IRA_2012",
    "industrial relations act 2012": "IRA_2012",
    "ira 2012": "IRA_2012",
    "ira": "IRA_2012",
    "nirc": "IRA_2012",

    # Bar Councils
    "legal practitioners and bar councils act": "BAR_COUNCILS_1973",
    "bar councils act": "BAR_COUNCILS_1973",
    "bar council act": "BAR_COUNCILS_1973",

    # Punjab Tenancy Act
    "punjab tenancy act": "PUNJAB_TENANCY_1887",
    "tenancy act": "PUNJAB_TENANCY_1887",
    "punjab tenancy act 1887": "PUNJAB_TENANCY_1887",

    # CPC
    "cpc": "CPC_1908",
    "c.p.c": "CPC_1908",
    "c.p.c.": "CPC_1908",
    "code of civil procedure": "CPC_1908",
    "civil procedure code": "CPC_1908",
    "cpc 1908": "CPC_1908",
    "cpc, 1908": "CPC_1908",

    # PPC
    "ppc": "PPC_1860",
    "p.p.c": "PPC_1860",
    "p.p.c.": "PPC_1860",
    "pakistan penal code": "PPC_1860",
    "penal code": "PPC_1860",
    "ppc 1860": "PPC_1860",
    "ppc, 1860": "PPC_1860",

    # CrPC
    "crpc": "CRPC_1898",
    "cr.pc": "CRPC_1898",
    "cr.p.c": "CRPC_1898",
    "cr.p.c.": "CRPC_1898",
    "code of criminal procedure": "CRPC_1898",
    "criminal procedure code": "CRPC_1898",
    "crpc 1898": "CRPC_1898",
    "crpc, 1898": "CRPC_1898",

    # Constitution
    "constitution": "CONST_1973",
    "constitution of pakistan": "CONST_1973",
    "pakistan constitution": "CONST_1973",
    "constitution 1973": "CONST_1973",
    "constitution, 1973": "CONST_1973",
    "const": "CONST_1973",
    "const.": "CONST_1973",

    # QSO
    "qso": "QSO_1984",
    "q.s.o": "QSO_1984",
    "q.s.o.": "QSO_1984",
    "qanun-e-shahadat": "QSO_1984",
    "qanun-e-shahadat order": "QSO_1984",
    "qanun e shahadat": "QSO_1984",
    "qso 1984": "QSO_1984",
    "qso, 1984": "QSO_1984",
    "evidence act": "QSO_1984",
    "evidence act 1872": "QSO_1984",

    # Limitation Act
    "limitation act": "LIMITATION_1908",
    "limitation act 1908": "LIMITATION_1908",
    "limitation act, 1908": "LIMITATION_1908",
    "the limitation act": "LIMITATION_1908",

    # Doctrinal statutes
    "mflo": "MFLO_1961",
    "muslim family laws ordinance": "MFLO_1961",
    "muslim family laws ordinance 1961": "MFLO_1961",
    "mflo 1961": "MFLO_1961",

    "family courts act": "FAMILY_COURTS_1964",
    "family court act": "FAMILY_COURTS_1964",
    "family courts act 1964": "FAMILY_COURTS_1964",
    "the family courts act, 1964": "FAMILY_COURTS_1964",

    "dmma": "DMMA_1939",
    "dissolution of muslim marriages act": "DMMA_1939",
    "dissolution of muslim marriages act 1939": "DMMA_1939",
    "dmma 1939": "DMMA_1939",

    "cnsa": "CNSA_1997",
    "control of narcotic substances act": "CNSA_1997",
    "control of narcotic substances act 1997": "CNSA_1997",
    "cnsa 1997": "CNSA_1997",

    "prpa": "PRPA_2009",
    "punjab rented premises act": "PRPA_2009",
    "punjab rented premises act 2009": "PRPA_2009",
    "prpa 2009": "PRPA_2009",

    "punjab pre-emption act": "PREEMPTION_1991",
    "punjab pre-emption act 1991": "PREEMPTION_1991",
    "punjab preemption act": "PREEMPTION_1991",
    "pre-emption act": "PREEMPTION_1991",
    "preemption act": "PREEMPTION_1991",

    # FIO 2001
    "fio": "FIO_2001",
    "fio 2001": "FIO_2001",
    "fio, 2001": "FIO_2001",
    "financial institutions (recovery of finances) ordinance": "FIO_2001",
    "financial institutions (recovery of finances) ordinance 2001": "FIO_2001",
    "financial institutions (recovery of finances) ordinance, 2001": "FIO_2001",
    "recovery of finances ordinance": "FIO_2001",
    "recovery of finances ordinance 2001": "FIO_2001",
    "financial institutions ordinance": "FIO_2001",
    "financial institutions ordinance 2001": "FIO_2001",
    "ordinance xlvi of 2001": "FIO_2001",
    # Anti-Terrorism Act
    "ata": "ATA_1997",
    "anti-terrorism act": "ATA_1997",
    "anti terrorism act": "ATA_1997",
    "ata 1997": "ATA_1997",
    "ata, 1997": "ATA_1997",
    "anti-terrorism act, 1997": "ATA_1997",
    "anti-terrorism act 1997": "ATA_1997",

    # National Accountability Ordinance
    "nao": "NAO_1999",
    "national accountability ordinance": "NAO_1999",
    "national accountability ordinance 1999": "NAO_1999",
    "nao 1999": "NAO_1999",
    "nab ordinance": "NAO_1999",
    "nab law": "NAO_1999",

    # PECA
    "peca": "PECA_2016",
    "prevention of electronic crimes act": "PECA_2016",
    "prevention of electronic crimes act 2016": "PECA_2016",
    "peca 2016": "PECA_2016",
    "electronic crimes act": "PECA_2016",

    # Prevention of Corruption Act
    "pca": "PCA_1947",
    "prevention of corruption act": "PCA_1947",
    "prevention of corruption act 1947": "PCA_1947",
    "pca 1947": "PCA_1947",

    # FIA Act
    "fia": "FIA_1974",
    "fia act": "FIA_1974",
    "federal investigation agency act": "FIA_1974",
    "fia 1974": "FIA_1974",

    # Specific Relief Act
    "sra": "SRA_1877",
    "specific relief act": "SRA_1877",
    "specific relief act 1877": "SRA_1877",
    "sra 1877": "SRA_1877",
    "the specific relief act, 1877": "SRA_1877",

    # Court Fees Act & Suits Valuation
    "court fees act": "COURT_FEES_1870",
    "court fee act": "COURT_FEES_1870",
    "court fees act 1870": "COURT_FEES_1870",
    "suits valuation act": "SUITS_VALUATION_1887",
    "suits valuation act 1887": "SUITS_VALUATION_1887",

    # Guardians and Wards Act
    "gwa": "GWA_1890",
    "guardians and wards act": "GWA_1890",
    "guardians and wards act 1890": "GWA_1890",
    "gwa 1890": "GWA_1890",
    "guardian and wards act": "GWA_1890",

    # Succession Act
    "succession act": "SUCCESSION_1925",
    "succession act 1925": "SUCCESSION_1925",
    "the succession act, 1925": "SUCCESSION_1925",

    # Child Marriage Restraint Act
    "child marriage restraint act": "CHILD_MARRIAGE_1929",
    "child marriage restraint act 1929": "CHILD_MARRIAGE_1929",

    # Contract Act
    "contract act": "CONTRACT_1872",
    "contract act 1872": "CONTRACT_1872",
    "the contract act, 1872": "CONTRACT_1872",

    # Negotiable Instruments Act
    "nia": "NIA_1881",
    "negotiable instruments act": "NIA_1881",
    "negotiable instruments act 1881": "NIA_1881",
    "nia 1881": "NIA_1881",

    # Banking Recovery 1997
    "banking companies (recovery of loans) act": "BANKING_RECOVERY_1997",
    "banking companies (recovery of loans, advances, credits and finances) act 1997": "BANKING_RECOVERY_1997",
    "banking companies (recovery of loans) act 1997": "BANKING_RECOVERY_1997",
    "banking companies recovery of loans act": "BANKING_RECOVERY_1997",
    "banking companies act 1997": "BANKING_RECOVERY_1997",
    "banking court": "FIO_2001",
    "banking court order": "FIO_2001",

    # Partnership Act
    "partnership act": "PARTNERSHIP_1932",
    "partnership act 1932": "PARTNERSHIP_1932",

    # Arbitration Acts
    "arbitration act": "ARBITRATION_1940",
    "arbitration act 1940": "ARBITRATION_1940",
    "recognition and enforcement act": "ARBITRATION_2011",
    "recognition and enforcement act 2011": "ARBITRATION_2011",

    # Sale of Goods Act
    "sale of goods act": "SALE_OF_GOODS_1930",
    "sale of goods act 1930": "SALE_OF_GOODS_1930",

    # Companies Act
    "companies act": "COMPANIES_2017",
    "companies act 2017": "COMPANIES_2017",

    # Transfer of Property Act
    "tpa": "TPA_1882",
    "transfer of property act": "TPA_1882",
    "transfer of property act 1882": "TPA_1882",
    "tpa 1882": "TPA_1882",

    # Registration Act
    "registration act": "REGISTRATION_1908",
    "registration act 1908": "REGISTRATION_1908",

    # Land Revenue Act
    "land revenue act": "LAND_REVENUE_1967",
    "land revenue act 1967": "LAND_REVENUE_1967",

    # Land Acquisition Act
    "land acquisition act": "LAND_ACQUISITION_1894",
    "land acquisition act 1894": "LAND_ACQUISITION_1894",

    # Sindh Rented Premises Ordinance
    "srpo": "SINDH_RENT_1979",
    "sindh rented premises ordinance": "SINDH_RENT_1979",
    "sindh rented premises ordinance 1979": "SINDH_RENT_1979",

    # Punjab Partition of Immoveable Property Act
    "punjab partition act": "PUNJAB_PARTITION_2012",
    "punjab partition of immoveable property act": "PUNJAB_PARTITION_2012",
    "punjab partition of immoveable property act 2012": "PUNJAB_PARTITION_2012",
    "punjab partition act 2012": "PUNJAB_PARTITION_2012",

    # Tax & Customs
    "ito": "ITO_2001",
    "income tax ordinance": "ITO_2001",
    "income tax ordinance 2001": "ITO_2001",
    "ito 2001": "ITO_2001",

    "sales tax act": "SALES_TAX_1990",
    "sales tax act 1990": "SALES_TAX_1990",

    "customs act": "CUSTOMS_1969",
    "customs act 1969": "CUSTOMS_1969",

    "amla": "AMLA_2010",
    "anti-money laundering act": "AMLA_2010",
    "anti money laundering act": "AMLA_2010",
    "amla 2010": "AMLA_2010"

}

# Roman to Integer mapping
ROMAN_TO_INT = {
    "I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6, "VII": 7, "VIII": 8, "IX": 9, "X": 10,
    "XI": 11, "XII": 12, "XIII": 13, "XIV": 14, "XV": 15, "XVI": 16, "XVII": 17, "XVIII": 18, "XIX": 19, "XX": 20,
    "XXI": 21, "XXII": 22, "XXIII": 23, "XXIV": 24, "XXV": 25, "XXVI": 26, "XXVII": 27, "XXVIII": 28, "XXIX": 29, "XXX": 30,
    "XXXI": 31, "XXXII": 32, "XXXIII": 33, "XXXIV": 34, "XXXV": 35, "XXXVI": 36, "XXXVII": 37, "XXXVIII": 38, "XXXIX": 39, "XL": 40,
    "XLI": 41, "XLII": 42, "XLIII": 43, "XLIV": 44, "XLV": 45, "XLVI": 46, "XLVII": 47, "XLVIII": 48, "XLIX": 49, "L": 50,
    "LI": 51
}

INT_TO_ROMAN = {v: k for k, v in ROMAN_TO_INT.items()}


def normalize_roman(val: str) -> str:
    """Convert Arabic integer string or Roman numeral to normalized Roman numeral."""
    val_clean = str(val).strip().upper()
    if val_clean in ROMAN_TO_INT:
        return val_clean
    if val_clean.isdigit():
        num = int(val_clean)
        return INT_TO_ROMAN.get(num, val_clean)
    return val_clean


class GroundTruthStatuteRegistry:
    """In-memory cache and query interface for official bare-act lookup tables."""
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(GroundTruthStatuteRegistry, cls).__new__(cls)
            cls._instance._loaded = False
            cls._instance._by_canonical_id = {}
            cls._instance._by_act = {}
        return cls._instance

    def ensure_loaded(self):
        if self._loaded:
            return

        if not os.path.exists(TABLES_DIR):
            return

        for fname in os.listdir(TABLES_DIR):
            if fname.endswith(".json"):
                act_code = fname[:-5]
                filepath = os.path.join(TABLES_DIR, fname)
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        entries = json.load(f)
                    if isinstance(entries, list):
                        self._by_act[act_code] = entries
                        for e in entries:
                            if isinstance(e, dict):
                                cid = e.get("canonical_id")
                                if cid:
                                    self._by_canonical_id[cid] = e
                except Exception as exc:
                    print(f"[StatuteRegistry] Warning loading {fname}: {exc}")

        self._loaded = True

    def get_by_canonical_id(self, canonical_id: str) -> Optional[Dict[str, Any]]:
        self.ensure_loaded()
        return self._by_canonical_id.get(canonical_id)

    def get_act_entries(self, act_code: str) -> List[Dict[str, Any]]:
        self.ensure_loaded()
        return self._by_act.get(act_code, [])

    def has_act(self, act_code: str) -> bool:
        self.ensure_loaded()
        return act_code in self._by_act


def generate_canonical_id(act_code: str, primary_num: str, 
                            subsection: str = None, clause: str = None,
                            rule_num: str = None, sub_rule: str = None,
                            provision_type: str = "section") -> str:
    """
    Deterministic canonical_id generator per Phase 2 spec.
    Structural distinction:
      subsection = numbered, nested directly under section (e.g. 12(2))
      clause     = lettered, nested under a subsection or section (e.g. 302(b), 22-A(6)(a))
      rule       = only applies to Order/Rule provisions (CPC First Schedule)
      sub_rule   = numbered, nested under a rule (e.g. Order XXXIX Rule 1(2))
    """
    parts = [act_code]

    if rule_num is not None:
        # Order/Rule track (CPC procedural)
        parts += ["ORD", normalize_roman(primary_num), "R", str(rule_num)]
        if sub_rule:
            parts += ["SR", str(sub_rule)]
    else:
        # Section/Article track (substantive)
        prefix = "ART" if (act_code in ("CONST_1973", "QSO_1984") or provision_type == "article") else "SEC"
        norm_primary = str(primary_num).upper().replace("-", "").replace(" ", "")
        parts += [prefix, norm_primary]
        if subsection:
            parts += [str(subsection)]
        if clause:
            parts += [str(clause).upper()]

    return "_".join(parts)


def check_hybrid_hallucination(text: str) -> Optional[Dict[str, Any]]:
    """
    Upstream check: Detects if a citation conflates substantive sections with procedural Orders/Rules
    (e.g., 'Section 12(2) Order XXI CPC', 'Order XXI Section 12(2)', 'Section 12(2) of Order XXI').
    """
    lower = text.lower()
    
    # 1. Direct co-occurrence of "Section ... Order ..." or "Order ... Section ..."
    has_sec = bool(re.search(r'\b(?:sec|section|s\.)\s*\d+', lower))
    has_ord = bool(re.search(r'\b(?:order|ord|o\.)\s*(?:[ivxlcdm]+|\d+)', lower))
    has_rule = bool(re.search(r'\b(?:rule|r\.)\s*\d+', lower))

    # CPC hybrid signature: combining Section with Order or Rule in the same citation clause
    if has_sec and (has_ord or has_rule):
        # Check if they are part of the same phrase
        hybrid_patterns = [
            r'section\s*[\d\(\)a-zA-Z\-]+\s*(?:of\s+)?order\s*[ivxlcdm\d]+',
            r'order\s*[ivxlcdm\d]+\s*(?:rule\s*\d+\s*)?(?:of\s+)?section\s*[\d\(\)a-zA-Z\-]+',
            r'section\s*12\s*\(\s*2\s*\)\s*order\s*[ivxlcdm\d]+',
            r'section\s*[\d\(\)a-zA-Z\-]+\s*rule\s*\d+'
        ]
        for pat in hybrid_patterns:
            if re.search(pat, lower):
                return {
                    "is_valid": False,
                    "status": "hybrid_hallucination",
                    "raw_citation": text,
                    "message": f"Statutory citation '{text}' is a hybrid hallucination. It conflates a substantive Section with a procedural Order/Rule, which do not exist as a single provision in the Code of Civil Procedure, 1908."
                }

    return None


def parse_statutory_citation(text: str, context: Optional[str] = None) -> Dict[str, Any]:
    """
    Parses a raw citation string into structured components:
    {
       'act_code': str,
       'provision_type': 'section' | 'order_rule' | 'article',
       'primary_num': str,
       'subsection': Optional[str],
       'clause': Optional[str],
       'rule_num': Optional[str],
       'sub_rule': Optional[str],
       'is_hybrid': bool
    }
    Enhanced to support:
    - Standard Pakistani legal shorthands (489-F PPC, 497 CrPC, 302(b) PPC, 12(2) CPC, 561-A CrPC, 22-A CrPC, 7/11 CPC, O. 39, r. 1 CPC, 199 Const).
    - Punctuation-tolerant order/rule matching (Order 39, Rule 1 / O. 39, r. 1).
    - Topical intent disambiguation for colliding sections (Section 12, Section 9, Section 42, Section 56).
    """
    # Check upstream hybrid hallucination first
    hybrid_check = check_hybrid_hallucination(text)
    if hybrid_check:
        return hybrid_check

    clean_text = text.strip()
    # ORDER 2.1 - ITEM 4: Never extract section numbers from percentages (e.g. 60%)
    if re.search(r'\b\d+\s*%', clean_text) or clean_text.endswith('%'):
        return {"is_valid": False, "status": "percentage_not_statute", "raw_citation": text}

    lower_text = clean_text.lower()
    search_context = f"{lower_text} {str(context or '').lower()}"

    # Shorthand 1: 7/11 or 7-11 CPC (Rejection of plaint)
    if re.search(r'\b7\s*[/\\-]\s*11\b', clean_text):
        return {
            "is_valid": True,
            "status": "parsed",
            "act_code": "CPC_1908",
            "provision_type": "order_rule",
            "primary_num": "VII",
            "subsection": None,
            "clause": None,
            "rule_num": "11",
            "sub_rule": None,
            "raw_citation": text
        }

    # Identify act code from aliases
    act_code = None
    for alias, code in sorted(ACT_ALIASES.items(), key=lambda x: len(x[0]), reverse=True):
        if re.search(rf'\b{re.escape(alias)}\b', lower_text):
            act_code = code
            break

    # Check search_context if act not found in immediate token
    # ORDER 2.1 - ITEM 4: A section number binds to the Act named in the same sentence.
    if not act_code:
        sentence_to_search = lower_text
        if context:
            ctx_str = str(context).lower()
            sentences = re.split(r'(?<=[.!?\n])\s+', ctx_str)
            for s in sentences:
                if lower_text in s:
                    sentence_to_search = s
                    break
        for alias, code in sorted(ACT_ALIASES.items(), key=lambda x: len(x[0]), reverse=True):
            if re.search(rf'\b{re.escape(alias)}\b', sentence_to_search):
                act_code = code
                break

    # If no act identified, check cues
    if not act_code:
        if "order" in lower_text and ("rule" in lower_text or "cpc" in lower_text):
            act_code = "CPC_1908"
        elif "article" in lower_text or "art" in lower_text:
            if "constitution" in search_context or "1973" in search_context or "const" in search_context:
                act_code = "CONST_1973"
            elif "qso" in search_context or "shahadat" in search_context:
                act_code = "QSO_1984"
            else:
                act_code = "CONST_1973"

    # Default fallback to CPC_1908 if Order/Rule is present
    if not act_code and re.search(r'\b(?:order|ord\.?|o\.?)\s*[ivxlcdm\d]+', lower_text):
        act_code = "CPC_1908"

    # 1. Parse Order/Rule track (Punctuation-tolerant, e.g. "O. 39, r. 1 CPC", "Order XXXIX Rule 2A")
    ord_match = re.search(
        r'\b(?:order|ord\.?|o\.?)\s*([ivxlcdm]+|\d+)\s*[,/\.\s\-]*\s*(?:rule|r\.?)\s*(\d+[a-zA-Z]?)(?:\s*\(\s*(\d+[a-zA-Z]?)\s*\))?',
        clean_text, re.IGNORECASE
    )
    if ord_match:
        ord_num = ord_match.group(1).upper()
        rule_num = ord_match.group(2)
        sub_rule = ord_match.group(3) if ord_match.group(3) else None
        return {
            "is_valid": True,
            "status": "parsed",
            "act_code": act_code or "CPC_1908",
            "provision_type": "order_rule",
            "primary_num": normalize_roman(ord_num),
            "subsection": None,
            "clause": None,
            "rule_num": rule_num,
            "sub_rule": sub_rule,
            "raw_citation": text
        }

    # 2. Shorthand Section + Act pattern (e.g. "489-F PPC", "497 CrPC", "302(b) PPC", "12(2) CPC", "561-A CrPC", "22-A CrPC")
    shorthand_sec_act = re.search(
        r'\b(\d+(?:-[A-Za-z]+|[A-Za-z])?)(?:\s*\(\s*(\d+)\s*\))?(?:\s*\(\s*([a-zA-Z])\s*\))?\s*(ppc|crpc|cr\.p\.c\.?|cpc|c\.p\.c\.?|qso|mflo|fio|sra|tpa|peca|ata|nab|nao|ito|gwa|nia|cnsa|const|constitution)\b',
        clean_text, re.IGNORECASE
    )
    if shorthand_sec_act:
        raw_num = shorthand_sec_act.group(1).upper().replace("-", "")
        g2 = shorthand_sec_act.group(2)
        g3 = shorthand_sec_act.group(3)
        act_token = shorthand_sec_act.group(4).lower()

        token_map = {
            "ppc": "PPC_1860",
            "crpc": "CRPC_1898",
            "cr.p.c": "CRPC_1898",
            "cr.p.c.": "CRPC_1898",
            "cpc": "CPC_1908",
            "c.p.c": "CPC_1908",
            "c.p.c.": "CPC_1908",
            "qso": "QSO_1984",
            "mflo": "MFLO_1961",
            "fio": "FIO_2001",
            "sra": "SRA_1877",
            "tpa": "TPA_1882",
            "peca": "PECA_2016",
            "ata": "ATA_1997",
            "nab": "NAO_1999",
            "nao": "NAO_1999",
            "ito": "ITO_2001",
            "gwa": "GWA_1890",
            "nia": "NIA_1881",
            "cnsa": "CNSA_1997",
            "const": "CONST_1973",
            "constitution": "CONST_1973"
        }
        resolved_act = token_map.get(act_token, act_code or "CPC_1908")
        prov_type = "article" if resolved_act in ("CONST_1973", "QSO_1984") else "section"

        sub = None
        cl = None
        if g2 and g2.isdigit():
            sub = g2
            if g3:
                cl = g3
        elif g2 and g2.isalpha():
            cl = g2
        elif g3:
            cl = g3

        return {
            "is_valid": True,
            "status": "parsed",
            "act_code": resolved_act,
            "explicit_act": True,
            "provision_type": prov_type,
            "primary_num": raw_num,
            "subsection": sub,
            "clause": cl,
            "rule_num": None,
            "sub_rule": None,
            "raw_citation": text
        }

    # 3. Parse Article track (Constitution, QSO, Limitation Schedule)
    art_match = re.search(
        r'\b(?:article|art\.?)\s*(\d+[A-Za-z]?)(?:\s*\(\s*(\d+)\s*\))?(?:\s*\(\s*([a-zA-Z])\s*\))?',
        clean_text, re.IGNORECASE
    )
    if not art_match:
        # Match "199 Const" or "184(3) Const"
        art_match = re.search(
            r'\b(\d+[A-Za-z]?)(?:\s*\(\s*(\d+)\s*\))?(?:\s*\(\s*([a-zA-Z])\s*\))?\s*(?:const|constitution)\b',
            clean_text, re.IGNORECASE
        )

    if art_match:
        primary_num = art_match.group(1).upper()
        sub = art_match.group(2)
        cl = art_match.group(3)
        if act_code in ("CONST_1973", "QSO_1984", "LIMITATION_1908", "SC_RULES_1980"):
            resolved_act = act_code
        elif "qso" in lower_text or "shahadat" in lower_text:
            resolved_act = "QSO_1984"
        elif "limitation" in lower_text or ("limitation" in search_context and int(re.sub(r'[^0-9]', '', primary_num) or 0) <= 183):
            resolved_act = "LIMITATION_1908"
        else:
            resolved_act = "CONST_1973"
        return {
            "is_valid": True,
            "status": "parsed",
            "act_code": resolved_act,
            "provision_type": "article",
            "primary_num": primary_num,
            "subsection": sub,
            "clause": cl,
            "rule_num": None,
            "sub_rule": None,
            "raw_citation": text
        }

    # 4. Parse Section track (CPC substantive, PPC, CrPC, SRA, TPA, etc.)
    sec_match = re.search(
        r'\b(?:section|sec\.?|s\.?)\s*(\d+(?:-[A-Za-z]+|[A-Za-z])?)(?:\s*\(\s*(\d+)\s*\))?(?:\s*\(\s*([a-zA-Z])\s*\))?',
        clean_text, re.IGNORECASE
    )
    if not sec_match:
        # Bare section or clause e.g. "302(b)", "12(2)", "489-F", "561-A", "22-A"
        # ORDER 2.1 - ITEM 4: Do not match digits preceding %
        sec_match = re.search(
            r'\b(\d+(?:-[A-Za-z]+|[A-Za-z])?)(?!\s*%)(?:\s*\(\s*(\d+)\s*\))?(?:\s*\(\s*([a-zA-Z])\s*\))?',
            clean_text, re.IGNORECASE
        )
        if sec_match:
            candidate_prim = sec_match.group(1).replace("-", "")
            if candidate_prim.isdigit() and 1800 <= int(candidate_prim) <= 2099:
                # ORDER 1.11: Standalone calendar years are not section numbers
                sec_match = None

    if sec_match:
        raw_prim = sec_match.group(1).upper().replace("-", "")
        g2 = sec_match.group(2)
        g3 = sec_match.group(3)

        sub = None
        cl = None
        if g2 and g2.isdigit():
            sub = g2
            if g3:
                cl = g3
        elif g2 and g2.isalpha():
            cl = g2
        elif g3:
            cl = g3

        # Topical Disambiguation logic when act_code is not explicit
        resolved_act = act_code
        explicit_act = (act_code is not None)

        if not resolved_act:
            # Order 1.14 - Item 4: Strictly forbid guessing FIO_2001 from 'of the Ordinance'.
            # Resolve to FIO_2001 ONLY when the full title appears in context.
            if "ordinance" in search_context and any(w in search_context for w in ["financial institutions (recovery of finances) ordinance", "financial institutions ordinance", "recovery of finances ordinance"]):
                resolved_act = "FIO_2001"
            elif raw_prim == "12":
                if any(w in search_context for w in ["specific performance", "agreement to sell", "contractual", "sra"]):
                    resolved_act = "SRA_1877"
                elif sub == "2" or any(w in search_context for w in ["fraud", "misrepresentation", "decree", "cpc"]):
                    resolved_act = "CPC_1908"
                else:
                    resolved_act = "CPC_1908"
            elif raw_prim == "9":
                if any(w in search_context for w in ["dispossessed", "dispossession", "possession", "summary possession", "tenant", "sra"]):
                    resolved_act = "SRA_1877"
                elif any(w in search_context for w in ["narcotic", "charas", "heroin", "contraband", "cnsa"]):
                    resolved_act = "CNSA_1997"
                elif any(w in search_context for w in ["maintenance", "wife", "mflo"]):
                    resolved_act = "MFLO_1961"
                else:
                    resolved_act = "CPC_1908"
            elif raw_prim == "42":
                if any(w in search_context for w in ["declaration", "legal character", "cloud on title", "declaratory", "sra"]):
                    resolved_act = "SRA_1877"
                elif any(w in search_context for w in ["mutation", "intiqal", "patwari", "fard", "land revenue"]):
                    resolved_act = "LAND_REVENUE_1967"
                else:
                    resolved_act = "SRA_1877"
            elif raw_prim == "56":
                if any(w in search_context for w in ["frustration", "impossibility", "impossible", "contract"]):
                    resolved_act = "CONTRACT_1872"
                elif any(w in search_context for w in ["injunction", "refused", "sra"]):
                    resolved_act = "SRA_1877"
                else:
                    resolved_act = "CONTRACT_1872"
            elif raw_prim == "52":
                if any(w in search_context for w in ["lis pendens", "transfer pending", "alienation", "tpa"]):
                    resolved_act = "TPA_1882"
                elif any(w in search_context for w in ["jamabandi", "presumption of truth", "land revenue"]):
                    resolved_act = "LAND_REVENUE_1967"
                else:
                    resolved_act = "TPA_1882"
            elif raw_prim == "22":
                if any(w in search_context for w in ["1997", "act xv of 1997", "recovery of loans, advances", "banking companies (recovery of loans) act 1997"]):
                    resolved_act = "BANKING_RECOVERY_1997"
                elif any(w in search_context for w in ["banking", "bank", "financial institution", "financial institutions", "fio", "loan", "finance", "recovery of finances", "decretal", "banking court", "banking judge"]):
                    resolved_act = "FIO_2001"
                elif any(w in search_context for w in ["justice of peace", "peace", "crpc", "fir", "police", "ex-officio"]):
                    resolved_act = "CRPC_1898"
                elif any(w in search_context for w in ["transfer of suit", "power to transfer", "subordinate court", "cpc"]):
                    resolved_act = "CPC_1908"
                else:
                    resolved_act = "CPC_1908"
            elif raw_prim == "138":
                if any(w in search_context for w in ["cheque", "dishonour", "bounced", "negotiable", "ni act"]):
                    resolved_act = "NI_ACT_1881"
                elif any(w in search_context for w in ["railway", "railways"]):
                    resolved_act = "RAILWAYS_1890"
                else:
                    resolved_act = "NI_ACT_1881"
            elif raw_prim == "7":
                if any(w in search_context for w in ["ata", "terror", "anti-terrorism", "terrorist"]):
                    resolved_act = "ATA_1997"
                elif any(w in search_context for w in ["court fees", "valuation", "stamp"]):
                    resolved_act = "COURT_FEES_1870"
                elif any(w in search_context for w in ["cnsa", "narcotics", "contraband"]):
                    resolved_act = "CNSA_1997"
                elif any(w in search_context for w in ["mflo", "talaq", "divorce", "arbitration council"]):
                    resolved_act = "MFLO_1961"
                else:
                    resolved_act = "CPC_1908"
            elif raw_prim in ("496", "497", "498", "561A", "22A", "154", "156", "161", "164", "173"):
                resolved_act = "CRPC_1898"
            elif raw_prim in ("302", "337", "489F", "420", "406", "376", "34", "109"):
                resolved_act = "PPC_1860"
            elif raw_prim in ("199", "184", "185", "204", "10A", "25", "9"):
                resolved_act = "CONST_1973"
            else:
                resolved_act = "CPC_1908"

        prov_type = "article" if resolved_act in ("CONST_1973", "QSO_1984") else "section"
        return {
            "is_valid": True,
            "status": "parsed",
            "act_code": resolved_act,
            "explicit_act": explicit_act,
            "provision_type": prov_type,
            "primary_num": raw_prim,
            "subsection": sub,
            "clause": cl,
            "rule_num": None,
            "sub_rule": None,
            "raw_citation": text
        }

    return {
        "is_valid": False,
        "status": "unparseable",
        "raw_citation": text,
        "message": f"Could not parse statutory citation structure from '{text}'."
    }


def validate_statutory_citation(citation: str, default_act: str = None) -> Dict[str, Any]:
    """
    Validates a statutory citation string against the ground-truth lookup registry.
    Performs upstream hybrid rejection, canonical ID generation, and exact registry check.
    """
    registry = GroundTruthStatuteRegistry()
    registry.ensure_loaded()

    # Upstream hybrid check
    hybrid = check_hybrid_hallucination(citation)
    if hybrid:
        return hybrid

    parsed = parse_statutory_citation(citation)
    if not parsed.get("is_valid"):
        return parsed

    explicit_act = parsed.get("explicit_act", True)
    act_code = parsed.get("act_code") or default_act
    record = None
    canonical_id = None

    # If act was not explicitly stated in the citation (e.g. "Section 489-F"),
    # search candidate acts in registry (prioritizing penal/procedural acts for sections > 158 or with letter suffixes)
    if not explicit_act and parsed.get("provision_type") == "section":
        candidate_acts = ["PPC_1860", "CRPC_1898", "CPC_1908", "CNSA_1997", "PRPA_2009", "FAMILY_COURTS_1964", "LIMITATION_1908", "PREEMPTION_1991", "MFLO_1961", "DMMA_1939"]
        for cand_act in candidate_acts:
            cand_id = generate_canonical_id(
                act_code=cand_act,
                primary_num=parsed["primary_num"],
                subsection=parsed.get("subsection"),
                clause=parsed.get("clause"),
                rule_num=parsed.get("rule_num"),
                sub_rule=parsed.get("sub_rule"),
                provision_type=parsed.get("provision_type", "section")
            )
            rec = registry.get_by_canonical_id(cand_id)
            if rec:
                act_code = cand_act
                canonical_id = cand_id
                record = rec
                break

    if not record:
        if not act_code:
            return {
                "is_valid": False,
                "status": "missing_act",
                "raw_citation": citation,
                "message": f"Could not determine statute for citation '{citation}'."
            }

        canonical_id = generate_canonical_id(
            act_code=act_code,
            primary_num=parsed["primary_num"],
            subsection=parsed.get("subsection"),
            clause=parsed.get("clause"),
            rule_num=parsed.get("rule_num"),
            sub_rule=parsed.get("sub_rule"),
            provision_type=parsed.get("provision_type", "section")
        )
        record = registry.get_by_canonical_id(canonical_id)

    if record:
        return {
            "is_valid": True,
            "status": "verified",
            "canonical_id": canonical_id,
            "display_name": record.get("display_name") or record.get("title") or citation,
            "title": record.get("title"),
            "status_jurisdiction": record.get("status"),
            "superseded_reference": record.get("superseded_reference"),
            "source_citation": record.get("source_citation") or record.get("source_file") or "Pakistan Code",
            "raw_citation": citation
        }

    # If canonical ID not found, check if base primary exists (e.g. Section 12 exists, but subsection 99 does not)
    base_id = generate_canonical_id(
        act_code=act_code,
        primary_num=parsed["primary_num"],
        rule_num=parsed.get("rule_num"),
        provision_type=parsed.get("provision_type", "section")
    )
    base_record = registry.get_by_canonical_id(base_id)

    if base_record:
        return {
            "is_valid": False,
            "status": "unverified_sub_provision",
            "canonical_id": canonical_id,
            "base_provision": base_record.get("display_name"),
            "raw_citation": citation,
            "message": f"The base provision '{base_record.get('display_name')}' exists, but specific sub-provision ({parsed.get('subsection') or parsed.get('clause') or parsed.get('sub_rule')}) could not be verified in official text."
        }

    return {
        "is_valid": False,
        "status": "unverified_provision",
        "canonical_id": canonical_id,
        "raw_citation": citation,
        "message": f"Provision with Canonical ID '{canonical_id}' does not exist in verified statutory lookup tables."
    }


def validate_citations_in_text(text: str) -> Dict[str, Any]:
    """
    Scans free-text content (e.g. LLM synthesis or draft pleading), validates all statutory
    citations, and flags hallucinations or unverified provisions with a deterministic banner.
    """
    # Regex to find candidate statutory references in text
    citation_patterns = [
        # Hybrid patterns
        r'\b(?:section|sec\.?)\s*\d+[\(\)\w\-]*\s*(?:of\s+)?(?:order|ord\.?)\s*[ivxlcdm\d]+(?:\s*(?:rule|r\.?)\s*\d+)?(?:\s*cpc)?\b',
        # Order / Rule
        r'\b(?:order|ord\.?|o\.?)\s*[ivxlcdm\d]+\s*(?:rule|r\.?)\s*\d+(?:\s*\(\s*\d+\s*\))?(?:\s*(?:of\s+the\s+)?cpc)?\b',
        # Article
        r'\b(?:article|art\.?)\s*\d+[a-zA-Z]?(?:\s*\(\s*\d+\s*\))?(?:\s*\(\s*[a-zA-Z]\s*\))?(?:\s*(?:of\s+the\s+)?(?:constitution|qso))?\b',
        # Section with Act
        r'(?<![\w\'])\b(?:section|sec\.?|s\.)\s*\d+(?:-[A-Za-z]+|[A-Za-z])?(?:\s*\(\s*\d+\s*\))?(?:\s*\(\s*[a-zA-Z]\s*\))?(?:\s*(?:of\s+the\s+)?(?:cpc|ppc|crpc|cnsa|prpa|mflo|limitation\s+act))?\b'
    ]

    all_matches = set()
    for cp in citation_patterns:
        for m in re.finditer(cp, text, re.IGNORECASE):
            match_str = m.group(0).strip()
            # Filter trivial noise
            if len(match_str) > 4:
                all_matches.add(match_str)

    results = []
    hybrids = []
    unverified = []
    verified = []

    for cit in sorted(all_matches):
        res = validate_statutory_citation(cit)
        results.append(res)
        if res.get("status") == "hybrid_hallucination":
            hybrids.append(res)
        elif res.get("status") == "verified":
            verified.append(res)
        elif not res.get("is_valid"):
            unverified.append(res)

    warning_banner = None
    if hybrids or unverified:
        lines = ["⚠️ **Statutory Citation Notice**: The following cited provision(s) could not be verified against official bare acts:"]
        for h in hybrids:
            lines.append(f"- **{h['raw_citation']}**: Conflates substantive section with procedural order (invalid hybrid citation).")
        for u in unverified:
            lines.append(f"- **{u['raw_citation']}**: {u.get('message', 'Provision unverified.')}")
        warning_banner = "\n".join(lines)

    return {
        "verified_count": len(verified),
        "hybrid_count": len(hybrids),
        "unverified_count": len(unverified),
        "verified": verified,
        "hybrids": hybrids,
        "unverified": unverified,
        "warning_banner": warning_banner
    }
