import json
import logging
import os
import tempfile
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

import requests
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

app = Flask(__name__)
app.json.ensure_ascii = False
CORS(app, origins=os.getenv("CORS_ORIGINS", "null,http://127.0.0.1:5000").split(","))
logging.basicConfig(level=logging.INFO)
log = app.logger

BASE_DIR = Path(__file__).resolve().parent
DATA_FILE = Path(os.getenv("LOA_DATA_FILE", BASE_DIR / "loa_data.json"))
API_URL = "https://developer-lostark.game.onstove.com/armories/characters/{}/{}"
TIMEOUT = (5, 15)


@app.get("/")
def index():
    return send_from_directory(BASE_DIR, "index.HTML")


@app.get("/health")
def health():
    return jsonify({"status": "ok"})


def load_env_file():
    """Load local .env values without overriding explicitly set environment variables."""
    env_file = BASE_DIR / ".env"
    try:
        lines = env_file.read_text(encoding="utf-8-sig").splitlines()
    except FileNotFoundError:
        return
    except OSError:
        log.exception("Unable to read environment file %s", env_file)
        return

    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        name, value = name.strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if name and name not in os.environ:
            os.environ[name] = value


load_env_file()


class ApiError(Exception):
    def __init__(self, message, status):
        self.message, self.status = message, status


def api_headers():
    key = os.getenv("LOSTARK_API_KEY", "").strip()
    if not key:
        raise ApiError("서버에 LOSTARK_API_KEY 환경 변수를 설정해주세요.", 503)
    return {"accept": "application/json", "authorization": f"bearer {key}"}


def request_loa(char_name, endpoint):
    url = API_URL.format(quote(char_name, safe=""), endpoint)
    try:
        response = requests.get(url, headers=api_headers(), timeout=TIMEOUT)
    except ApiError:
        raise
    except requests.Timeout as exc:
        raise ApiError("로스트아크 API 응답 시간이 초과되었습니다.", 504) from exc
    except requests.RequestException as exc:
        log.warning("Lost Ark API request failed: %s", exc)
        raise ApiError("로스트아크 API에 연결하지 못했습니다.", 502) from exc

    if response.status_code == 401:
        raise ApiError("API 키가 만료되었거나 올바르지 않습니다.", 502)
    if response.status_code == 404:
        raise ApiError(f"'{char_name}' 캐릭터를 찾을 수 없습니다.", 404)
    if not response.ok:
        log.warning("Lost Ark API returned HTTP %s", response.status_code)
        raise ApiError("로스트아크 서버에서 데이터를 가져오지 못했습니다.", 502)
    try:
        return response.json()
    except requests.exceptions.JSONDecodeError as exc:
        raise ApiError("로스트아크 API 응답을 읽을 수 없습니다.", 502) from exc


def load_data():
    try:
        with DATA_FILE.open(encoding="utf-8") as file:
            data = json.load(file)
        if not isinstance(data, dict):
            raise ValueError("root must be an object")
        return data
    except FileNotFoundError:
        return {}
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        log.exception("Unable to read data file %s", DATA_FILE)
        raise ApiError("기록 파일을 읽지 못했습니다. 파일을 확인해주세요.", 500) from exc


def save_data(data):
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=DATA_FILE.parent,
            delete=False, suffix=".tmp"
        ) as file:
            temp_path = Path(file.name)
            json.dump(data, file, ensure_ascii=False, indent=2)
            file.flush()
            os.fsync(file.fileno())
        temp_path.replace(DATA_FILE)
    except OSError as exc:
        log.exception("Unable to save data file %s", DATA_FILE)
        raise ApiError("기록을 저장하지 못했습니다. 폴더 권한을 확인해주세요.", 500) from exc
    finally:
        if temp_path and temp_path.exists():
            temp_path.unlink(missing_ok=True)


@app.get("/api/search")
def search_character():
    char_name = request.args.get("name", "").strip()
    if not char_name:
        raise ApiError("캐릭터 이름을 입력해주세요.", 400)

    profile = request_loa(char_name, "profiles")
    if not isinstance(profile, dict):
        raise ApiError("캐릭터 프로필 응답 형식이 올바르지 않습니다.", 502)
    equipment = request_loa(char_name, "equipment")
    try:
        item_level = float(str(profile.get("ItemAvgLevel") or "0").replace(",", ""))
        combat_power = float(str(profile.get("CombatPower") or "0").replace(",", ""))
    except (TypeError, ValueError) as exc:
        raise ApiError("캐릭터 수치 데이터 형식이 올바르지 않습니다.", 502) from exc

    now = datetime.now().astimezone()
    today = now.date().isoformat()
    char_info = {
        "name": profile.get("CharacterName", char_name),
        "server": profile.get("ServerName", "알 수 없음"),
        "className": profile.get("CharacterClassName", "알 수 없음"),
        "itemLevel": item_level,
        "combatPower": combat_power,
        "title": profile.get("Title") or "없음",
        "updateTime": now.strftime("%Y-%m-%d %H:%M:%S"),
        "equipment": equipment if isinstance(equipment, list) else [],
    }

    data = load_data()
    history = data.get(char_name, [])
    if not isinstance(history, list):
        raise ApiError("캐릭터 기록 형식이 올바르지 않습니다.", 500)
    previous = [row for row in history if isinstance(row, dict) and row.get("date", "") < today]
    entry = {**char_info, "date": today}
    today_index = next(
        (i for i, row in enumerate(history)
         if isinstance(row, dict) and row.get("date") == today), None
    )
    if today_index is None:
        history.append(entry)
    else:
        history[today_index] = entry
    data[char_name] = history
    save_data(data)

    yesterday_power = max(previous, key=lambda row: row["date"], default={}).get("combatPower")
    return jsonify({
        "status": 200, "character": char_info,
        "yesterdayPower": yesterday_power, "history": history,
    })


@app.errorhandler(ApiError)
def handle_api_error(error):
    return jsonify({"status": error.status, "message": error.message}), error.status


@app.errorhandler(Exception)
def handle_unexpected_error(error):
    log.exception("Unexpected API error")
    return jsonify({"status": 500, "message": "서버 내부 오류가 발생했습니다."}), 500


if __name__ == "__main__":
    app.run(port=int(os.getenv("PORT", "5000")), debug=False)
