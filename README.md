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

Render 무료 웹 서비스는 15분간 요청이 없으면 잠들고, 다음 요청 때 다시 시작합니다. 무료 서비스의 파일 저장 공간은 재시작 및 재배포 후 유지되지 않으므로, 검색 기능은 작동하지만 `loa_data.json`의 기록 보존은 보장되지 않습니다. 기록을 계속 보관하려면 영구 디스크나 외부 데이터베이스 설정이 필요합니다.

## API 테스트

```powershell
python ..\test_api.py
```

`LOSTARK_CHARACTER_NAME` 환경 변수로 테스트할 캐릭터 이름을 바꿀 수 있습니다. 로컬 서버는 `PORT`로 포트를 지정할 수 있고, 기록 파일은 `LOA_DATA_FILE`로 위치를 지정할 수 있습니다.

## 보안

`.env`, `loa_data.json`, 임시 파일은 Git에서 제외됩니다. 이전에 노출된 API 키는 폐기하고 새 키를 Render의 환경 변수로 등록하세요.
