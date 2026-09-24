# 불법 유통 의심 게시물 탐지기

공개 웹 게시판을 순회하며 지정한 키워드가 포함된 게시물을 수집하고 Excel로 정리하는 Python 기반 모니터링 도구입니다.

이 프로그램은 게시물의 불법 여부를 법적으로 판정하지 않습니다. 키워드와 문자열 유사도를 이용해 사람이 검토할 후보를 1차로 선별합니다.

## 주요 기능

- Requests를 이용한 정적 웹페이지 수집
- Selenium을 이용한 JavaScript 기반 페이지 수집 옵션
- BeautifulSoup 기반 게시물 링크 및 본문 추출
- 게시판 페이지 자동 순회
- 동일 게시물 URL 중복 제거
- 키워드 정확 일치 및 RapidFuzz 유사도 검사
- robots.txt 확인과 요청 간격 적용
- 탐지 결과를 `results.xlsx`로 저장
- Selenium 사용 시 탐지 화면 스크린샷 저장

그누보드처럼 URL에 `wr_id`가 들어가는 게시판에서는 메뉴, 회원가입, 개인정보 처리방침 등의 링크를 제외하고 실제 게시물 링크만 수집합니다.

## 설치

Python 환경에서 필요한 패키지를 설치합니다.

```bash
pip install requests beautifulsoup4 pandas rapidfuzz selenium webdriver-manager openpyxl
```

Selenium을 사용하려면 Chrome 브라우저도 필요합니다.

## 대상 사이트 설정

`targets.csv`에서 수집할 게시판을 설정합니다.

```csv
base_url,listing_paths,use_selenium,max_pages
http://hello-dr1.com,/bbs/board.php?bo_table=after,0,10
```

| 열 | 설명 |
| --- | --- |
| `base_url` | 사이트 기본 주소 |
| `listing_paths` | 게시판 목록 경로. 여러 경로는 `;`로 구분 |
| `use_selenium` | `0`: Requests 사용, `1`: Selenium 사용 |
| `max_pages` | 게시판별 최대 순회 페이지 수 |

페이지 순회는 URL의 `page` 쿼리 값을 변경하는 방식입니다. 새로운 게시물 URL이 없는 페이지를 만나면 설정한 최대 페이지에 도달하기 전에 종료합니다.

## 탐지 키워드 설정

`crawler_detector.py`의 `KEYWORDS` 목록을 수정합니다.

```python
KEYWORDS = [
    "네이버 해킹",
    "해킹 DB",
    "계정 판매",
    "계정 매매",
    "개인정보",
    "유출",
    "해킹",
    "010인증",
    "게임 해킹",
]
```

정확히 포함된 표현과 RapidFuzz 부분 유사도를 함께 검사합니다. 기본 유사도 기준은 `80`입니다. 짧거나 일반적인 키워드는 정상 게시물까지 탐지할 수 있으므로 결과를 반드시 사람이 검토해야 합니다.

## 실행

```bash
python crawler_detector.py
```

실행 로그에는 현재 페이지, 발견한 게시물 수, 중복되지 않는 새 게시물 수와 최종 저장 건수가 표시됩니다.

## 결과 확인

탐지 결과는 프로젝트 폴더의 `results.xlsx`에 저장됩니다.

| 열 | 설명 |
| --- | --- |
| `source_site` | 출처 사이트 |
| `page_url` | 게시물을 발견한 목록 페이지 |
| `page_number` | 발견한 페이지 번호 |
| `post_title` | 게시물 제목 |
| `post_url` | 게시물 주소 |
| `matched_keywords` | 탐지된 키워드 |
| `snippet` | 키워드 주변 본문 |
| `screenshot_path` | Selenium 스크린샷 경로 |
| `http_status` | HTTP 상태 코드 |
| `timestamp` | 탐지 시각 |

Excel에서 `results.xlsx`를 열어둬 덮어쓸 수 없는 경우에는 `results_20260925_043551.xlsx`처럼 시간이 붙은 별도 파일로 자동 저장됩니다.

`results*.xlsx`, `screenshots/`, `__pycache__/`는 실행 산출물이므로 Git에서 제외됩니다.

## 처리 흐름

```text
targets.csv 읽기
→ 게시판 페이지 순회
→ 게시물 링크 추출 및 중복 제거
→ Requests 또는 Selenium으로 본문 수집
→ 키워드 정확 일치 및 유사도 검사
→ 의심 게시물을 Excel로 저장
→ 사람의 최종 검토
```

## 현재 한계

- URL의 `page` 값을 사용하는 게시판 구조를 기준으로 순회합니다.
- 사이트마다 HTML 구조가 달라 본문 영역을 정확히 찾지 못할 수 있습니다.
- 로그인, CAPTCHA, 폐쇄형 커뮤니티는 처리하지 않습니다.
- 이미지 속 글자는 OCR을 사용하지 않아 탐지하지 못합니다.
- 은어와 문맥을 이해하는 분류 모델이 아니므로 오탐과 미탐이 발생합니다.
- 여러 Selenium 대상을 병렬 처리할 때는 드라이버 공유 구조를 추가로 개선해야 합니다.

## 주의사항

공개 페이지라도 실제 운영에 사용하기 전에 사이트 이용약관, robots.txt, 관련 법령과 개인정보 처리 기준을 확인해야 합니다. 서버에 부담을 주지 않도록 요청 간격과 최대 페이지 수를 적절하게 설정하세요.
