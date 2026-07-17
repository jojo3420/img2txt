# 읽기순서 인식 채점 지표 교체 설계 (#11)

작성일: 2026-07-17
관련 이슈: [#11](https://github.com/jojo3420/img2txt/issues/11) (블로커), [#13](https://github.com/jojo3420/img2txt/issues/13)
상위 스펙: `docs/superpowers/specs/2026-07-13-ocr-llm-quality-harness-design.md` (5.3 채점규칙, 5.6 리포트 스키마, 7.3 D8) — 이 설계로 개정
근거: `docs/bench/2026-07-17-preprocess-ab-2010.md` 실험 결함 3종 1번, truth-check(2026-07-17)

## 1. 배경과 문제

벤치 하네스의 정답 라벨은 AI Hub 공공문서(dataSetSn=71299) JSON의 Bbox 단어 목록을 `id` 오름차순으로 공백 join해 복원한다(`img2txt/bench/aihub.py`). 그러나 공공행정문서는 2차원 양식이라 라벨 id 순서 != OCR 읽기순서(위→아래). 현행 CER(글자오류율, Character Error Rate)은 어순 민감 시퀀스 편집거리라, OCR이 정확히 읽어도 순서가 다르면 오류율이 부풀려진다.

실측(캐시된 baseline OCR 출력으로 OCR 재실행 없이 재계산, 문서 기록치와 일치 검증됨):

| 지표 | 2010 | b1980 |
|------|------|-------|
| A) id순 CER (현행) | 17.36% | 53.24% |
| B) 읽기순서 재정렬 CER | 11.60% | 41.73% |
| C) 순서무관 글자 놓침률 | **0.98%** | **17.77%** |

핵심 시사점: 좌표 기반 읽기순서 재정렬(B)은 왜곡을 절반쯤만 걷어낸다. 2010은 11.6%까지 내려가도 진짜 OCR 놓침은 1%뿐 — 남는 잔차는 (a) 읽기순서 휴리스틱이 Apple Vision 실제 읽기경로와 완벽히 못 맞고 (b) 라벨 불완전성(OCR이 라벨에 없는 양식기호-헤더-페이지번호를 정확히 읽으면 CER에선 삽입 오류로 계산)에서 온다. 즉 **재정렬만으로는 지표가 안 고쳐진다.**

동시에 순서무관 놓침률(C)은 위치가 틀린 오인식과 LLM 환각(없는 글자 생성)을 못 잡아 **과소평가**한다(Codex 교차 검증 지적). LLM 보정 비교 트랙은 환각 탐지가 필수라 C 단독도 부적합하다.

## 2. 목표와 비목표

목표
- 어순 착시에 안 흔들리는 주지표(놓침률)와 위치오류-환각을 잡는 보조지표(읽기순서 CER 델타)를 하네스 1급 지표로 도입한다.
- baseline 4세트를 재측정해 진짜 OCR 품질이 드러나는지 검증한다.
- 상위 스펙 5.3/5.6/7.3을 개정한다.

비목표 (이번 범위 밖)
- 전처리본 JPEG 재압축 교란 수정(#13 SHOULD) — baseline 재측정은 원본만 써 교란 없음.
- 사람이 완전 교정한 정답셋 확보(#13 NICE) — 라벨 불완전성은 추가율로 노출만 하고 라벨 자체는 안 고침.
- 읽기순서 휴리스틱의 다열/표 열검출 고도화 — 이번엔 하지 않는다(YAGNI). 근거는 "델타로 완전 상쇄"가 아니라 "주 판정은 순서무관 놓침률이 담당하고, 읽기순서 CER은 부작용 감시라 잔차에 덜 민감"이기 때문이다. 오묶음은 고도화 대신 진단 필드(suspicious_layout_flag)로 관측한다(Should, 5-6절).
- 품질 하한 임계값의 최종 확정 — 임계값은 baseline 분포를 근거 자료로 남기되, 실제 통과선은 LLM 트랙이 보정 데이터를 보고 정한다.

## 3. 확정 결정 사항

두 지표 병행. 각 지표의 역할을 분리한다.

- **놓침률 (miss rate) — 주지표, 품질 하한 게이트.** 정답 글자 multiset 중 OCR이 못 낸 비율(공백 제외, 한 방향). 어순-라벨불완전성에 안 흔들려 절대 품질 하한 판정에 쓴다.
- **읽기순서 CER — 순서/문장성 부작용 감시 (랭킹 아님).** 정답을 좌표 기반 읽기순서로 재정렬 후 계산. `corrected vs assembled` paired delta(짝지어 비교한 개선폭)로 순서-문장성이 나빠졌는지 본다. 동일 페이지-동일 참조의 paired 비교에서 상수 편향(라벨불완전성-재정렬 잔차)의 영향이 **부분 완화**되나, LLM이 텍스트를 재배열/추가하면 완화가 약해지므로 완전 상쇄로 보지 않는다. 최종 모델 랭킹은 상위 스펙 7.3의 비용→속도를 따르고, 놓침률 게이트 통과가 선행 조건이다.
- **추가율 (extra rate) — 진단.** OCR이 라벨에 없는 글자를 낸 초과분 / 정답 글자수. 라벨 불완전성-LLM 환각 노출용. `degraded_page_count`와 함께 부작용 감시.

## 4. 지표 정의 (산식)

정규화는 기존과 동일하게 `normalize_strict`(NFC + 공백류 단일 공백)를 먼저 적용한다. multiset 지표는 그 위에서 공백을 제거하고 글자 Counter로 계산한다.

페이지-지점별 (raw/assembled/corrected 각각):
- `ref = normalize_strict(reference)`, `hyp = normalize_strict(output)`
- `ref_c = Counter(ref 공백제거)`, `hyp_c = Counter(hyp 공백제거)`, `N = sum(ref_c.values())`
- 놓침률 = `sum(max(0, ref_c[c] - hyp_c[c]) for c in ref_c) / N` (N=0이면 0.0)
- 추가율 = `sum(max(0, hyp_c[c] - ref_c[c]) for c in hyp_c) / N` (N=0이면 rate는 정의 불가라 0.0으로 두되, 아래 빈정답 진단을 별도로 남긴다)
- 빈 정답 환각 진단 (Must): `N=0 and len(hyp 공백제거)>0`이면 `empty_ref_with_output=True`와 초과 글자수 `empty_ref_extra_chars`를 페이지 레코드에 기록. 주의: 기존 `cer`는 빈정답+출력에 1.0을 반환(`scoring.py:70`)하는데 multiset rate는 0이라 같은 페이지에서 값이 엇갈린다 — 이 진단 필드로 불일치를 드러내고 리포트는 두 값을 함께 노출해 환각이 숫자에서 사라지지 않게 한다.
- 읽기순서 CER = 기존 `cer(ref, hyp)` 그대로. 정답이 읽기순서 join으로 바뀌므로 `cer_strict`가 자동으로 읽기순서 CER이 됨. **CER 계산 코드는 안 건드림.**

micro 집계(지점별): `Σ miss / Σ N`, `Σ extra / Σ N`. CER은 기존 micro 방식 유지.

## 5. 읽기순서 재정렬 알고리즘 (aihub 어댑터)

각 Bbox entry는 `x=[left,left,right,right]`, `y=[top,bottom,top,bottom]` 좌표 배열을 가진다(실데이터 확인: entry 키 `data,id,type,typeface,x,y`).

1. entry별 파생: `x_left=min(x)`, `y_top=min(y)`, `y_bot=max(y)`, `y_center=(y_top+y_bot)/2`, `height=y_bot-y_top`.
2. 양수 height의 중앙값 `med_h`, 허용오차 `tol = med_h * 0.6`. 양수 height가 하나도 없으면(전부 퇴화 좌표) `y_center`만으로 정렬하는 폴백을 쓴다.
3. `y_center` 오름차순 정렬 후 그리디 행 그룹핑: 다음 entry의 `y_center`가 현재 행 평균과 `tol` 이내면 같은 행에 넣고 행 평균 갱신, 아니면 새 행 시작.
4. 각 행 내부 `x_left` 오름차순 정렬.
5. 행을 위→아래로 이어 붙여 단어를 공백 join. 빈 Bbox는 "".
6. 진단 메타 산출(Should): `bbox_count`, `row_count`, `median_height`, 오묶음 의심 플래그 `suspicious_layout_flag`(예: 한 행에 지나치게 넓은 x-범위의 단어가 많이 묶이는 등 다열/표 정황). 재정렬을 바꾸지 않고 이상치 페이지 추적용으로만 리포트에 남긴다.

경계 방어: `_validate_bbox`에 x/y 검증 추가 — (a) 리스트이고 원소가 숫자(int/float), (b) NaN/무한대 아님, (c) x와 y 길이가 같고 비어있지 않음. 위반 시 `ValueError`(조기 발견, 조용한 폴백 금지). height≤0(퇴화 좌표)은 재정렬을 깨지 않게 `med_h` 계산에서 제외하고 2단계 폴백으로 처리. 기존 id/data 검증은 유지하되 id는 정렬 키가 아니라 검증-오류메시지용으로만 남는다.

## 6. 컴포넌트 변경 (최소 변경)

| 파일 | 변경 |
|------|------|
| `img2txt/bench/aihub.py` | join을 id순 → 읽기순서로 교체(5절). `_validate_bbox`에 x/y 검증(숫자/NaN/길이) 추가. 읽기순서 진단 메타(bbox_count, row_count, median_height, suspicious_layout_flag) 산출 |
| `img2txt/bench/scoring.py` | `char_miss_rate`, `char_extra_rate` 추가(4절 산식). 기존 `cer`/`wer`/`levenshtein` 불변 |
| `scripts/bench_ocr.py` `_score_outputs` (117행~) | 3지점별 놓침률-추가율 + 빈정답 환각 진단(`empty_ref_with_output`, `empty_ref_extra_chars`) 계산해 PageRecord에 전달 |
| `img2txt/bench/report.py` | `PageRecord`에 `char_miss_rate`, `char_extra_rate`, `empty_ref_with_output`, `empty_ref_extra_chars` 필드 추가; `summarize()` points에 micro 놓침률-추가율 + 빈정답 환각 페이지 수 집계. `degraded_page_count`는 유지 |

핵심: 정답 생성 방식 한 곳(어댑터)만 읽기순서로 바꾸면 그 정답 하나로 CER(순서 반영)-놓침/추가(순서 무관 multiset)가 다 파생된다.

## 7. 재측정 방법

캐시된 baseline JSONL(`bench_data/reports/baseline-*.jsonl`)의 `output_text`를 재사용하고, 라벨 JSON에서 읽기순서 정답을 재도출해 신규 지표를 recompute한다. OCR 재실행 없음. 산출물: 4세트(2010/1990/1980/b1980) id순 CER → 읽기순서 CER → 놓침률 → 추가율 before/after 표를 신규 벤치 리포트(`docs/bench/2026-07-17-reading-order-metric.md`)로 정리. 재측정 스크립트는 하네스 함수(교체된 어댑터, 신규 scoring)를 그대로 호출해 하네스와 재측정이 같은 코드를 쓰도록 한다.

검증 기준: 놓침률이 truth-check 근사치(2010 약 1%, b1980 약 17%)와 일치하고, 읽기순서 CER이 id순 대비 하락하면 성공.

## 8. 스펙/문서 개정 대상

- 상위 스펙 5.3 채점규칙: 놓침률(주)/읽기순서 CER(델타)/추가율(진단) 정의 + 공백-정규화 처리 명시, id순 join 서술 → 읽기순서 join으로 교체.
- 상위 스펙 5.6 리포트 스키마: PageRecord 신규 필드(char_miss_rate, char_extra_rate, empty_ref_with_output, empty_ref_extra_chars)와 읽기순서 진단 메타, summary 신규 집계(micro 놓침률-추가율, 빈정답 환각 페이지 수) 반영.
- 상위 스펙 6절 전처리 채택 규칙: 레버는 "놓침률을 개선(하락)하고 추가율-degraded_page_count를 악화시키지 않을 때만" 채택 후보로 명시. 놓침률 개선 없이 CER만 변하는 경우는 채택하지 않는다.
- 상위 스펙 7.3 D8 판정규칙: 품질 하한=corrected 놓침률(통과선은 baseline 분포 근거로 LLM 트랙에서 확정), 랭킹=비용→속도(기존 유지, 놓침률 게이트 통과가 선행), 부작용 감시=읽기순서 CER 델타 + degraded_page_count + 추가율 증가 + 빈정답 환각. 읽기순서 CER 델타는 랭킹 축이 아니라 부작용 축임을 명시.
- 신규 벤치 리포트(7절).

## 9. 테스트

- `tests/bench/test_aihub.py`: 현재 id순 join assert를 읽기순서 기대값으로 갱신. y가 뒤섞인 Bbox 재정렬, 같은 행 x정렬, x/y 누락 시 ValueError 케이스 추가. 엣지: 0/음수 height, NaN/무한대 좌표, x-y 길이 불일치, 좌우 2열/표형 배치(오묶음 관측-suspicious_layout_flag).
- 신규 scoring 테스트: 놓침률/추가율 — 완전일치(0), 일부 누락, 초과(환각), 빈 정답+출력 있음(empty_ref_with_output/extra_chars 진단), 공백 제외 확인.
- `report.py` summarize: 신규 micro 집계 필드가 나오는지, 빈 페이지 및 빈정답 환각 페이지 집계 테스트.

## 10. 리스크와 불확실성

- ⚠️ 읽기순서 휴리스틱 잔차: 다열-표 양식은 Vision 실제 읽기경로와 완벽히 못 맞음(2010 재정렬 후에도 11.6%). 완화 논리는 "델타가 완전 상쇄"가 아니라 "주 판정은 순서무관 놓침률이 담당하고, 읽기순서 CER은 부작용 감시라 잔차에 덜 민감"이다. LLM이 텍스트를 재배열하면 잔차가 가설에 따라 달라져 완화가 약해지므로, 오묶음 이상치는 suspicious_layout_flag로 관측한다.
- ⚠️ 놓침률 과소평가: 위치 틀린 오인식, 필드 간 값 이동, 의미 오류, 같은 글자 반복 오류(정답에 있는 글자면 다른 위치 오인식도 상쇄됨), 환각을 못 잡음 → 추가율-읽기순서 CER 델타-빈정답 진단으로 보완(병행 설계의 이유).
- ⚠️ 추가율 분모(정답 글자수)는 라벨 불완전성이 크면 값이 커질 수 있음 — 진단용이지 합격/불합격 단독 판정엔 안 씀.
- ⚠️ 재측정은 baseline(원본)만 — 전처리본 JPEG 재압축 교란(#13)은 별도. baseline은 교란 없어 지표 검증엔 충분.

## 11. 근거 실측 데이터 (재현 메타)

- 데이터: AI Hub dataSetSn=71299 Validation, 2010(`AF_2010_5270218_0001`)-b1980(`AF_b1980_5350073_0001`) 각 앞 50페이지.
- 방법: `bench_data/reports/baseline-{2010,AF_b1980_5350073_0001}.jsonl`의 raw 지점 `normalized_output` + 라벨 JSON 읽기순서 재도출, `normalize_strict` 적용 후 micro 집계. A/C가 문서 기록치(0.1736/0.5324, 놓침 약1%/약17%)와 일치.
