# swiftui-ids

SwiftUI 소스에 `.accessibilityIdentifier(…)`를 자동으로 끼워 넣는 도구. **QA 워크트리에서 빌드하는 동안만** 쓴다 (개발 폴더에 쓰지 않는다). 규칙은 `docs/PLAN.md`의 "ID 규칙 (SwiftUI)".

```bash
swift build -c release                      # 처음 한 번, 약 3분 (SwiftSyntax)
.build/release/swiftui-ids list <폴더>... [--exclude 이름] [--json]     # ID 목록만
.build/release/swiftui-ids insert <폴더>... --manifest <파일>           # 소스에 삽입, 원본은 manifest에 보관
.build/release/swiftui-ids restore --manifest <파일>                    # 원본으로 복원
```

- `list`와 `insert`는 같은 코드를 쓰므로 상수 생성과 삽입이 어긋나지 않는다.
- 앱이 이미 붙인 `.accessibilityIdentifier`·`.accessibilityHidden`이 있는 식은 건드리지 않는다.
- `Pods`, `.build`, `Derived`, `Vendor`, `*Tests`, `*Demo` 폴더와 `#Preview`는 건너뛴다.
