# 담다 데모 폴백 이미지 라이브러리 (정제만, 보정 X)

보정(선명도/국소대비)은 FE 화면 필터가 전담 → 폴백 이미지는 정제만. 이중보정 방지.
원본(목업용 zip) 543장 → 중복제거(dHash)+초점필터 → 그룹당 4컷 = 180장/50그룹.

## 구성
- demo_images/ : 180장. `{연령}_{성별}_{부위}_{조명}_{idx}.jpg`
- demo_image_map.json : (age_band,gender,part,light) -> file,url,focus,low_quality
- contact/ : QA 컨택트시트
- clean.py : 정제 파이프라인(ENHANCE=False). 보정 켜려면 ENHANCE=True
- upload_to_supabase.py : scan-images/demo/ 업로드 (SUPABASE_SERVICE_KEY 필요)

## 커버리지
20대F·50대F·50대M·60대+(72)F·기타(M2_03)F × 5부위 × white/uv = 50그룹
URL: https://roghtpxrhxkicleukrfz.supabase.co/storage/v1/object/public/scan-images/demo/<file>

## 주의
- part는 폴더 기준(원본 파일명 part 전부 FOREHEAD 오기), CNIN=CHIN, M2_03 age 오타→'기타'.
- 보정은 FE에서: 아래 SVG 언샤프 필터 참고(BE 전달).
