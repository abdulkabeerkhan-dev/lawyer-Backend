import os, sys
from dotenv import load_dotenv
load_dotenv('D:/lawyer-Backend/.env')
sys.path.append('D:/lawyer-Backend')
from legal_ai.config import get_zilliz_client

client = get_zilliz_client()
res = client.query(
    collection_name='statutes_v3',
    filter='act_code == "PRPA_2009"',
    limit=5,
    output_fields=['canonical_id', 'heading']
)
print('PRPA_2009 in Zilliz statutes_v3:', res)

res2 = client.query(
    collection_name='statutes_v3',
    filter='canonical_id == "TPA_1882_SEC_106"',
    limit=5,
    output_fields=['canonical_id', 'heading', 'in_force']
)
print('TPA_1882_SEC_106 in Zilliz statutes_v3:', res2)
