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
python -m unittest discover -s tests -v
```

이 테스트는 코드에 포함된 합성 응답 fixture로 성공, 날짜 경계, 시간 초과, 인증 실패, 요청 한도, 연결 실패, 응답 형식 변경을 확인합니다. 실제 API 조회값을 재현한 테스트로 오해하지 않도록 fixture 데이터는 `시험용캐릭터`로 표시되어 있습니다. 로컬 서버는 `PORT`로 포트를 지정할 수 있고, 기록 파일은 `LOA_DATA_FILE`로 위치를 지정할 수 있습니다.

## 제출·검증 정보

- 결과 화면: https://loa-information.onrender.com
- 소스 코드: https://github.com/khn0916/information/tree/codex/deploy-information
- 공개 출처 안내: https://developer-lostark.game.onstove.com/
- 확인 순서: (1) 결과 URL을 로그아웃 상태로 연다. (2) 캐릭터를 검색해 실제 응답의 전투력·아이템 레벨과 화면 값을 비교한다. (3) 출처 링크, 원본 갱신 시각 유무, 조회 시작·완료 시각, KST 기록 날짜를 확인한다. (4) 위 fixture 테스트를 실행하고, 실패 시 마지막 저장값이 유지되며 오래된 값 표시가 나오는지 확인한다.
- 공개 API 응답에서 원본 갱신 시각 또는 `Last-Modified`가 없으면 임의로 만들지 않고 `API에서 제공하지 않음`으로 표시합니다. 조회 시작·완료 시각은 서버가 KST로 기록합니다.
- AI가 맡은 일: 조회 실패 종류, 마지막 정상값 보존, KST 일별 저장, 전일/이전 기록 변화, fixture 검증을 코드로 확인했습니다.
- 판단한 일: 원본 시각이 없을 때는 추정하지 않고 미제공으로 표시합니다. Lost Ark API는 과거 날짜 조회가 없어 기존 백업 밖의 과거값을 새로 만들어내지 않습니다.
- 따르지 않은 제안: 과거 기록을 합성해 채우거나 원본 시각을 임의로 표시하는 방법은 실제값으로 오해될 수 있어 적용하지 않았습니다.
- 남은 실서비스 확인: 실제 API를 사용한 두 KST 날짜 비교와 공개 배포 화면 확인은 합성 테스트로 대체하지 않았습니다. 이 실행 환경에서는 외부 도메인 확인이 되지 않아 여기서 실시간 값을 확인하지 못했습니다.

## 보안

`.env`, `loa_data.json`, 임시 파일은 Git에서 제외됩니다. 이전에 노출된 API 키는 폐기하고 새 키를 Render의 환경 변수로 등록하세요.
