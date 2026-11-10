@echo off
chcp 65001 >nul
REM 키 없이 샘플 대본으로 웹툰 이미지 렌더링 테스트 (output 폴더에 생성)
pip install -r requirements.txt
python -m gtoon.main make --slot noon --sample
pause
