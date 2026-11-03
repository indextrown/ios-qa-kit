//
//  QAApp.swift
//  QAKit
//
//  설정(qakit.yml)에 맞춰 대상 앱을 실행한다. 자동 ID dylib 주입, 언어 고정을 처리한다.
//

import XCTest

@MainActor
public enum QAApp {

    /// 대상 앱 객체 (실행하지 않음)
    public static func make() -> XCUIApplication {
        let app = XCUIApplication(bundleIdentifier: QAConfig.bundleId)
        if let dylib = QAConfig.autoIDDylib {
            app.launchEnvironment["DYLD_INSERT_LIBRARIES"] = dylib
        }
        if let language = QAConfig.language {
            app.launchArguments += ["-AppleLanguages", "(\(language))"]
        }
        if let locale = QAConfig.locale {
            app.launchArguments += ["-AppleLocale", locale]
        }
        return app
    }

    /// 앱을 새로 실행한다 (이미 실행 중이면 종료 후 재실행). 앱 데이터는 유지된다.
    @discardableResult
    public static func launch(
        arguments: [String] = [],
        environment: [String: String] = [:]
    ) -> XCUIApplication {
        let app = make()
        app.launchArguments += arguments
        environment.forEach { app.launchEnvironment[$0.key] = $0.value }
        app.launch()
        return app
    }

    /// 이미 떠 있는 앱을 앞으로 가져온다. 실행 중이 아니면 새로 실행한다.
    /// 주의: qakit 밖에서 실행된 앱이면 자동 ID가 없다.
    @discardableResult
    public static func attach() -> XCUIApplication {
        let app = make()
        if app.state == .notRunning { app.launch() } else { app.activate() }
        return app
    }
}
