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
import psycopg
from psycopg.rows import dict_row

app = Flask(__name__)
app.json.ensure_ascii = False
CORS(app, origins=os.getenv("CORS_ORIGINS", "null,http://127.0.0.1:5000").split(","))
logging.basicConfig(level=logging.INFO)
log = app.logger

BASE_DIR = Path(__file__).resolve().parent
DATA_FILE = Path(os.getenv("LOA_DATA_FILE", BASE_DIR / "loa_data.json"))
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
API_URL = "https://developer-lostark.game.onstove.com/armories/characters/{}/{}"
TIMEOUT = (5, 15)


@app.get("/")
def index():
    return send_from_directory(BASE_DIR, "index.HTML")


@app.get("/health")
def health():
    return jsonify({"status": "ok"})


@app.get("/tear.png")
def error_image():
    return send_from_directory(BASE_DIR, "tear.png")


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


def ranking_connection():
    if not DATABASE_URL:
        raise ApiError("랭킹 저장소 연결이 필요합니다.", 503)
    connection = None
    try:
        connection = psycopg.connect(
            DATABASE_URL, row_factory=dict_row, connect_timeout=10
        )
        connection.execute(
            """CREATE TABLE IF NOT EXISTS ranking_characters (
                name TEXT NOT NULL,
                server TEXT NOT NULL,
                class_name TEXT NOT NULL,
                combat_power DOUBLE PRECISION NOT NULL CHECK (combat_power >= 0),
                item_level DOUBLE PRECISION NOT NULL DEFAULT 0,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                PRIMARY KEY (server, name)
            )"""
        )
        return connection
    except psycopg.Error as exc:
        if connection is not None:
            connection.close()
        log.exception("Unable to connect to the ranking database")
        raise ApiError("랭킹 저장소에 연결하지 못했습니다.", 503) from exc


def search_history_ranking():
    data = load_data()
    latest_by_name = {}
    for name, history in data.items():
        if not isinstance(history, list):
            continue
        valid = [
            row for row in history
            if isinstance(row, dict)
            and isinstance(row.get("combatPower"), (int, float))
            and row["combatPower"] >= 0
        ]
        if not valid:
            continue
        latest = max(valid, key=lambda row: str(row.get("date", "")))
        latest_by_name[name] = {
            "name": latest.get("name") or name,
            "className": latest.get("className") or "알 수 없음",
            "server": latest.get("server") or "알 수 없음",
            "combatPower": latest["combatPower"],
        }
    ranking = sorted(
        latest_by_name.values(), key=lambda row: row["combatPower"], reverse=True
    )[:10]
    for rank, row in enumerate(ranking, 1):
        row["rank"] = rank
    return ranking


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


@app.get("/api/ranking")
def character_ranking():
    if not DATABASE_URL:
        return jsonify({
            "status": 200,
            "ranking": search_history_ranking(),
            "registrationEnabled": False,
        })
    try:
        with ranking_connection() as connection:
            ranking = connection.execute(
                """SELECT name, server, class_name AS \"className\", combat_power AS \"combatPower\"
                   FROM ranking_characters
                   ORDER BY combat_power DESC, name ASC
                   LIMIT 10"""
            ).fetchall()
    except psycopg.Error as exc:
        log.exception("Unable to load character ranking")
        raise ApiError("랭킹을 불러오지 못했습니다.", 503) from exc
    for rank, row in enumerate(ranking, 1):
        row["rank"] = rank
    return jsonify({"status": 200, "ranking": ranking, "registrationEnabled": True})


@app.post("/api/ranking/register")
def register_ranking_character():
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        raise ApiError("캐릭터 이름을 확인해주세요.", 400)
    char_name = payload.get("name", "")
    if not isinstance(char_name, str) or not char_name.strip() or len(char_name.strip()) > 32:
        raise ApiError("캐릭터 이름을 확인해주세요.", 400)
    char_name = char_name.strip()
    if not DATABASE_URL:
        raise ApiError("랭킹 저장소 연결이 필요합니다.", 503)

    matches = []
    for history in load_data().values():
        if not isinstance(history, list):
            continue
        valid = [
            row for row in history
            if isinstance(row, dict)
            and str(row.get("name", "")).casefold() == char_name.casefold()
            and isinstance(row.get("combatPower"), (int, float))
            and row["combatPower"] >= 0
        ]
        if valid:
            matches.append(max(valid, key=lambda row: str(row.get("date", ""))))
    if not matches:
        raise ApiError("먼저 캐릭터를 검색한 뒤 랭킹에 등록해주세요.", 400)
    latest = max(matches, key=lambda row: str(row.get("date", "")))

    entry = {
        "name": latest["name"],
        "server": latest.get("server") or "알 수 없음",
        "class_name": latest.get("className") or "알 수 없음",
        "combat_power": float(latest["combatPower"]),
        "item_level": float(latest.get("itemLevel") or 0),
    }
    try:
        with ranking_connection() as connection:
            connection.execute(
                """INSERT INTO ranking_characters
                       (name, server, class_name, combat_power, item_level)
                   VALUES (%(name)s, %(server)s, %(class_name)s, %(combat_power)s, %(item_level)s)
                   ON CONFLICT (server, name) DO UPDATE SET
                       class_name = EXCLUDED.class_name,
                       combat_power = EXCLUDED.combat_power,
                       item_level = EXCLUDED.item_level,
                       updated_at = now()""",
                entry,
            )
    except psycopg.Error as exc:
        log.exception("Unable to register character in ranking")
        raise ApiError("랭킹 등록을 저장하지 못했습니다.", 503) from exc
    return jsonify({"status": 200, "message": "랭킹에 등록했습니다.", "character": entry})


@app.errorhandler(ApiError)
def handle_api_error(error):
    return jsonify({"status": error.status, "message": error.message}), error.status


@app.errorhandler(Exception)
def handle_unexpected_error(error):
    log.exception("Unexpected API error")
    return jsonify({"status": 500, "message": "서버 내부 오류가 발생했습니다."}), 500


if __name__ == "__main__":
    app.run(port=int(os.getenv("PORT", "5000")), debug=False)
