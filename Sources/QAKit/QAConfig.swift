//
//  QAConfig.swift
//  QAKit
//
//  qakit CLI가 qakit.yml을 읽어 TEST_RUNNER_QA_* 환경변수로 넘긴 값을 읽는다.
//  (xcodebuild는 TEST_RUNNER_ 접두어를 떼고 테스트 프로세스에 전달한다)
//

import Foundation

public enum QAConfig {

    static var env: [String: String] { ProcessInfo.processInfo.environment }

    /// 테스트 대상 앱의 bundle ID (qakit.yml: app.bundleId)
    public static var bundleId: String {
        guard let value = env["QA_BUNDLE_ID"], !value.isEmpty else {
            fatalError("QA_BUNDLE_ID가 없습니다. 테스트는 `qakit test`로 실행하세요.")
        }
        return value
    }

    /// 자동 ID dylib 경로. 없으면 주입하지 않는다 (qakit.yml: autoid: embedded 인 경우)
    public static var autoIDDylib: String? { nonEmpty("QA_AUTOID_DYLIB") }

    /// 앱 언어 (qakit.yml: language), 예) ko
    public static var language: String? { nonEmpty("QA_LANGUAGE") }

    /// 앱 지역 (qakit.yml: locale), 예) ko_KR
    public static var locale: String? { nonEmpty("QA_LOCALE") }

    /// 실기기에서 실행 중 (qakit run --device). Mac 파일을 읽고 쓸 수 없어 결과는 테스트 첨부로 넘긴다
    public static var isDevice: Bool { env["QA_DEVICE"] == "1" }

    /// 결과물(덤프 등)을 저장할 호스트 폴더
    public static var resultsDir: String? { nonEmpty("QA_RESULTS_DIR") }

    /// 비밀값 파일 경로 (환경변수로 비밀값이 오지 않았을 때 대비)
    public static var secretsFile: String? { nonEmpty("QA_SECRETS_FILE") }

    /// 임의 키 읽기 (CLI의 --env KEY=VALUE 로 넘긴 값)
    public static func value(_ key: String) -> String? { nonEmpty("QA_ARG_\(key)") }

    private static func nonEmpty(_ key: String) -> String? {
        guard let value = env[key], !value.isEmpty else { return nil }
        return value
    }
}
