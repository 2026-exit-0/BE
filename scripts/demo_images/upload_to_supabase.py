"""demo_images/ 를 Supabase scan-images/demo/ 로 업로드.
사용:  SUPABASE_SERVICE_KEY=... python upload_to_supabase.py
service role key 필요(스토리지 쓰기). anon key로는 안 됨.
"""
import os, sys, json, mimetypes, urllib.request
REF="roghtpxrhxkicleukrfz"; BUCKET="scan-images"
KEY=os.environ.get("SUPABASE_SERVICE_KEY")
if not KEY: sys.exit("환경변수 SUPABASE_SERVICE_KEY 설정 필요 (service role key).")
here=os.path.dirname(os.path.abspath(__file__)); imgdir=os.path.join(here,"demo_images")
m=json.load(open(os.path.join(here,"demo_image_map.json"))); ok=fail=0
for e in m:
    url=f"https://{REF}.supabase.co/storage/v1/object/{BUCKET}/demo/{e['file']}"
    req=urllib.request.Request(url, data=open(os.path.join(imgdir,e['file']),"rb").read(), method="POST")
    req.add_header("Authorization",f"Bearer {KEY}"); req.add_header("apikey",KEY)
    req.add_header("Content-Type",mimetypes.guess_type(e['file'])[0] or "image/jpeg")
    req.add_header("x-upsert","true")
    try: urllib.request.urlopen(req); ok+=1
    except Exception as ex: fail+=1; print("FAIL",e['file'],ex)
print(f"done: {ok} uploaded, {fail} failed")
