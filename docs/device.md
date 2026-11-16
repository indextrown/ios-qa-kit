# 실기기에서 실행 (`--device`)

같은 Wi-Fi(또는 케이블)로 연결된 iPhone·iPad에서 시나리오와 성능 측정을 그대로 돌립니다. 명령 뒤에 `--device`만 붙이면 됩니다.

[← README](../README.md)

```bash
qakit run <시나리오> --device                          # 기기 목록이 뜨고 ↑↓ · Enter로 고름 (= --device select)
qakit run <시나리오> --device "내 iPhone"              # 이름으로 바로
qakit run <시나리오> --device last                     # 지난번에 고른 기기
qakit run <시나리오> --device last --bench 5m          # 실기기 성능 측정 (Time Profiler)
qakit build-app --device last                          # 기기에 앱만 빌드·설치
```

```text
실행할 기기를 고르세요  (↑↓ 이동 · Enter 선택 · Esc 취소)

  ❯ 내 iPhone      iPhone 15          iOS 26.6   케이블 연결됨   ← 지난번
    팀 iPad        iPad Air (4th…)    iOS 26.5   같은 네트워크 (실행할 때 연결)
    시뮬레이터     iPhone 17          (qakit.yml의 simulator)
    옛 iPhone      iPhone 13          iOS 27.0   연결 안 됨        ← 흐리게, 고를 수 없음
```

**처음 한 번 (기기마다)**

1. 기기에서 **개발자 모드**를 켠다: 설정 › 개인정보 보호 및 보안 › 개발자 모드
2. 케이블로 연결해 Xcode에서 페어링하고 "네트워크로 연결"을 켠다. 그다음부터는 같은 Wi-Fi에서 무선으로 된다.
3. 실행하는 동안 기기 잠금을 풀어 둔다.

**qakit이 대신 하는 일**

| 단계 | 시뮬레이터 | 실기기 |
|---|---|---|
| 앱 빌드 | 서명 없이 | 앱의 개발자 팀으로 자동 서명 (`-allowProvisioningUpdates`) |
| 자동 ID (AutoID) | dylib을 환경변수로 주입 | dylib을 앱 안 `Frameworks/`에 넣고 앱과 같은 인증서로 다시 서명한 뒤 주입 |
| 설치 | `simctl install` | `devicectl device install app` |
| 시나리오 전달 | 파일 경로 | 기기 안 실행기는 Mac 파일을 못 읽어서 내용째(base64) 전달 |
| `pref` 조건 (앱 설정 값) | Mac에서 설정 파일을 직접 읽음 | AutoID가 앱 설정 값을 보이지 않는 요소(`QAKit.prefs`)에 담아 두고 테스트가 읽음 |
| 덤프 (`dump:`·`dump-ui`) | 결과 폴더에 바로 저장 | 테스트 첨부로 받아 결과 폴더로 꺼냄 |
| `--bench` | `ps`(CPU·메모리) + `sample`(함수) | **Time Profiler** 하나로 CPU %와 함수 목록. `bench.trace`는 Instruments로 바로 열림. 메모리는 같이 녹화하는 Activity Monitor에서 |

**성능 측정(`--bench`)은 어디서 무엇이 되나**

| | 시뮬레이터 | 실기기 |
|---|---|---|
| Time Profiler 기록 (`bench.trace`) | ❌ — 명령어(`xctrace`)로 시뮬레이터 앱에 붙으면 녹화가 시작되지 않고 멈춘다 | ✅ |
| 함수별 CPU (요약의 상위 함수) | ✅ `sample`로 대신 기록 (`bench-sample.txt`) | ✅ Time Profiler에서 |
| 호출 트리 텍스트 | ✅ `bench-sample.txt` (sample 원본) | ✅ `bench-calltree.txt` (Time Profiler 샘플로 만든 한글 트리, 0.5% 이상만) |
| CPU % (1초 단위) | ✅ `ps` | ✅ Time Profiler 샘플로 계산 |
| 메모리 (1초 단위) | ✅ `ps` | ✅ Activity Monitor (Time Profiler와 같이 녹화, Xcode 메모리 게이지와 같은 physical footprint) |

- **Time Profiler는 실기기에서만 된다.** 시뮬레이터 앱을 Time Profiler로 보려면 Instruments 앱에서 직접 녹화한다.
- **실기기 측정(`--bench`)은 케이블로 연결해서 한다.** 무선에서는 Time Profiler가 앱에 붙지 못하고(`Cannot find process`), 대신 하는 기기 전체 녹화도 테스트와 같이 돌면 몇 초 만에 끊긴다(`Device disconnected`). 시나리오 실행만은 무선으로 된다. 무선으로 측정을 시작하면 qakit이 미리 알리고, 녹화가 짧게 끊기면 요약에 적는다.
- 권한(위치 등)은 미리 허용할 수 없다. 처음 한 번 기기에서 허용하거나 시나리오가 팝업을 누르게 한다.
- `--reset`은 앱 재설치만 한다. 키체인은 지울 수 없어 저장된 로그인 정보가 남을 수 있다.
- 서명 팀은 앱 빌드 설정의 `DEVELOPMENT_TEAM`을 쓴다. 다르게 하려면 `qakit.yml`에 `device: { team: <팀 ID> }`.
- 실기기 실행은 `qakit run`(시나리오)·`dump-ui`·`build-app`에서 된다. `qakit test`(Swift 테스트)는 아직 시뮬레이터만.
