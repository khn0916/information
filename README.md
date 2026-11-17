# 과제 4: 오늘의 정보판

## 로컬 실행

Python 3.10 이상에서 최초 한 번 의존성을 설치합니다.

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

`.env`에 `LOSTARK_API_KEY=발급받은키`를 저장한 뒤 `python app.py`를 실행하고, 브라우저에서 `http://127.0.0.1:5000`을 엽니다. 서버와 화면이 같은 주소로 제공됩니다.

## Render 배포

저장소의 `render.yaml`을 사용해 Render Blueprint를 생성합니다. Render 대시보드에서 `LOSTARK_API_KEY`를 Secret 값으로 등록하면 화면과 검색 API를 같은 공개 주소에서 제공합니다. 키를 코드나 GitHub에 저장하지 마세요.

Render 무료 웹 서비스는 15분간 요청이 없으면 잠들고, 다음 요청 때 다시 시작합니다. 파일 기록은 재시작 및 재배포 후 유지되지 않으므로, 과거 기록과 새 검색 내역을 계속 보관하려면 PostgreSQL이 필요합니다. Render 대시보드의 Environment에 `DATABASE_URL`을 등록하면 검색 내역을 날짜별로 PostgreSQL에 저장합니다. 첫 DB 연결 때 저장소에 포함된 `history_seed.json`의 과거 기록도 자동으로 한 번 가져옵니다. DB 연결 전에는 기존 기록 파일로 동작합니다.

## 참가 캐릭터 랭킹

메인 TOP 10은 검색된 캐릭터의 최신 저장 전투력으로 자동 계산됩니다. 과거에 검색해 저장한 기록만 대상으로 하며 전체 로아 유저 순위는 아닙니다. 별도의 참가 등록 기능은 기본 꺼져 있고, `ENABLE_RANKING_REGISTRATION=true`를 명시한 경우에만 켜집니다.

## API 테스트

```powershell
python ..\test_api.py
```

`LOSTARK_CHARACTER_NAME` 환경 변수로 테스트할 캐릭터 이름을 바꿀 수 있습니다. 로컬 서버는 `PORT`로 포트를 지정할 수 있고, 기록 파일은 `LOA_DATA_FILE`로 위치를 지정할 수 있습니다.

## 보안

`.env`, `loa_data.json`, 임시 파일은 Git에서 제외됩니다. 이전에 노출된 API 키는 폐기하고 새 키를 Render의 환경 변수로 등록하세요.
