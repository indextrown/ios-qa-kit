//
//  Model.swift
//  swiftui-ids
//
//  규칙은 docs/PLAN.md "ID 규칙 (SwiftUI)"과 같아야 한다. 이 도구가 삽입(insert)과 목록(list)에 같이 쓰이므로
//  규칙이 한 곳에만 있다 (gen_ids.py는 SwiftUI ID를 이 도구에서 받는다).
//

import Foundation
import SwiftSyntax

/// SwiftUI 말단 컨트롤. 키는 호출 이름, 값은 바인딩 인자 라벨(우선순위 순).
let controls: [String: [String]] = [
    "Button": [], "NavigationLink": [], "Link": [], "Menu": [],
    "TextField": ["text", "value"], "SecureField": ["text"], "TextEditor": ["text"],
    "Toggle": ["isOn"], "Picker": ["selection"], "Slider": ["value"], "Stepper": ["value"],
    "DatePicker": ["selection"], "ColorPicker": ["selection"],
]

/// 행을 만드는 호출. 트레일링 클로저 안 단일 식이 행 콘텐츠.
let repeaters: Set<String> = ["ForEach", "List"]

/// 라벨 클로저 안에서 라벨 글자를 찾을 때 보는 호출
let labelCarriers: Set<String> = ["Text", "Label"]

let maxLabelLength = 20

/// 소스에서 찾은 View 타입 하나 (struct, 중첩이면 "바깥.안쪽")
final class ViewDecl {
    let module: String                 // 소스 루트 기준 모듈 키 (같은 타입 이름이 다른 모듈에 있을 수 있다)
    let path: String
    var controlCount = 0               // 직접 가진 말단 컨트롤 수
    var looseLeafCount = 0             // 컨트롤 밖에 있는 Text/Image/Label 수 (있으면 "컨트롤 하나짜리"가 아니다)
    var customCalls: [String] = []     // 호출한 (앱) 커스텀 뷰 타입 이름
    var hasRepeater = false            // ForEach/List가 있으면 컨트롤 수를 셀 수 없음
    init(module: String, path: String) { self.module = module; self.path = path }
    var key: String { ViewDecl.key(module, path) }
    static func key(_ module: String, _ path: String) -> String { module + "|" + path }
}

/// 컨트롤 호출 하나 (이름 계산 전)
struct Candidate {
    enum Kind {
        case control(String)           // Button, TextField ...
        case custom(String)            // 앱 커스텀 뷰 호출부 (컨트롤 하나짜리일 때만 ID를 붙인다)
        case row                       // ForEach/List 행 콘텐츠
    }
    let kind: Kind
    let module: String
    let view: String                   // 접두사가 되는 View 타입 경로
    let file: String
    let line: Int
    let order: Int                     // 파일 안 등장 순서 (정렬용)
    let insertOffset: Int              // UTF-8 바이트 오프셋. 이 자리에 수식어를 끼워 넣는다
    let bindingPath: String?           // "$email" → "email", "$vm.email" → "vm.email"
    let label: String?                 // 리터럴 라벨 (정리 전)
    let argLiteral: String?            // 커스텀 뷰 첫 인자 리터럴 (.kakao, "x")
    let hasOwnID: Bool                 // 앱이 이미 .accessibilityIdentifier / .accessibilityHidden을 붙임
}

/// 최종 결과 한 줄
struct Assigned: Codable {
    let id: String
    let file: String
    let line: Int
    let kind: String                   // Button, TextField, custom:SocialLoginButton, row
    let view: String
    let modifier: String               // 삽입할 수식어 텍스트
    let offset: Int
    /// 컨트롤 하나짜리 커스텀 뷰 안쪽 ID. 호출부 ID가 있으면 실행 중엔 그쪽이 보인다.
    let overridable: Bool
}

struct Manifest: Codable {
    var version = 1
    var createdAt: String
    var files: [ManifestFile]
    var ids: [Assigned]
}

struct ManifestFile: Codable {
    let path: String
    let original: String               // 원래 내용 전체 (복원용. SwiftUI 파일만이라 크지 않다)
    let insertedSHA: String            // 삽입 뒤 내용의 해시 (복원 전에 손댔는지 확인)
}
