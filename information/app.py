from flask import Flask, jsonify, request
from flask_cors import CORS
import requests
import json
import os
from datetime import datetime

app = Flask(__name__)
app.json.ensure_ascii = False # 👈 한글이 깨지지 않게 해주는 마법!

# ⚠️ 아까 발급받은 API 키와 캐릭터 이름을 여기에 넣어줘!
API_KEY = "eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiIsIng1dCI6IktYMk40TkRDSTJ5NTA5NWpjTWk5TllqY2lyZyIsImtpZCI6IktYMk40TkRDSTJ5NTA5NWpjTWk5TllqY2lyZyJ9.eyJpc3MiOiJodHRwczovL2x1ZHkuZ2FtZS5vbnN0b3ZlLmNvbSIsImF1ZCI6Imh0dHBzOi8vbHVkeS5nYW1lLm9uc3RvdmUuY29tL3Jlc291cmNlcyIsImNsaWVudF9pZCI6IjEwMDAwMDAwMDAzMjA2MjUifQ.kB4wih9iRhyY1nRZ07qqUf57neGL97FrmHs77TYUI_-dCWKCeMqTvFFlwk-ByegZYeKYYRzQSOwjmozEyutywISjBKgIXOtZU4foLbQxhLHJa-JC30lfrTRrSza5obE0i9YJrLKzhI138dotGvL0zAfbQE05iMJfgB5treKg732p_IATvmrgfwBj5rH02apgfcU5mNAldMMrhFGeZqbrNy8EWb8qc1b9nLWxQwsd_UTpJgaU8QcNhy4wILs2CRZEebhtYWN_JUawSVW8dZ_c-2Uy00HEEkJPKMpBSCT2Z353TqCW8KFGBRg_yNc4f-ZxX8mrWVij1_9vYQBrCOG-Ig"
# CHARACTER_NAME = "불효자의움직임"  <-- 검색을 위해 동적으로 받을 거라 주석 처리

DATA_FILE = "loa_data.json"

# 데이터 저장/불러오기 함수
def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# 로스트아크 API 호출 함수
def get_loa_data(char_name):
    url = f"https://developer-lostark.game.onstove.com/armories/characters/{char_name}/profiles"
    headers = {
        "accept": "application/json",
        "authorization": f"bearer {API_KEY}"
    }
    
    try:
        response = requests.get(url, headers=headers)
        
        if response.status_code == 200:
            return {"status": 200, "data": response.json()}
        elif response.status_code == 401:
            return {"status": 401, "message": "API 키가 만료되었거나 올바르지 않습니다."}
        elif response.status_code == 404:
            return {"status": 404, "message": f"'{char_name}' 캐릭터를 찾을 수 없습니다."}
        else:
            return {"status": response.status_code, "message": "로스트아크 서버 점검 중이거나 통신 오류가 발생했습니다."}
            
    except requests.exceptions.RequestException:
        return {"status": 500, "message": "인터넷 연결이 불안정합니다."}

# 메인 검색 API 엔드포인트
@app.route('/api/search')
def search_character():
    char_name = request.args.get('name')
    if not char_name:
        return jsonify({"status": 400, "message": "캐릭터 이름을 입력해주세요."})

    # 1. 로아 API 호출
    result = get_loa_data(char_name)
    if result["status"] != 200:
        return jsonify(result)

    profile_data = result["data"]
    
    # 2. 우리가 필요한 데이터만 추출
    char_info = {
        "name": profile_data.get("CharacterName"),
        "server": profile_data.get("ServerName"),
        "className": profile_data.get("CharacterClassName"),
        "itemLevel": float(profile_data.get("ItemAvgLevel", "0").replace(",", "")),
        "combatPower": float(profile_data.get("CombatPower", "0").replace(",", "")),
        "title": profile_data.get("Title", "없음"),
        "updateTime": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }

    # 3. 데이터 저장 및 비교 로직
    db = load_data()
    today_str = datetime.now().strftime("%Y-%m-%d")
    
    if char_name not in db:
        db[char_name] = []

    history = db[char_name]
    
    # 오늘 날짜의 데이터가 이미 있으면 업데이트, 없으면 추가
    existing_index = next((i for i, item in enumerate(history) if item["date"] == today_str), -1)
    if existing_index >= 0:
        history[existing_index] = {**char_info, "date": today_str}
    else:
        history.append({**char_info, "date": today_str})
    
    save_data(db)

    # 4. 어제 데이터와 비교
    yesterday_power = None
    if len(history) > 1:
        # 오늘 데이터를 제외한 가장 최근 데이터 (어제)
        sorted_history = sorted(history, key=lambda x: x['date'])
        today_index = next((i for i, item in enumerate(sorted_history) if item["date"] == today_str), -1)
        if today_index > 0:
            yesterday_power = sorted_history[today_index - 1]["combatPower"]

    # 5. 프론트엔드로 보낼 최종 응답
    return jsonify({
        "status": 200,
        "character": char_info,
        "yesterdayPower": yesterday_power,
        "history": history
    })

if __name__ == '__main__':
    app.run(debug=True, port=5000)
