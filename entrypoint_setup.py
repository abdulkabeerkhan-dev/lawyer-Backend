import os
import shutil

for p in ['/app/lawyer-Backend-master', '/app/lawyer-backend']:
    if os.path.isdir(p):
        for f in os.listdir(p):
            src = os.path.join(p, f)
            dst = os.path.join('/app', f)
            if not os.path.exists(dst):
                shutil.move(src, dst)

print('Verified files in /app:', len(os.listdir('/app')))
assert os.path.exists('/app/requirements.txt'), f"requirements.txt missing from /app! Contents: {os.listdir('/app')[:10]}"
