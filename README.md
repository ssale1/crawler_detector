# 개인정보 불법유통 의심 게시물 탐지기

온라인 게시판에서 개인정보 불법유통이 의심되는 게시물을 자동으로 수집하고 선별하기 위한 **Python 기반 웹 모니터링 자동화 도구**입니다.

개인정보 불법유통 대응 대학생 모니터링단 활동 중 다수의 게시물을 사람이 직접 확인하고 기록해야 하는 반복적인 작업의 비효율성을 경험했습니다. 이를 개선하기 위해 웹 게시물을 자동으로 수집하고, 개인정보 불법유통 관련 키워드를 기반으로 의심 게시물을 1차 선별하여 Excel 파일로 정리할 수 있도록 개발했습니다.

> 본 프로젝트는 게시물의 불법 여부를 법적으로 판정하는 시스템이 아니라, 모니터링 대상 중 **의심 게시물을 빠르게 선별하기 위한 보조 도구**입니다.

## 주요 기능

### 1. 정적·동적 웹페이지 수집

* `Requests`를 이용한 정적 웹페이지 수집
* `Selenium`을 이용한 JavaScript 기반 동적 페이지 수집
* Headless Chrome을 이용한 백그라운드 크롤링

### 2. 게시글 자동 추출

`BeautifulSoup`을 이용해 HTML을 파싱하고 게시판 내 게시글 링크를 자동으로 수집합니다.

다음과 같은 URL 패턴과 링크 텍스트를 활용해 게시글 후보를 탐색합니다.

```text
view
read
post
board
bbs
article
entry
/product/
/article/
숫자 기반 게시글 URL
```

### 3. 개인정보 불법유통 의심 키워드 탐지

게시글의 본문을 추출한 뒤 개인정보 불법유통과 관련된 키워드를 검색합니다.

현재 기본 키워드 예시는 다음과 같습니다.

```python
KEYWORDS = [
    "네이버 해킹",
    "해킹 DB",
    "계정판매",
    "계정 매매",
    "개인정보",
    "유출",
    "게임 해킹",
    "해킹",
    "010인증"
]
```

단순 문자열 일치뿐만 아니라 `RapidFuzz`를 활용한 유사도 기반 탐지를 함께 적용하여 키워드가 정확히 일치하지 않는 경우도 탐지할 수 있도록 구현했습니다.

```python
FUZZY_THRESHOLD = 80
```

### 4. 탐지 결과 자동 정리

탐지된 게시물은 `pandas`를 활용하여 `results.xlsx` 파일로 자동 저장합니다.

저장되는 정보는 다음과 같습니다.

* 출처 사이트
* 게시판 URL
* 게시글 제목
* 게시글 URL
* 탐지된 키워드
* 키워드 주변 본문
* 스크린샷 경로
* HTTP 상태 코드
* 탐지 시각

### 5. 스크린샷 저장

Selenium을 사용하는 사이트에서 의심 게시물이 탐지되면 해당 페이지의 스크린샷을 `screenshots/` 디렉터리에 저장할 수 있도록 구현했습니다.

### 6. robots.txt 확인

크롤링 전 대상 사이트의 `robots.txt`를 확인하여 해당 URL에 대한 접근 허용 여부를 확인합니다.

또한 연속적인 요청으로 대상 서버에 과도한 부하를 주지 않도록 요청 간 지연 시간을 적용했습니다.

### 7. 병렬 처리

`ThreadPoolExecutor`를 이용해 여러 대상 사이트를 동시에 처리할 수 있도록 구현했습니다.

```python
MAX_WORKERS = 4
```

이를 통해 여러 모니터링 사이트를 순차적으로 처리하는 것보다 효율적으로 탐색할 수 있도록 구성했습니다.

---

## 동작 구조

```text
targets.csv
     │
     ▼
모니터링 대상 사이트 확인
     │
     ▼
robots.txt 접근 가능 여부 확인
     │
     ▼
Requests / Selenium
웹페이지 수집
     │
     ▼
BeautifulSoup
게시글 링크 및 본문 추출
     │
     ▼
Keyword Exact Matching
        +
RapidFuzz Similarity Matching
     │
     ▼
의심 게시물 선별
     │
     ├──────────────► Screenshot 저장
     │
     ▼
pandas
     │
     ▼
results.xlsx
```

---

## 프로젝트 구조

```text
.
├── crawler_detector.py
├── targets.csv
├── results.xlsx          # 실행 후 생성
└── screenshots/          # 실행 후 생성
```

### `crawler_detector.py`

크롤링, 게시글 분석, 키워드 탐지 및 결과 저장을 담당하는 메인 프로그램입니다.

### `targets.csv`

모니터링할 웹사이트와 게시판 경로를 관리하는 설정 파일입니다.

---

## targets.csv 설정

`targets.csv`에는 다음 세 가지 값을 설정합니다.

```csv
base_url,listing_paths,use_selenium
https://example.com,/board;/bbs,0
```

| 항목              | 설명                                      |
| --------------- | --------------------------------------- |
| `base_url`      | 크롤링할 웹사이트의 기본 URL                       |
| `listing_paths` | 확인할 게시판 경로. 여러 경로는 `;`로 구분              |
| `use_selenium`  | Selenium 사용 여부 (`1` 또는 `true` 사용 시 활성화) |

예를 들어 게시판 경로가 여러 개인 경우 다음과 같이 설정할 수 있습니다.

```csv
base_url,listing_paths,use_selenium
https://example.com,/board/free;/board/community,0
```

JavaScript를 통해 게시글이 로드되는 사이트라면 다음과 같이 설정할 수 있습니다.

```csv
base_url,listing_paths,use_selenium
https://example.com,/community,1
```

---

## 기술 스택

### Language

* Python

### Crawling & Parsing

* Requests
* Selenium
* BeautifulSoup4

### Data Processing

* pandas
* RapidFuzz

### Etc.

* ThreadPoolExecutor
* urllib.robotparser
* Chrome WebDriver

---

## 설치

Python 환경에서 필요한 라이브러리를 설치합니다.

```bash
pip install requests beautifulsoup4 pandas rapidfuzz selenium webdriver-manager openpyxl
```

`pandas`에서 `.xlsx` 파일을 생성하기 위해 `openpyxl`을 함께 설치합니다.

Chrome 브라우저가 설치되어 있어야 Selenium 기반 크롤링을 사용할 수 있습니다.

---

## 실행 방법

### 1. 저장소 Clone

```bash
git clone <repository-url>
cd <repository-name>
```

### 2. targets.csv 설정

모니터링할 사이트와 게시판 경로를 `targets.csv`에 입력합니다.

### 3. 프로그램 실행

```bash
python crawler_detector.py
```

### 4. 결과 확인

의심 게시물이 탐지되면 프로젝트 디렉터리에 다음 파일이 생성됩니다.

```text
results.xlsx
```

Selenium을 사용하는 사이트에서 탐지된 게시물의 화면은 다음 디렉터리에 저장됩니다.

```text
screenshots/
```

---

## 구현 과정에서 고려한 점

### 정적 페이지와 동적 페이지 대응

모든 웹사이트가 동일한 방식으로 HTML을 제공하지 않기 때문에 정적인 사이트는 Requests를 이용하고, JavaScript 렌더링이 필요한 사이트는 Selenium을 사용할 수 있도록 분리했습니다.

### 단순 키워드 탐지의 한계 보완

게시물 작성자가 항상 동일한 표현을 사용하지 않는다는 점을 고려하여 단순 문자열 검색과 함께 RapidFuzz 기반 유사도 검색을 적용했습니다.

### 탐지와 판정의 분리

키워드가 포함되어 있다는 이유만으로 개인정보 불법유통 게시물이라고 단정하지 않고, 시스템에서는 의심 게시물을 1차적으로 선별한 뒤 사람이 최종적으로 검토하는 방식을 목표로 했습니다.

### 크롤링 대상 관리 분리

모니터링 대상 사이트를 코드에 직접 작성하지 않고 `targets.csv`에서 관리하도록 구성하여 새로운 대상 사이트를 추가할 때 프로그램 코드를 수정하지 않아도 되도록 했습니다.

---

## 프로젝트를 통해 얻은 경험

개인정보 불법유통 대응 모니터링 활동에서 경험했던 반복적인 수작업을 직접 개발한 프로그램으로 자동화하면서 실제 문제를 기술적으로 해결하는 과정을 경험했습니다.

특히 다음과 같은 경험을 얻을 수 있었습니다.

* Python 기반 웹 크롤링 및 데이터 수집
* 정적·동적 웹페이지 처리 방식의 차이 이해
* HTML 구조 분석 및 게시글 데이터 추출
* 키워드 및 문자열 유사도 기반 데이터 필터링
* 수집 데이터의 Excel 자동화
* 여러 사이트를 대상으로 한 병렬 처리
* robots.txt 및 요청 주기를 고려한 크롤링
* 실제 활동에서 발견한 문제를 개발 프로젝트로 구체화하는 경험

---

## 한계 및 개선 방향

현재 버전은 키워드와 문자열 유사도를 기반으로 의심 게시물을 선별하기 때문에 문맥에 따라 오탐이 발생할 수 있습니다.

향후에는 다음과 같은 방향으로 개선할 수 있습니다.

* 게시판별 HTML 구조에 맞춘 Parser 개선
* 키워드별 위험도 Score 적용
* 탐지 결과 중복 제거
* 사이트별 요청 속도 제한 세분화
* 탐지 데이터 DB 저장
* 관리자 Web Dashboard 구현
* 자연어 처리 기반 게시물 문맥 분석
* 신고·검토 결과를 활용한 탐지 기준 개선

---

## 주의사항

본 프로젝트는 개인정보 불법유통 의심 게시물을 모니터링하기 위한 학습 및 연구 목적의 프로젝트입니다.

실제 웹사이트를 대상으로 사용할 경우 해당 사이트의 이용약관, `robots.txt`, 관련 법령 및 접근 정책을 확인해야 하며 서버에 과도한 요청을 발생시키지 않도록 주의해야 합니다.
