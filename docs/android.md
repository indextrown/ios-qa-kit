# 안드로이드 (미리 보기)

에뮬레이터·안드로이드 기기에서 iOS와 같은 `.qa.yml` 시나리오를 돌립니다. 옵션까지 전부는 [cli.md 안드로이드](../skills/qa-kit/references/cli.md#안드로이드-미리-보기).

[← README](../README.md)

## 시작하기

`qakit init`은 아직 안드로이드를 탐지하지 않습니다. 작업공간 폴더에 `qakit.yml`을 직접 씁니다.

```bash
qakit android setup          # JDK 17·SDK·에뮬레이터·AVD 설치 (한 번, Android Studio 없이)
qakit android boot           # 에뮬레이터 띄우기
```

```yaml
# qakit.yml
platform: android
app:
  project: ../            # Gradle 루트 (settings.gradle(.kts)가 있는 폴더)
  module: app             # 기본 app
  variant: debug          # 기본 debug
  packageName: com.example.app
emulator: qakit           # AVD 이름 (기본 qakit)
```

```bash
qakit doctor && qakit build-app && qakit run <시나리오>
```

- 기기가 여러 대면 `ANDROID_SERIAL=<serial>` 또는 `--avd`.

## 명령

| 명령 | 하는 일 |
|---|---|
| `qakit android setup` | JDK 17·Android SDK·에뮬레이터·AVD(`qakit`) 설치. **Android Studio 없이**. 태블릿: `--avd qakit-tablet --device-profile pixel_tablet` |
| `qakit android doctor` | 안드로이드 도구·AVD·연결된 기기 점검 |
| `qakit android boot [--avd 이름] [--landscape]` | 에뮬레이터 띄우기 (부팅 완료까지 기다림). `--landscape`: 가로로 고정 |
| `qakit android rotate landscape\|portrait\|auto` | 실행 중인 에뮬레이터 화면 방향 바꾸기 |
| `qakit android screen [--json]` | 지금 화면의 앱·Activity·Fragment |
| `qakit android dump [--package P] [-o 파일] [--json]` | 지금 화면 구조를 iOS `dump-ui`와 같은 형식으로 (작업공간 없이) |
| `qakit android logs [--since 10m] [-f] [--level W] [--grep 글자] [--crash] [--net]` | 앱 로그(uid로 거름, 재실행해도 이어짐). 끝에 크래시·ANR·실패한 요청·많은 오류 요약. `--crash`: 크래시·ANR만 (release는 `mapping.txt`로 스택 복원) |

## 작업공간에서

`qakit.yml`에 `platform: android`를 적으면 아래 명령이 안드로이드로 동작합니다.

| 기능 | 내용 |
|---|---|
| `qakit doctor`·`dump-ui`·`run`·`do`·`serve` | 같은 `.qa.yml` 문법, UiAutomator2 상주 실행기 |
| `qakit build-app` | Gradle 빌드 → 설치 → 권한. 앱이 바뀌면 자동 재빌드 |
| `qakit ui` 라이브 세션 | 화면 보기 12fps·직접 터치·녹화. 에뮬레이터 GPU 가속이 켜져 있어야 부드럽습니다 (`qakit android setup`이 켬) |
| `run` 실패 요약 | 그 실행 동안의 앱 크래시·ANR·실패한 요청(OkHttp 로그, 보통 debug 빌드만)·오류 로그가 붙습니다. 결과 폴더에 `logcat.txt`(인증 값 가림)·`crash.txt` |

## 한계

- Compose 화면은 앱에 testTag가 있어야 ID로 찾습니다 (없으면 글자로).
- 실패 영상, `--bench`는 아직입니다. AI QA·AI 채팅은 됩니다 (직접 터치는 `adb input`, 화면 사진은 `screencap`). 문제 보고 영상은 아직 iOS만.
- 설계: [PLAN.md](PLAN.md#안드로이드-지원-설계-진행-중)
